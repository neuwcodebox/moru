import json
import sqlite3
from pathlib import Path

import pytest

from moru.api import Api
from moru.errors import MESSAGES, MoruError
from moru.language import model_file_filter, startup_language, startup_message
from moru.repository import Repository


def test_ui_language_defaults_to_korean_and_persists_separately_from_generation_settings(app):
    api = Api(app)
    before = api.bootstrap()["value"]
    assert before["language"] == "ko"

    assert api.set_language("en") == {"ok": True, "value": "en"}
    after = api.bootstrap()["value"]
    assert after["language"] == "en"
    for key in ("project", "settings", "prompt_settings"):
        assert after[key] == before[key]

    app.repository.close()
    app.repository = Repository(app.data_dir / "anima.db")
    assert Api(app).bootstrap()["value"]["language"] == "en"


@pytest.mark.parametrize("value", ["fr", "en-US", "", None, 1, {}, []])
def test_unsupported_language_is_rejected_without_changing_the_saved_choice(app, value):
    api = Api(app)
    api.set_language("en")
    assert api.set_language(value)["error"]["code"] == "INVALID_SETTINGS"
    assert app.get_language() == "en"


@pytest.mark.parametrize("value", ["fr", None, 1, {}])
def test_unsupported_saved_language_uses_english_fallback_without_rewriting_it(app, value):
    app.repository.set_preference("language", value)
    assert Api(app).bootstrap()["value"]["language"] == "en"
    assert app.repository.get_preference("language") == value


def test_language_can_change_during_generation_without_changing_the_request_or_its_settings(app):
    project = app.create_project()
    job = app.submit_request(project.id, "밤에 걷는 고양이")
    before = app.repository.get_request(job.request_id)
    assert Api(app).set_language("en")["ok"]
    assert app.repository.get_request(job.request_id) == before
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"


def test_failed_language_save_does_not_claim_success_or_change_the_language(app, monkeypatch):
    def unavailable(*args):
        raise MoruError("DATABASE_FAILED")

    monkeypatch.setattr(app.repository, "set_preference", unavailable)
    assert Api(app).set_language("en")["error"]["code"] == "DATABASE_FAILED"
    assert app.get_language() == "ko"


def test_startup_language_read_does_not_create_data_for_a_new_install(tmp_path):
    assert startup_language(tmp_path) == "ko"
    assert not (tmp_path / "data").exists()


def test_startup_language_read_never_recovers_another_instances_pending_request(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "anima.db") as db:
        db.executescript(
            "CREATE TABLE preferences (key TEXT, value TEXT);"
            "CREATE TABLE requests (status TEXT);"
            "INSERT INTO requests VALUES ('pending');"
        )
        db.execute("INSERT INTO preferences VALUES ('language', ?)", (json.dumps("en"),))
    assert startup_language(tmp_path) == "en"
    with sqlite3.connect(data / "anima.db") as db:
        assert db.execute("SELECT status FROM requests").fetchone()[0] == "pending"


def test_unreadable_startup_preference_still_provides_a_safe_default(tmp_path, caplog):
    data = tmp_path / "data"
    data.mkdir()
    (data / "anima.db").write_text("not a database")
    assert startup_language(tmp_path) == "en"
    assert "startup language preference could not be read" in caplog.text


@pytest.mark.parametrize(
    "code", ["APP_ALREADY_RUNNING", "DATABASE_FAILED", "MODEL_LOAD_FAILED"]
)
def test_native_startup_errors_follow_the_saved_language(code):
    error = MoruError(code)
    assert startup_message(error, "ko") == MESSAGES[code]
    assert startup_message(error, "en").isascii()
    assert startup_message(error, "en") != code


def test_unknown_startup_errors_never_expose_exception_details():
    error = RuntimeError("private path /secret/model.gguf")
    for language in ("ko", "en"):
        assert "private" not in startup_message(error, language)
        assert "WebView2 Runtime" in startup_message(error, language)


@pytest.mark.parametrize(
    ("model", "extension"), [("prompt", "gguf"), ("anima-turbo-v1.1", "safetensors")]
)
def test_native_model_file_filter_is_localized_without_changing_extensions(model, extension):
    assert model_file_filter(model, "en") == f"Model files (*.{extension})"
    assert model_file_filter(model, "ko") == f"모델 파일 (*.{extension})"


def test_both_frontend_languages_cover_every_backend_error_code():
    locales = Path(__file__).resolve().parents[1] / "frontend/src/locales"
    english = json.loads((locales / "en/errors.json").read_text(encoding="utf-8"))
    korean = json.loads((locales / "ko/errors.json").read_text(encoding="utf-8"))
    assert english.keys() == korean.keys()
    assert MESSAGES.keys() <= english.keys()
    assert all(isinstance(value, str) and value.strip() for value in english.values())
    assert all(isinstance(value, str) and value.strip() for value in korean.values())


@pytest.mark.parametrize("language", ["en", "ko"])
def test_saved_language_is_available_even_when_model_status_prevents_bootstrap(app, language):
    class UnavailableModels:
        def status(self):
            raise MoruError("MODEL_LOAD_FAILED")

    app.set_language(language)
    api = Api(app, downloads=UnavailableModels())
    assert api.get_language() == {"ok": True, "value": language}
    assert api.bootstrap()["ok"] is False


def test_inaccessible_startup_database_uses_english_without_hiding_the_error_dialog(
    tmp_path, monkeypatch,
):
    def inaccessible(self):
        raise PermissionError("database inaccessible")

    monkeypatch.setattr(Path, "is_file", inaccessible)
    assert startup_language(tmp_path) == "en"
