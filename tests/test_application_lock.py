import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from moru import desktop
from moru.application_lock import application_lock
from moru.domain import GenerationSettings, Project, Request
from moru.errors import MoruError
from moru.repository import Repository


def test_second_app_cannot_claim_the_same_data_folder(tmp_path):
    with application_lock(tmp_path):
        with pytest.raises(MoruError) as error, application_lock(tmp_path):
            pass
        assert error.value.code == "APP_ALREADY_RUNNING"
    with application_lock(tmp_path):
        pass


def test_failed_startup_releases_the_data_folder_lock(tmp_path):
    with pytest.raises(RuntimeError), application_lock(tmp_path):
        raise RuntimeError("startup failed")
    with application_lock(tmp_path):
        pass


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop startup notification")
def test_second_desktop_launch_does_not_interrupt_the_first_apps_request(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    repository = Repository(data_dir / "anima.db")
    repository.create_project(Project("project", "now"))
    repository.add_request(
        Request("request", "project", "girl", "now", None, "create", GenerationSettings())
    )
    message = Mock()
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", message)
    monkeypatch.setattr(sys, "argv", ["moru", "--root", str(tmp_path)])
    monkeypatch.setattr(desktop, "configure_logging", lambda root: None)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(create_window=Mock(), start=Mock()))
    try:
        with application_lock(data_dir):
            desktop.main()
        assert repository.get_request("request").status == "pending"
        assert "이미 실행 중" in message.call_args.args[1]
    finally:
        repository.close()
