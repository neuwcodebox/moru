import pytest
from support.application import generate

from moru.domain import GenerationSettings


@pytest.mark.parametrize("model_id,defaults", [
    ("anima-aesthetic-v1.1", (40, 4.5)), ("flux2-klein-4b", (4, 1)),
])
def test_refinement_uses_the_selected_model_and_preserves_the_original_record(
    app, model_id, defaults,
):
    project = app.create_project()
    original = generate(app, project.id)
    app.update_settings(GenerationSettings(model_id=model_id))
    job = app.submit_request(project.id, "밤으로 바꿔줘")
    app.scheduler.run_next()

    assert app.prompts.contexts[-1]["model_id"] == model_id
    assert app.prompts.inputs[-1] == ("refine", original.prompt, "밤으로 바꿔줘")
    result = app.repository.get_image(app.get_job(job.id).image_id)
    assert result.settings.model_id == model_id
    assert (result.settings.steps, result.settings.cfg) == defaults
    assert app.repository.get_image(original.id) == original


@pytest.mark.parametrize("model_id", ["anima-aesthetic-v1.1", "flux2-klein-4b"])
def test_regenerating_with_another_variant_keeps_the_prompt_and_bypasses_the_llm(app, model_id):
    project = app.create_project()
    original = generate(app, project.id)
    app.update_settings(GenerationSettings(model_id=model_id))
    before = len(app.prompts.inputs)
    job = app.regenerate(original.id)
    app.scheduler.run_next()
    result = app.repository.get_image(app.get_job(job.id).image_id)
    assert len(app.prompts.inputs) == before
    assert result.prompt == original.prompt
    assert result.settings.model_id == model_id
    assert app.repository.image_turn(result.id) == app.repository.image_turn(original.id)


@pytest.mark.parametrize("model_id", ["anima-aesthetic-v1.1", "flux2-klein-4b"])
def test_retry_preserves_the_original_image_model_after_the_active_selection_changes(app, model_id):
    project = app.create_project()
    app.update_settings(GenerationSettings(model_id=model_id))
    app.images.failures = ["GENERATION_FAILED"]
    failed = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    app.update_settings(GenerationSettings())
    retry = app.retry_request(failed.request_id)
    app.scheduler.run_next()
    assert app.get_job(retry.id).state == "completed"
    assert app.images.inputs[-1][1].model_id == model_id
