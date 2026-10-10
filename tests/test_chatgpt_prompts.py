from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest
from support.chatgpt import SETTINGS, Auth, StreamHttp, delta

from moru.chatgpt.http import ChatGPTHttpError, sse_events
from moru.chatgpt.instructions import prompt_messages
from moru.chatgpt.prompts import ChatGPTPrompts
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.prompts.providers import PromptProviders


@pytest.mark.parametrize("operation", ["create", "refine"])
def test_gpt_reasoning_effort_does_not_use_local_reasoning_budget(operation):
    http = StreamHttp([delta(), {"type": "response.completed"}])
    settings = replace(SETTINGS, chatgpt_model="gpt-5.4", chatgpt_reasoning_effort="high",
                       reasoning_level="low", thinking=False)
    prompts = ChatGPTPrompts(Auth(), http)
    args = ("girl", settings, Event(), lambda *_: None)
    prompts.create(*args) if operation == "create" else prompts.refine("original scene", *args)
    assert len(http.calls) == 1
    assert http.calls[0][1]["reasoning"] == {"effort": "high"}


def test_unsupported_reasoning_does_not_start_an_inference_request():
    http = StreamHttp([])
    with pytest.raises(MoruError) as error:
        ChatGPTPrompts(Auth(), http).create(
            "girl", replace(SETTINGS, chatgpt_reasoning_effort="high"), Event(), lambda *_: None,
        )
    assert error.value.code == "CHATGPT_UNSUPPORTED"
    assert http.calls == []


def test_chatgpt_streams_prompt_with_short_guidance_and_supported_fields_only():
    http = StreamHttp([delta(), {"type": "response.completed"}])
    progress = []
    result = ChatGPTPrompts(Auth(), http).create(
        "girl", SETTINGS, Event(), lambda *p: progress.append(p)
    )
    assert result == "1girl, silver hair, moonlight"
    assert progress == [("", result)]
    token, payload = http.calls[0]
    assert token == "access"
    assert set(payload) == {"model", "instructions", "input", "store", "stream"}
    assert payload["model"] == "account-model"
    assert payload["store"] is False and payload["stream"] is True
    assert "Danbooru" in payload["instructions"]
    assert len(payload["instructions"]) < 1500
    assert all(item["role"] != "system" for item in payload["input"])
    assert http.closed


def test_cloud_refinement_preserves_canonical_prompt_and_selected_history():
    http = StreamHttp([delta(), {"type": "response.completed"}])
    ChatGPTPrompts(Auth(), http).refine(
        "original scene",
        "change lighting",
        SETTINGS,
        Event(),
        lambda *_: None,
        history=(PromptTurn("girl", "first scene"),),
    )
    messages = http.calls[0][1]["input"]
    assert messages[:2] == [
        {"role": "user", "content": "girl"},
        {"role": "assistant", "content": "first scene"},
    ]
    assert (
        messages[-1]["content"]
        == "Existing image prompt:\noriginal scene\n\nChange request:\nchange lighting"
    )


def test_flux_cloud_guidance_uses_sentences_without_tag_reference():
    instructions, _ = prompt_messages("scene", model_id="flux2-klein-4b")
    assert "natural language" in instructions
    assert "Danbooru" not in instructions


