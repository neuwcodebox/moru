import json
import runpy
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def builder():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_portable.py"))


def test_archiver_uses_the_windows_executable_on_path(builder, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "C:/tools/7z.exe")
    assert builder["seven_zip"]() == "C:/tools/7z.exe"


def test_archiver_finds_a_standard_installation_without_path_changes(
    builder, monkeypatch, tmp_path,
):
    executable = tmp_path / "7-Zip/7z.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"archiver")
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert builder["seven_zip"]() == str(executable)


def test_missing_archiver_explains_the_installation_requirement(builder, monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Install Windows 7-Zip"):
        builder["seven_zip"]()


@pytest.fixture
def release_paths(tmp_path, monkeypatch):
    application = tmp_path / "dist/Moru"
    application.mkdir(parents=True)
    (application / "Moru.exe").write_bytes(b"application")
    release = tmp_path / "release"
    release.mkdir()
    (release / "Moru.7z").write_bytes(b"previous release")
    (release / "last-build.json").write_text("previous metadata", encoding="utf-8")
    (release / "Moru.7z.part").write_bytes(b"stale partial archive")
    monkeypatch.setattr("shutil.which", lambda _: "7z.exe")
    return application, release


def test_release_is_published_only_after_its_7z_integrity_check(
    builder, release_paths, monkeypatch,
):
    application, release = release_paths
    temporary = release / "Moru.7z.part"
    commands = []

    def run(command, *, cwd=None, check):
        assert check
        commands.append(command)
        assert (release / "Moru.7z").read_bytes() == b"previous release"
        if command[1] == "a":
            assert not temporary.exists()
            assert cwd == application.parent
            assert command[-1] == "Moru"
            assert "-t7z" in command
            assert Path(command[-2]) == temporary
            temporary.write_bytes(b"new release")
        else:
            assert command[1] == "t"
            assert Path(command[-1]) == temporary
            assert temporary.read_bytes() == b"new release"

    monkeypatch.setattr(subprocess, "run", run)
    builder["archive_release"](application, release)

    assert len(commands) == 2
    assert (release / "Moru.7z").read_bytes() == b"new release"
    assert not temporary.exists()
    assert json.loads((release / "last-build.json").read_text(encoding="utf-8")) == {
        "application": str(application), "archive": str(release / "Moru.7z"),
    }


@pytest.mark.parametrize("failed_operation", ["a", "t"])
def test_archive_failure_preserves_previous_release_and_cleans_partial_file(
    builder, release_paths, monkeypatch, failed_operation,
):
    application, release = release_paths
    temporary = release / "Moru.7z.part"

    def run(command, **kwargs):
        if command[1] == "a":
            temporary.write_bytes(b"unverified archive")
        if command[1] == failed_operation:
            raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        builder["archive_release"](application, release)

    assert (release / "Moru.7z").read_bytes() == b"previous release"
    assert (release / "last-build.json").read_text(encoding="utf-8") == "previous metadata"
    assert not temporary.exists()


def test_missing_application_fails_before_starting_the_archiver(builder, tmp_path, monkeypatch):
    def unexpected_run(*args, **kwargs):
        pytest.fail("The archiver must not start without a built application")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    with pytest.raises(FileNotFoundError, match="Build Moru.exe"):
        builder["archive_release"](tmp_path / "missing", tmp_path / "release")
