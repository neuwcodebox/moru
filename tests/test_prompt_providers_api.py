from dataclasses import asdict

import pytest

from moru.api import Api
from moru.config import ModelPaths
from moru.domain import PromptSettings
from moru.errors import MoruError


class Account:
    def __init__(self, connected=True, plan_enabled=True, waiting=False):
        self.connected, self.plan_enabled = connected, plan_enabled
        self.waiting = waiting
        self.logouts = 0

    def status(self):
        return {
            "connected": self.connected,
            "plan_enabled": self.plan_enabled,
            "login_state": "waiting" if self.waiting else "idle",
        }

    def logout(self):
        self.logouts += 1
        self.connected = False
        return self.status()


def test_chatgpt_only_settings_do_not_require_a_local_model(app, tmp_path):
    api = Api(app, ModelPaths(tmp_path), chatgpt_auth=Account())
    prompt = PromptSettings(
        provider="chatgpt", chatgpt_model="account-model", tag_search_enabled=False
    )
    assert api.update_settings({}, asdict(prompt))["ok"] is True
    assert app.get_prompt_settings() == prompt
    assert not ModelPaths(tmp_path).get("prompt").exists()


@pytest.mark.parametrize(
    "account,code",
    [
        (Account(connected=False), "CHATGPT_SIGN_IN_REQUIRED"),
        (Account(plan_enabled=False), "CHATGPT_NOT_ELIGIBLE"),
    ],
)
def test_unavailable_chatgpt_cannot_partially_save_settings(app, account, code):
    api = Api(app, chatgpt_auth=account)
    before = app.get_settings()
    result = api.update_settings(
        {"steps": 33},
        asdict(
            PromptSettings(
                provider="chatgpt",
                chatgpt_model="model",
            )
        ),
    )
    assert result["error"]["code"] == code
    assert app.get_settings() == before
    assert app.get_prompt_settings() == PromptSettings()


def test_neither_provider_prepared_cannot_save_local_as_ready(app, tmp_path):
    result = Api(app, ModelPaths(tmp_path)).update_settings({}, asdict(PromptSettings()))
    assert result["error"]["code"] == "PROMPT_MODEL_NOT_FOUND"


def test_preparing_chatgpt_model_does_not_activate_it_or_require_local_files(app, tmp_path):
    api = Api(app, ModelPaths(tmp_path), chatgpt_auth=Account())
    before = app.get_settings()
    result = api.configure_prompt_writer({"chatgpt_model": "prepared-model"})
    assert result["ok"] is True
    assert app.get_prompt_settings() == PromptSettings(chatgpt_model="prepared-model")
    assert app.get_settings() == before
    assert api.select_prompt_provider("chatgpt")["ok"] is True


def test_preparing_local_options_preserves_active_chatgpt_and_image_settings(app):
    app.update_settings(app.get_settings(), PromptSettings(provider="chatgpt", chatgpt_model="gpt"))
    before = app.get_settings()
    result = Api(app).configure_prompt_writer({"context_size": 8192, "history_turns": 6})
    assert result["value"]["provider"] == "chatgpt"
    assert app.get_prompt_settings() == PromptSettings(
        provider="chatgpt", chatgpt_model="gpt", context_size=8192, history_turns=6
    )
    assert app.get_settings() == before


@pytest.mark.parametrize(
    "values", [[], {"provider": "chatgpt"}, {"unknown": 1}, {"max_tokens": 8192}]
)
def test_invalid_preparation_cannot_partially_save_settings(app, values):
    before = app.get_prompt_settings()
    result = Api(app).configure_prompt_writer(values)
    assert result["error"]["code"] == "INVALID_SETTINGS"
    assert app.get_prompt_settings() == before


def test_switching_both_configured_providers_preserves_model_and_generation_settings(app, tmp_path):
    paths = ModelPaths(tmp_path)
    paths.get("prompt").parent.mkdir(parents=True)
    paths.get("prompt").write_bytes(b"local model")
    api = Api(app, paths, chatgpt_auth=Account())
    app.update_settings(
        app.get_settings(), PromptSettings(chatgpt_model="chosen", tag_search_enabled=False)
    )
    before = app.get_settings()
    assert api.select_prompt_provider("chatgpt")["value"]["chatgpt_model"] == "chosen"
    assert api.select_prompt_provider("local")["value"]["provider"] == "local"
    assert app.get_prompt_settings().tag_search_enabled is False
    assert app.get_settings() == before


def test_account_and_provider_cannot_switch_during_an_accepted_job(app):
    account = Account()
    api = Api(app, chatgpt_auth=account)
    app.update_settings(app.get_settings(), PromptSettings(chatgpt_model="chosen"))
    app.submit_request(app.create_project().id, "scene")
    assert api.select_prompt_provider("chatgpt")["error"]["code"] == "GENERATION_BUSY"
    result = api.configure_prompt_writer({"chatgpt_model": "other"})
    assert result["error"]["code"] == "GENERATION_BUSY"
    assert api.logout_chatgpt()["error"]["code"] == "GENERATION_BUSY"
    assert account.logouts == 0


def test_chatgpt_generation_waits_until_pending_account_login_finishes(app):
    api = Api(app, chatgpt_auth=Account(waiting=True))
    app.update_settings(
        app.get_settings(), PromptSettings(provider="chatgpt", chatgpt_model="model")
    )
    project = app.create_project()
    assert api.submit_request(project.id, "scene")["error"]["code"] == "GENERATION_BUSY"
    assert app.repository.unfinished_requests(project.id) == []


@pytest.mark.parametrize(
    "values",
    [
        {"provider": "other"},
        {"provider": []},
        {"provider": "chatgpt"},
        {"chatgpt_model": []},
        {"chatgpt_model": "x" * 201},
    ],
)
def test_invalid_provider_and_model_settings_are_rejected(values):
    with pytest.raises(MoruError) as error:
        PromptSettings(**values)
    assert error.value.code == "INVALID_SETTINGS"
