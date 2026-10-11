import runpy
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def builder():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_portable.py"))


def test_source_archive_contains_current_sources_and_build_inputs_without_runtime_files(
    builder, tmp_path, monkeypatch,
):
    root = tmp_path / "project"
    files = {
        "LICENSE": "Moru GPL license",
        "src/moru/service.py": "current application source",
        "frontend/src/App.tsx": "current frontend source",
        "frontend/package-lock.json": "frontend lock",
        "scripts/build_portable.py": "build script",
        "pyproject.toml": "build metadata",
        "uv.lock": "python lock",
        "vendor/comfyui-revision.txt": "pinned revision",
        "vendor/comfyui/LICENSE": "ComfyUI GPL license",
        "vendor/comfyui/comfy/sd.py": "pinned engine source",
        "data/private.db": "private history",
        "models/private.gguf": "model weights",
    }
    for name, contents in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def git_output(command):
        repository = Path(command[command.index("-C") + 1])
        if repository == root:
            assert "--others" in command
            assert "--exclude-standard" in command
            assert "data" not in command
            assert "models" not in command
            names = [
                name for name in files
                if not name.startswith(("vendor/comfyui/", "data/", "models/"))
            ]
            names.append("src/moru/deleted.py")
        else:
            assert repository == root / "vendor/comfyui"
            names = ["LICENSE", "comfy/sd.py"]
        return ("\0".join(names) + "\0").encode()

    monkeypatch.setattr(subprocess, "check_output", git_output)
    application = tmp_path / "distribution"
    application.mkdir()

    builder["copy_source_archive"](application, root)

    with zipfile.ZipFile(application / "Moru-source.zip") as archive:
        assert archive.read("moru/src/moru/service.py").decode() == "current application source"
        assert archive.read("moru/frontend/src/App.tsx").decode() == "current frontend source"
        assert archive.read("moru/vendor/comfyui/comfy/sd.py").decode() == "pinned engine source"
        assert "moru/LICENSE" in archive.namelist()
        assert "moru/uv.lock" in archive.namelist()
        assert "moru/scripts/build_portable.py" in archive.namelist()
        assert not any("private" in name or "deleted" in name for name in archive.namelist())
    assert "Moru-source.zip" in (application / "SOURCE.txt").read_text(encoding="utf-8")


def test_missing_engine_sources_fail_without_replacing_an_existing_source_archive(
    builder, tmp_path, monkeypatch,
):
    (tmp_path / "Moru-source.zip").write_bytes(b"previous sources")
    root = tmp_path / "project"
    root.mkdir()
    (root / "LICENSE").write_text("Moru GPL license", encoding="utf-8")
    responses = iter([b"LICENSE\0", b""])
    monkeypatch.setattr(subprocess, "check_output", lambda command: next(responses))

    with pytest.raises(RuntimeError, match="No source files"):
        builder["copy_source_archive"](tmp_path, root)

    assert (tmp_path / "Moru-source.zip").read_bytes() == b"previous sources"
    assert not (tmp_path / "Moru-source.zip.part").exists()
