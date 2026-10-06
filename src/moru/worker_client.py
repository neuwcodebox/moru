"""Hidden self-spawned image worker, JSON Lines pipes and cancellable observation."""

import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock, Thread

from moru.config import ModelPaths
from moru.domain import GenerationSettings
from moru.errors import MESSAGES, MoruError
from moru.ports import Progress
from moru.windows_job import WindowsJob

log = logging.getLogger(__name__)


def worker_command(root: Path, comfy_root: Path, parent_pid: int) -> list[str]:
    executable = (
        [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "moru"]
    )
    return executable + [
        "--internal-image-worker",
        "--parent-pid",
        str(parent_pid),
        "--root",
        str(root),
        "--comfy-root",
        str(comfy_root),
    ]


def parse_worker_message(line: str, request_id: str) -> dict:
    try:
        message = json.loads(line)
        if (
            not isinstance(message, dict)
            or message.get("id") != request_id
            or message.get("type") not in ("progress", "result", "error")
            or not isinstance(message.get("payload"), dict)
        ):
            raise ValueError("invalid worker message")
        return message
    except (TypeError, ValueError) as exc:
        raise MoruError("GENERATION_FAILED") from exc


class ImageWorker:
    def __init__(self, paths: ModelPaths, comfy_root: Path):
        self._paths, self._comfy_root = paths, comfy_root
        self._process = None
        self._lock = RLock()
        self._closed = False
        self._messages = None
        self._process_job = None

    def _start(self):
        with self._lock:
            if self._closed:
                raise MoruError("GENERATION_CANCELLED")
            if self._process is not None and self._process.poll() is None:
                return self._process, self._messages
            self._stop()
            logs = self._paths.root / "data/logs"
            logs.mkdir(parents=True, exist_ok=True)
            process_job = WindowsJob() if sys.platform == "win32" else None
            process = None
            try:
                with (logs / "image-worker.log").open("ab") as error_log:
                    process = subprocess.Popen(
                        worker_command(self._paths.root, self._comfy_root, os.getpid()),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=error_log,
                        text=True,
                        encoding="utf-8",
                        bufsize=1,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                if process_job is not None:
                    process_job.assign(process._handle)
            except (OSError, MoruError) as exc:
                if process_job is not None:
                    process_job.close()
                if process is not None:
                    process.kill()
                    process.wait()
                raise MoruError("IMAGE_WORKER_START_FAILED") from exc
            messages = Queue()

            def read_messages():
                try:
                    for line in process.stdout:
                        messages.put(line)
                finally:
                    messages.put(None)

            Thread(target=read_messages, daemon=True, name="worker-output").start()
            self._process, self._messages = process, messages
            self._process_job = process_job
            log.info("image worker started pid=%s", process.pid)
            return process, messages

    def _stop(self):
        with self._lock:
            process = self._process
            process_job = self._process_job
            self._process, self._messages = None, None
            self._process_job = None
        if process is None:
            return
        if process.poll() is None:
            try:
                process.stdin.write('{"id":"shutdown","type":"shutdown"}\n')
                process.stdin.flush()
            except (OSError, ValueError):
                log.info("worker input already closed pid=%s", process.pid)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if process_job is not None:
                    process_job.close()
                else:
                    process.kill()
                process.wait()
        if process_job is not None:
            process_job.close()
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()
        log.info("image worker stopped pid=%s", process.pid)

    def reserve_memory(self, required_bytes: int, cancelled: Event):
        if required_bytes:
            self._request("reserve_memory", {"required_bytes": required_bytes}, cancelled)

    def needs_prompt_unload(self, settings: GenerationSettings, cancelled: Event) -> bool:
        result = self._request("memory_budget", {
            "settings": asdict(settings), "paths": self._paths.image_payload(settings.model_id),
        }, cancelled)
        if type(result.get("release_prompt")) is not bool:
            self._stop()
            raise MoruError("GENERATION_FAILED")
        return result["release_prompt"]

    def generate(
        self,
        prompt: str,
        settings: GenerationSettings,
        output_path: Path,
        progress: Progress,
        cancelled: Event,
    ):
        if output_path.exists():
            raise MoruError("IMAGE_SAVE_FAILED")
        paths = self._paths.image_payload(settings.model_id)
        payload = {
            **asdict(settings),
            "prompt": prompt,
            "output_path": str(output_path.resolve()),
            "paths": paths,
        }
        try:
            details = self._request("generate", payload, cancelled, progress)
            if (
                details.get("image_path") != str(output_path.resolve())
                or details.get("seed") != settings.seed
            ):
                self._stop()
                raise MoruError("GENERATION_FAILED")
        except MoruError as exc:
            if exc.code == "GENERATION_CANCELLED":
                output_path.unlink(missing_ok=True)
            raise
        finally:
            output_path.with_suffix(".png.part").unlink(missing_ok=True)

    def _request(self, message_type, payload, cancelled, progress=None):
        if cancelled.is_set():
            raise MoruError("GENERATION_CANCELLED")
        process, messages = self._start()
        request_id = uuid.uuid4().hex
        try:
            process.stdin.write(
                json.dumps({"id": request_id, "type": message_type, "payload": payload}) + "\n"
            )
            process.stdin.flush()
            while True:
                if cancelled.is_set() or self._closed:
                    self._stop()
                    raise MoruError("GENERATION_CANCELLED")
                try:
                    line = messages.get(timeout=0.1)
                except Empty:
                    continue
                if cancelled.is_set() or self._closed:
                    raise MoruError("GENERATION_CANCELLED")
                if line is None:
                    raise MoruError("GENERATION_FAILED")
                message = parse_worker_message(line, request_id)
                details = message["payload"]
                if message["type"] == "progress":
                    if progress is None:
                        raise MoruError("GENERATION_FAILED")
                    progress(
                        details.get("state", "generating"),
                        details.get("step"),
                        details.get("total"),
                    )
                elif message["type"] == "error":
                    code = details.get("code")
                    raise MoruError(code if code in MESSAGES else "GENERATION_FAILED")
                else:
                    return details
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, MoruError)
                else (
                    "GENERATION_CANCELLED"
                    if cancelled.is_set() or self._closed
                    else "GENERATION_FAILED"
                )
            )
            if code != "CUDA_OOM":
                self._stop()
            if isinstance(exc, MoruError):
                raise
            raise MoruError(code) from exc

    def close(self):
        with self._lock:
            self._closed = True
        self._stop()
