import runpy
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def builder():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_portable.py"))


def test_source_notice_provides_downloads_for_exact_build_revisions(builder, tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "vendor").mkdir(parents=True)
    (root / "vendor/comfyui-revision.txt").write_text("engine-revision\n", encoding="utf-8")
    application = tmp_path / "application"
    application.mkdir()
    responses = iter(["", "moru-revision\n"])
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: next(responses))

    builder["write_source_notice"](application, root)

    notice = (application / "SOURCE.txt").read_text(encoding="utf-8")
    assert "https://github.com/neuwcodebox/moru/archive/moru-revision.zip" in notice
    assert "https://github.com/Comfy-Org/ComfyUI/archive/engine-revision.zip" in notice
    assert "build scripts and lockfiles" in notice
    assert not (application / "Moru-source.zip").exists()


@pytest.mark.parametrize("status", [" M src/moru/service.py", "?? src/moru/new_feature.py"])
def test_uncommitted_sources_cannot_be_replaced_with_public_commit_links(
    builder, tmp_path, monkeypatch, status,
):
    notice = tmp_path / "SOURCE.txt"
    notice.write_text("previous source links", encoding="utf-8")
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: status)

    with pytest.raises(RuntimeError, match="Commit build inputs"):
        builder["write_source_notice"](tmp_path, tmp_path)

    assert notice.read_text(encoding="utf-8") == "previous source links"
