"""Run the actual windowed executable without development runtimes on PATH."""

import argparse
import json
import os
import sqlite3
import subprocess
import uuid
from pathlib import Path

from moru.config import DEFAULT_MODEL_FILES, ModelPaths, application_root
from moru.windows_job import WindowsJob


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("application", type=Path)
    parser.add_argument("--ui-only", action="store_true")
    options = parser.parse_args()
    root = application_root()
    smoke_root = root / "build" / f"smoke-{uuid.uuid4().hex[:8]}"
    smoke_root.mkdir(parents=True)
    models = ModelPaths(root)
    isolated_models = ModelPaths(smoke_root)
    for model_id in DEFAULT_MODEL_FILES:
        isolated_models.set(model_id, models.get(model_id))
    report_path = smoke_root / "report.json"
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join(
        (environment["SYSTEMROOT"], str(Path(environment["SYSTEMROOT"]) / "System32"))
    )
    for name in list(environment):
        if name.startswith("CUDA_PATH") or name in ("PYTHONPATH", "PYTHONHOME"):
            environment.pop(name)
    command = [
        str((options.application / "Moru.exe").resolve()),
        "--root",
        str(smoke_root),
        "--internal-smoke-report",
        str(report_path),
    ]
    if options.ui_only:
        command.append("--internal-smoke-ui-only")
    job = WindowsJob()
    process = None
    try:
        process = subprocess.Popen(
            command, cwd=smoke_root, env=environment, creationflags=subprocess.CREATE_NO_WINDOW
        )
        job.assign(process._handle)
        process.wait(timeout=660)
        if process.returncode:
            raise RuntimeError(f"Portable process exited with {process.returncode}")
        report = json.loads(report_path.read_text("utf-8"))
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        assert report["ok"], report
        assert report["title"] == "Moru"
        assert report["defaults"]["steps"] == 10
        assert report["defaults"]["cfg"] == 1.0
        assert report["defaults"]["seed"] is None
        assert report["prompt_defaults"] == {
            "context_size": 2048,
            "max_tokens": 1024,
            "thinking": False,
        }
        if options.ui_only:
            assert report["clipboard_copied"]
            assert report["saved_prompt_settings"] == {
                "context_size": 4096,
                "max_tokens": 2048,
                "thinking": True,
            }
            print(f"portable_ui_and_clipboard_ok report={report_path}", flush=True)
            return
        assert report["image_size"] == [1024, 1024]
        assert report["prompt_written"]
        assert report["conversation_image_visible"]
        with sqlite3.connect(smoke_root / "data/anima.db") as database:
            prompt = database.execute(
                "SELECT prompt FROM images WHERE id=?", (report["image_id"],)
            ).fetchone()[0]
        assert "<think>" not in prompt and "</think>" not in prompt
        assert not prompt.lstrip().startswith("Thinking Process:")
        print(f"portable_runtime_ok report={report_path}", flush=True)
    finally:
        job.close()
        if process is not None:
            process.wait()


if __name__ == "__main__":
    main()
