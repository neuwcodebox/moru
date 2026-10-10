"""Internal worker entry: protocol stdout, diagnostics stderr, no web server."""

import ctypes
import json
import logging
import os
import sys
from pathlib import Path
from threading import Event, Thread
from typing import TextIO

from moru.diagnostics import PrivateTracebackFormatter
from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.images.engine import ComfyEngine

log = logging.getLogger(__name__)


def inherited_stream(name: str, handle_number: int, mode: str) -> TextIO:
    stream = getattr(sys, name)
    if stream is not None:
        stream.reconfigure(encoding="utf-8")
        return stream
    # PyInstaller windowed Python sets stdio objects to None; the inherited pipes still exist.
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel.GetStdHandle(handle_number & 0xFFFFFFFF)
    descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY if mode == "r" else os.O_WRONLY)
    return os.fdopen(descriptor, mode, encoding="utf-8", buffering=1)


def monitor_parent(parent_pid: int):
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)
        if not handle:
            os._exit(0)
        try:
            result = kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            if result == 0:
                os._exit(0)
            log.error("parent process wait failed")
            os._exit(1)
        finally:
            kernel.CloseHandle(handle)
    else:
        stop = Event()
        while not stop.wait(1):
            if os.getppid() != parent_pid:
                os._exit(0)


def serve(input_stream: TextIO, output_stream: TextIO, engine, data_dir: Path):
    def send(request_id, message_type, payload):
        output_stream.write(
            json.dumps({"id": request_id, "type": message_type, "payload": payload}) + "\n"
        )
        output_stream.flush()

    for line in input_stream:
        request_id = None
        try:
            message = json.loads(line)
            request_id = message["id"]
            if message["type"] == "shutdown":
                return
            if message["type"] == "reserve_memory" and isinstance(request_id, str):
                required = message["payload"]["required_bytes"]
                if type(required) is not int or required <= 0:
                    raise MoruError("INVALID_REQUEST")
                engine.reserve_memory(required)
                send(request_id, "result", {})
                continue
            if message["type"] == "memory_budget" and isinstance(request_id, str):
                payload = message["payload"]
                settings = GenerationSettings(**payload["settings"])
                release = engine.needs_prompt_unload(settings, payload["paths"])
                send(request_id, "result", {"release_prompt": release})
                continue
            if message["type"] != "generate" or not isinstance(request_id, str):
                raise MoruError("INVALID_REQUEST")
            payload = message["payload"]
            settings = GenerationSettings(
                **{
                    key: payload[key]
                    for key in (
                        "model_id",
                        "width",
                        "height",
                        "steps",
                        "cfg",
                        "seed",
                    )
                }
            )
            if settings.seed is None or not isinstance(payload["prompt"], str):
                raise MoruError("INVALID_REQUEST")
            output_path = Path(payload["output_path"]).resolve()
            if (
                output_path.parent != (data_dir / "images").resolve()
                or output_path.suffix != ".png"
                or output_path.exists()
            ):
                raise MoruError("IMAGE_SAVE_FAILED")

            def progress(state, step=None, total=None, current_request_id=request_id):
                send(current_request_id, "progress", {"state": state, "step": step, "total": total})

            engine.generate(
                payload["prompt"],
                settings,
                output_path,
                progress,
                Event(),
                payload["paths"],
            )
            send(request_id, "result", {"image_path": str(output_path), "seed": settings.seed})
        except Exception as exc:
            code = exc.code if isinstance(exc, MoruError) else "GENERATION_FAILED"
            log.exception("worker generation failed id=%s code=%s", request_id, code)
            send(request_id, "error", {"code": code})


def run(root: Path, comfy_root: Path, parent_pid: int):
    input_stream = inherited_stream("stdin", -10, "r")
    protocol_stream = inherited_stream("stdout", -11, "w")
    sys.stderr = inherited_stream("stderr", -12, "w")
    sys.stdout = sys.stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        PrivateTracebackFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    Thread(target=monitor_parent, args=(parent_pid,), daemon=True, name="parent-watch").start()
    log.info("image worker ready pid=%s", os.getpid())
    try:
        serve(input_stream, protocol_stream, ComfyEngine(comfy_root), root / "data")
    finally:
        log.info("image worker shutdown")
