from dataclasses import asdict
from types import SimpleNamespace

import pytest

from moru.api import Api
from moru.chatgpt.options import reasoning_efforts, validate_chatgpt_options
from moru.domain import PromptSettings
from moru.errors import MoruError


def test_existing_settings_keep_cloud_defaults_without_changing_local_reasoning():
    settings = PromptSettings(reasoning_level="high")
    assert settings.chatgpt_reasoning_effort == "default"
    assert settings.thinking_budget == 1408


@pytest.mark.parametrize("field,value", [
    ("chatgpt_reasoning_effort", "ultra"), ("chatgpt_reasoning_effort", []),
])
def test_invalid_cloud_options_are_rejected(field, value):
    with pytest.raises(MoruError, match="설정") as error:
        PromptSettings(**{field: value})
    assert error.value.code == "INVALID_SETTINGS"


@pytest.mark.parametrize("model,expected", [
    ("gpt-6-astra", ("low", "medium", "high", "xhigh", "max")),
    ("gpt-6.1-sol", ("low", "medium", "high", "xhigh", "max")),
    ("gpt-6-sol", ("none", "low", "medium", "high", "xhigh", "max")),
    ("gpt-6-luna", ("none", "low", "medium", "high", "xhigh", "max")),
    ("gpt-5.4-2026-03-05", ("none", "low", "medium", "high", "xhigh")),
    ("gpt-5.5", ("none", "low", "medium", "high", "xhigh")),
    ("o3", ("low", "medium", "high")),
    ("gpt-4.1", ()), ("gpt-6-astra-unknown", ()), ("account-model", ()),
])
def test_reasoning_choices_follow_documented_model_support(model, expected):
    assert reasoning_efforts(model) == expected


def test_unsupported_effort_fails_instead_of_silently_using_a_default():
    with pytest.raises(MoruError) as error:
        validate_chatgpt_options(PromptSettings(
            chatgpt_model="gpt-6-astra", chatgpt_reasoning_effort="none",
        ))
    assert error.value.code == "CHATGPT_UNSUPPORTED"


def test_cloud_preferences_round_trip_independently_of_local_options(app):
    settings = PromptSettings(
        reasoning_level="low", chatgpt_reasoning_effort="high",
    )
    app.update_settings(app.get_settings(), settings)
    assert PromptSettings(**app.repository.get_preference("prompt_settings")) == settings
    assert asdict(settings)["reasoning_level"] == "low"


def test_reasoning_choices_are_available_without_credentials_or_network(app):
    api = Api(app)
    assert api.get_chatgpt_reasoning_efforts("gpt-5.4")["value"] == (
        "none", "low", "medium", "high", "xhigh",
    )
    assert api.get_chatgpt_reasoning_efforts([])["error"]["code"] == "INVALID_SETTINGS"


def test_unsupported_cloud_effort_does_not_partially_save_image_or_prompt_settings(app):
    original_image, original_prompt = app.get_settings(), app.get_prompt_settings()
    api = Api(app, chatgpt_auth=SimpleNamespace(status=lambda: {
        "connected": True, "plan_enabled": True, "login_state": "idle",
    }))
    prompt = PromptSettings(provider="chatgpt", chatgpt_model="gpt-6-astra",
                            chatgpt_reasoning_effort="none")
    result = api.update_settings({"steps": 15}, asdict(prompt))
    assert result["error"]["code"] == "CHATGPT_UNSUPPORTED"
    assert app.get_settings() == original_image
    assert app.get_prompt_settings() == original_prompt
