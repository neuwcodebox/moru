"""Desktop composition root. Inference is lazy and runs outside the UI thread."""

import argparse
import ctypes
import logging
import sys
from importlib.resources import files
from logging.handlers import RotatingFileHandler
from pathlib import Path

from moru.api import Api
from moru.application_lock import application_lock
from moru.chatgpt_auth import ChatGPTAuth
from moru.chatgpt_credentials import CredentialStore, credential_path
from moru.chatgpt_http import ChatGPTHttp
from moru.chatgpt_prompts import ChatGPTPrompts
from moru.clipboard import copy_image, copy_text
from moru.config import ModelPaths, application_root
from moru.diagnostics import PrivateTracebackFormatter
from moru.downloads import ModelDownloads
from moru.language import model_file_filter, startup_language, startup_message
from moru.prompt_providers import PromptProviders
from moru.prompting import LlamaPrompts
from moru.repository import Repository
from moru.service import Application
from moru.worker_client import ImageWorker


def configure_logging(root: Path):
    logs = root / "data/logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logs / "app.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        PrivateTracebackFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Moru")
    parser.add_argument("--internal-image-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, default=application_root(), help=argparse.SUPPRESS)
    parser.add_argument("--comfy-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--internal-smoke-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--internal-smoke-ui-only", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    comfy_root = arguments.comfy_root or (
        Path(sys._MEIPASS) if getattr(sys, "frozen", False) else root / "vendor/comfyui"
    )
    if arguments.internal_image_worker:
        if not arguments.parent_pid:
            parser.error("internal worker requires parent pid")
        from moru.image_worker import run

        run(root, comfy_root, arguments.parent_pid)
        return
    log = logging.getLogger(__name__)
    try:
        with application_lock(root / "data"):
            _run_desktop(root, comfy_root, arguments)
    except Exception as exc:
        log.exception("desktop startup failed")
        if arguments.internal_smoke_report is not None:
            import json

            arguments.internal_smoke_report.write_text(
                json.dumps({"ok": False, "error": "desktop startup failed"}), encoding="utf-8"
            )
        elif sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                0,
                startup_message(exc, startup_language(root)),
                "Moru",
                0x10,
            )
        else:
            raise


def _run_desktop(root, comfy_root, arguments):
    configure_logging(root)
    log = logging.getLogger(__name__)
    log.info("app started")
    application = None
    downloads = None
    chatgpt_auth = None
    try:
        html = files("moru").joinpath("web/index.html").read_text(encoding="utf-8")
        paths = ModelPaths(root)
        model_status = paths.status()
        log.info(
            "model availability checked available=%s total=%s",
            sum(item["available"] for item in model_status),
            len(model_status),
        )
        chatgpt_http = ChatGPTHttp()
        chatgpt_auth = ChatGPTAuth(CredentialStore(credential_path()), http=chatgpt_http)
        chatgpt_prompts = ChatGPTPrompts(chatgpt_auth, chatgpt_http)
        application = Application(
            Repository(root / "data/anima.db"),
            PromptProviders(LlamaPrompts(paths), chatgpt_prompts),
            ImageWorker(paths, comfy_root),
            root / "data",
        )
        downloads = ModelDownloads(paths)
        import webview

        def choose_file(model_id):
            selected = window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=(model_file_filter(model_id, application.get_language()),),
            )
            return selected[0] if selected else None

        window = webview.create_window(
            "Moru",
            html=html,
            js_api=Api(
                application,
                paths,
                downloads,
                choose_file,
                copy_to_clipboard=lambda text: copy_text(window, text),
                copy_image_to_clipboard=lambda content: copy_image(window, content),
                chatgpt_auth=chatgpt_auth,
                chatgpt_prompts=chatgpt_prompts,
            ),
            width=1080,
            height=900,
            min_size=(640, 600),
            background_color="#14171b",
            hidden=arguments.internal_smoke_report is not None,
        )
        startup = None
        startup_arguments = None
        if arguments.internal_smoke_report is not None:
            from moru.runtime_smoke import verify_window

            startup = verify_window
            startup_arguments = (
                window,
                arguments.internal_smoke_report,
                arguments.internal_smoke_ui_only,
            )
        webview.start(
            startup,
            args=startup_arguments,
            gui="edgechromium" if sys.platform == "win32" else None,
            http_server=False,
            debug=False,
            storage_path=str(root / "data/webview"),
            icon=str(files("moru").joinpath("assets/icon.ico")),
        )
    finally:
        try:
            if downloads is not None:
                downloads.close()
        finally:
            try:
                if application is not None:
                    application.close()
            finally:
                if chatgpt_auth is not None:
                    chatgpt_auth.close()
                log.info("app stopped")
