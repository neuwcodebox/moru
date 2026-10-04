import pytest
from test_conversation import generate

from moru.api import Api
from moru.domain import GenerationSettings, PromptSettings


def test_main_conversation_view_hides_prompt_and_generation_metadata(app):
    api = Api(app)
    project = app.create_project()
    image = generate(app, project.id)
    view = api.get_project(project.id)["value"]["images"][0]
    assert view["request_text"] == "소녀를 그려줘"
    assert "prompt" not in view
    assert "settings" not in view
    assert "image_path" not in view
    details = api.get_image_details(image.id)["value"]
    assert details["prompt"] == image.prompt
    assert details["settings"]["seed"] == "42"


def test_live_prompt_is_available_during_generation_but_thinking_is_never_saved(app):
    api = Api(app)
    snapshots = []
    project = app.create_project()
    app.update_settings(app.get_settings(), PromptSettings(thinking=True))

    def create(text, settings, cancelled, progress):
        progress("choosing a scene", "")
        snapshots.append(api.get_job(job.id)["value"])
        progress("choosing a scene", "night, girl")
        snapshots.append(api.get_job(job.id)["value"])
        return "night, girl"

    app.prompts.create = create
    job = app.submit_request(project.id, "girl")
    app.scheduler.run_next()
    assert snapshots[0]["thinking_text"] == "choosing a scene"
    assert snapshots[0]["prompt_text"] == ""
    assert snapshots[0]["thinking_enabled"] is True
    assert snapshots[1]["prompt_text"] == "night, girl"
    completed = api.get_job(job.id)["value"]
    assert completed["thinking_text"] == completed["prompt_text"] == ""
    assert api.get_image_details(completed["image_id"])["value"]["prompt"] == "night, girl"


def test_manual_prompt_stays_in_details_instead_of_appearing_as_user_chat(app):
    api = Api(app)
    project = app.create_project()
    image = generate(app, project.id)
    app.generate_from_prompt(image.id, "private manual prompt")
    app.scheduler.run_next()
    view = api.get_project(project.id)["value"]
    assert view["images"][-1]["request_text"] is None


def test_bridge_preserves_large_seeds_without_javascript_precision_loss(app):
    api = Api(app)
    seed = str(2**63 - 1)
    result = api.update_settings({"seed": seed})
    assert result["ok"]
    assert result["value"]["seed"] == seed
    assert app.get_settings().seed == 2**63 - 1


def test_invalid_bridge_settings_have_stable_korean_error(app):
    api = Api(app)
    result = api.update_settings({"unknown": 1})
    assert result == {
        "ok": False,
        "error": {
            "code": "INVALID_SETTINGS",
            "message": "생성 설정을 확인해 주세요.",
        },
    }


def test_bootstrap_exposes_prompt_defaults_and_restores_saved_values(app):
    api = Api(app)
    assert api.bootstrap()["value"]["prompt_settings"] == {
        "context_size": 2048,
        "max_tokens": 1024,
        "thinking": False,
    }
    values = {"context_size": 4096, "max_tokens": 2048, "thinking": False}
    assert api.update_settings({"steps": 12}, values)["ok"]
    assert api.get_prompt_settings()["value"] == values
    assert api.bootstrap()["value"]["prompt_settings"] == values


@pytest.mark.parametrize(
    "values",
    [
        {"max_tokens": 8192},
        {"thinking": "false"},
        {"unknown": 1},
        [],
    ],
)
def test_invalid_prompt_settings_do_not_partially_save_image_settings(app, values):
    result = Api(app).update_settings({"steps": 12}, values)
    assert result["error"]["code"] == "INVALID_SETTINGS"
    assert app.get_settings() == GenerationSettings()
    assert app.get_prompt_settings() == PromptSettings()


def test_images_are_supplied_without_exposing_local_paths_or_running_a_server(app):
    project = app.create_project()
    image = generate(app, project.id)
    source = Api(app).get_image_source(image.id)
    assert source["ok"]
    assert source["value"].startswith("data:image/png;base64,")


def test_failed_requests_from_another_branch_are_not_shown_in_selected_conversation(app):
    project = app.create_project()
    root = generate(app, project.id)
    app.images.failures = ["GENERATION_FAILED"]
    job = app.submit_request(project.id, "실패한 밤 장면")
    app.scheduler.run_next()
    assert (
        Api(app).get_project(project.id)["value"]["unfinished_requests"][0]["id"] == job.request_id
    )
    latest = generate(app, project.id, "성공한 낮 장면")
    assert latest.parent_image_id == root.id
    assert Api(app).get_project(project.id)["value"]["unfinished_requests"] == []
    assert app.repository.get_request(job.request_id).status == "failed"


def test_prompt_copy_uses_native_clipboard_without_changing_image_history(app):
    copied = []
    api = Api(app, copy_to_clipboard=copied.append)
    result = api.copy_prompt("은발 소녀, 밤, rain")
    assert result["ok"]
    assert copied == ["은발 소녀, 밤, rain"]


def test_clipboard_failure_has_a_specific_error_and_does_not_expose_content(app):
    def unavailable(text):
        raise RuntimeError(text)

    result = Api(app, copy_to_clipboard=unavailable).copy_prompt("private prompt")
    assert not result["ok"]
    assert result["error"]["code"] == "CLIPBOARD_FAILED"
    assert "private prompt" not in result["error"]["message"]