def test_account_model_catalog_filters_hidden_models_and_preserves_server_order():
    from types import SimpleNamespace

    calls = []

    def catalog(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "models": [
                {"slug": "second", "display_name": "Second", "visibility": "list"},
                {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
                {"slug": "first", "display_name": "First", "visibility": "list"},
            ]
        }

    prompts = ChatGPTPrompts(Auth(), SimpleNamespace(json=catalog))
    assert prompts.models() == [
        {"slug": "second", "display_name": "Second"},
        {"slug": "first", "display_name": "First"},
    ]
    assert calls == [("https://api.openai.com/v1/models", {"token": "access"})]


@pytest.mark.parametrize(
    "events,code",
    [
        ([delta()], "PROMPT_RESPONSE_INTERRUPTED"),
        ([delta(), {"type": "response.incomplete"}], "PROMPT_RESPONSE_INTERRUPTED"),
        ([{"type": "response.refusal.delta", "delta": "refused"}], "CHATGPT_REFUSED"),
        ([{"type": "response.completed"}], "PROMPT_EMPTY_RESPONSE"),
        ([delta("소녀"), {"type": "response.completed"}], "PROMPT_NON_ENGLISH_RESPONSE"),
        (
            [
                delta(),
                {
                    "type": "response.failed",
                    "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
                },
            ],
            "CHATGPT_USAGE_LIMIT",
        ),
        (
            [
                delta(),
                {
                    "type": "response.completed",
                    "response": {
                        "output": [{"content": [{"type": "refusal", "refusal": "blocked"}]}]
                    },
                },
            ],
            "CHATGPT_REFUSED",
        ),
    ],
)
def test_incomplete_failed_refused_or_invalid_output_never_becomes_an_image_prompt(events, code):
    http = StreamHttp(events)
    with pytest.raises(MoruError) as error:
        ChatGPTPrompts(Auth(), http).create("scene", SETTINGS, Event(), lambda *_: None)
    assert error.value.code == code
    assert http.closed
    assert len(http.calls) == 1


def test_cancelling_during_a_delta_closes_stream_and_discards_partial_prompt():
    http = StreamHttp([delta(), {"type": "response.completed"}])
    cancelled = Event()
    with pytest.raises(MoruError) as error:
        ChatGPTPrompts(Auth(), http).create(
            "scene", SETTINGS, cancelled, lambda *_: cancelled.set()
        )
    assert error.value.code == "GENERATION_CANCELLED"
    assert http.closed


def test_admission_401_refreshes_once_without_replaying_partial_output():
    http = StreamHttp(ChatGPTHttpError(401))
    auth = Auth()
    with pytest.raises(MoruError):
        ChatGPTPrompts(auth, http).create("scene", SETTINGS, Event(), lambda *_: None)
    assert auth.refreshes == [None, "access"]
    assert [token for token, _ in http.calls] == ["access", "renewed"]


def test_sse_comments_and_multiline_data_are_decoded_and_done_is_ignored():
    stream = BytesIO(b': ping\n\ndata: {"type":\ndata: "response.completed"}\n\ndata: [DONE]\n\n')
    assert list(sse_events(stream, Event())) == [{"type": "response.completed"}]


def test_provider_is_fixed_at_acceptance_and_cloud_does_not_reserve_vram(app):
    from support.application import FakePrompts

    local = app.prompts
    cloud = FakePrompts()
    app.prompts = PromptProviders(local, cloud)
    app.update_settings(app.get_settings(), SETTINGS)
    project = app.create_project()
    job = app.submit_request(project.id, "girl")
    app.update_settings(app.get_settings(), PromptSettings())
    app.scheduler.run_next()
    assert cloud.inputs == [("create", "girl")]
    assert local.inputs == []
    assert local.unloads == 1
    assert app.images.reservations == []
    assert job.thinking_enabled is False
    app.submit_request(project.id, "night")
    app.scheduler.run_next()
    assert local.inputs[0][0] == "refine"
    assert local.contexts[0]["history"][0].text == "girl"


@pytest.mark.parametrize("provider", ["local", "chatgpt"])
@pytest.mark.parametrize("operation", ["create", "refine"])
def test_chosen_provider_receives_history_image_model_and_readiness_callback(provider, operation):
    from support.application import FakePrompts

    local, cloud = FakePrompts(), FakePrompts()
    prompts = PromptProviders(local, cloud)
    settings = PromptSettings(provider=provider, chatgpt_model="account-model")
    history = (PromptTurn("girl", "silver hair"),)
    ready = []
    context = {
        "history": history,
        "model_id": "flux2-klein-4b",
        "on_ready": lambda: ready.append(True),
    }

    if operation == "create":
        result = prompts.create("scene", settings, Event(), lambda *_: None, **context)
        assert result == "silver-haired girl, daytime"
        expected_input = ("create", "scene")
    else:
        result = prompts.refine("original", "night", settings, Event(), lambda *_: None, **context)
        assert result == "silver-haired girl, nighttime"
        expected_input = ("refine", "original", "night")

    chosen, other = (cloud, local) if provider == "chatgpt" else (local, cloud)
    assert chosen.inputs == [expected_input]
    assert chosen.settings == [settings]
    assert chosen.contexts == [{"history": history, "model_id": "flux2-klein-4b"}]
    assert ready == [True]
    assert other.inputs == []


def test_chatgpt_refusal_fails_job_without_falling_back_to_local_or_rendering(app):
    local = app.prompts
    app.prompts = PromptProviders(
        local,
        ChatGPTPrompts(
            Auth(),
            StreamHttp(
                [
                    {"type": "response.refusal.delta"},
                ]
            ),
        ),
    )
    app.update_settings(app.get_settings(), SETTINGS)
    job = app.submit_request(app.create_project().id, "scene")
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == "CHATGPT_REFUSED"
    assert app.images.inputs == [] and local.inputs == []


@pytest.mark.parametrize("remote_code", ["unsupported_parameter", "unsupported_value"])
def test_api_rejected_reasoning_fails_explicitly_without_retry_or_changed_effort(remote_code):
    http = StreamHttp(ChatGPTHttpError(400, remote_code))
    settings = replace(SETTINGS, chatgpt_model="gpt-5.4", chatgpt_reasoning_effort="high")
    with pytest.raises(MoruError) as error:
        ChatGPTPrompts(Auth(), http).create("girl", settings, Event(), lambda *_: None)
    assert error.value.code == "CHATGPT_UNSUPPORTED"
    assert len(http.calls) == 1
    assert http.calls[0][1]["reasoning"] == {"effort": "high"}
