from test_conversation import generate

from moru.domain import GenerationSettings


def test_refinement_uses_the_selected_model_and_preserves_the_original_record(app):
    project = app.create_project()
    original = generate(app, project.id)
    app.update_settings(GenerationSettings(model_id="anima-aesthetic-v1.1"))
    job = app.submit_request(project.id, "밤으로 바꿔줘")
    app.scheduler.run_next()

    assert app.prompts.contexts[-1]["model_id"] == "anima-aesthetic-v1.1"
    assert app.prompts.inputs[-1] == ("refine", original.prompt, "밤으로 바꿔줘")
    result = app.repository.get_image(app.get_job(job.id).image_id)
    assert result.settings.model_id == "anima-aesthetic-v1.1"
    assert (result.settings.steps, result.settings.cfg) == (40, 4.5)
    assert app.repository.get_image(original.id) == original


def test_regenerating_with_another_variant_keeps_the_prompt_and_bypasses_the_llm(app):
    project = app.create_project()
    original = generate(app, project.id)
    app.update_settings(GenerationSettings(model_id="anima-aesthetic-v1.1"))
    before = len(app.prompts.inputs)
    job = app.regenerate(original.id)
    app.scheduler.run_next()
    result = app.repository.get_image(app.get_job(job.id).image_id)
    assert len(app.prompts.inputs) == before
    assert result.prompt == original.prompt
    assert result.settings.model_id == "anima-aesthetic-v1.1"
    assert app.repository.image_turn(result.id) == app.repository.image_turn(original.id)


def test_retry_preserves_the_original_image_model_after_the_active_selection_changes(app):
    project = app.create_project()
    app.update_settings(GenerationSettings(model_id="anima-aesthetic-v1.1"))
    app.images.failures = ["GENERATION_FAILED"]
    failed = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    app.update_settings(GenerationSettings())
    retry = app.retry_request(failed.request_id)
    app.scheduler.run_next()
    assert app.get_job(retry.id).state == "completed"
    assert app.images.inputs[-1][1].model_id == "anima-aesthetic-v1.1"
