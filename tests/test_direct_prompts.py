import pytest
from support.application import FakePrompts, generate

from moru.domain import GenerationSettings, PromptSettings
from moru.errors import MoruError
from moru.prompts.providers import PromptProviders


@pytest.mark.parametrize("model_id", ["anima-turbo-v1.1", "flux2-klein-4b"])
def test_direct_input_preserves_complete_prompts_for_create_followup_and_fork(app, model_id):
    local, cloud = app.prompts, FakePrompts()
    app.prompts = PromptProviders(local, cloud)
    app.update_settings(
        GenerationSettings(model_id=model_id, width=64, height=64),
        PromptSettings(provider="direct"),
    )
    project = app.create_project()
    first_text = "  1girl,  silver_hair\n한글 원문, (daylight:1.2)  "
    expected_prompt = "1girl,  silver_hair\n한글 원문, (daylight:1.2)"
    first = generate(app, project.id, first_text)
    followup = generate(app, project.id, "blue sky")
    fork = app.fork(project.id, first.id)
    forked = generate(app, fork.id, "red sky")

    assert [first.prompt, followup.prompt, forked.prompt] == [
        expected_prompt, "blue sky", "red sky",
    ]
    assert app.repository.get_request(first.request_id).text == expected_prompt
    assert len(app.repository.conversation(project.id)) == 2
    assert followup.parent_image_id == first.id
    assert local.inputs == cloud.inputs == []
    assert [prompt for prompt, _ in app.images.inputs] == [expected_prompt, "blue sky", "red sky"]
    assert first.sources == followup.sources == forked.sources == ()
    assert app.images.reservations == []
    assert local.unloads >= 3


def test_direct_input_is_fixed_when_job_is_accepted(app):
    app.update_settings(GenerationSettings(width=64, height=64), PromptSettings(provider="direct"))
    job = app.submit_request(app.create_project().id, "unchanged prompt")
    app.update_settings(app.get_settings(), PromptSettings())
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert app.images.inputs[0][0] == "unchanged prompt"
    assert app.prompts.inputs == []
    assert job.thinking_enabled is False


def test_cancelled_direct_input_never_starts_image_generation(app):
    app.update_settings(app.get_settings(), PromptSettings(provider="direct"))
    job = app.submit_request(app.create_project().id, "scene")
    app.cancel_job(job.id)
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "cancelled"
    assert app.images.inputs == []


def test_regenerating_direct_input_preserves_prompt_and_conversation_turn(app):
    app.update_settings(GenerationSettings(width=64, height=64), PromptSettings(provider="direct"))
    project = app.create_project()
    original = generate(app, project.id, "  1girl, silver_hair\n(daylight:1.2)  ")
    job = app.regenerate(original.id)
    app.scheduler.run_next()
    repeated = app.repository.get_image(app.get_job(job.id).image_id)
    assert repeated.prompt == original.prompt
    rows = app.repository.conversation(project.id)
    assert len(rows) == 1
    assert [image.id for image in rows[0][2]] == [original.id, repeated.id]
    assert app.prompts.inputs == []


def test_direct_input_retries_original_text_after_image_failure(app):
    app.update_settings(GenerationSettings(width=64, height=64), PromptSettings(provider="direct"))
    app.images.failures = ["MODEL_LOAD_FAILED"]
    job = app.submit_request(app.create_project().id, "  original\nprompt  ")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "failed"
    retry = app.retry_request(job.request_id)
    app.scheduler.run_next()
    assert app.get_job(retry.id).state == "completed"
    assert app.images.inputs[-1][0] == "original\nprompt"
    assert app.prompts.inputs == []


def test_direct_input_selection_survives_restart(make_app, tmp_path):
    database = tmp_path / "direct.db"
    original = make_app(database=database)
    original.update_settings(original.get_settings(), PromptSettings(provider="direct"))
    original.close()
    restored = make_app(database=database)
    assert restored.get_prompt_settings().provider == "direct"


def test_direct_input_requires_a_prompt_writer_for_region_edits(app):
    app.update_settings(GenerationSettings(width=64, height=64), PromptSettings(provider="direct"))
    project = app.create_project()
    image = generate(app, project.id, "scene")
    with pytest.raises(MoruError) as error:
        app.edit_region(image.id, "blue cup", "unused mask")
    assert error.value.code == "REGION_PROMPT_WRITER_REQUIRED"
    assert app.repository.unfinished_requests(project.id) == []
