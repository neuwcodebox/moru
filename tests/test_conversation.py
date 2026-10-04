import pytest

from moru.domain import GenerationSettings
from moru.errors import MoruError


def generate(app, project_id, text="소녀를 그려줘"):
    job = app.submit_request(project_id, text)
    app.scheduler.run_next()
    result = app.get_job(job.id)
    assert result.state == "completed"
    return app.repository.get_image(result.image_id)


def test_first_request_creates_root_and_next_request_refines_its_actual_prompt(app):
    project = app.create_project()
    root = generate(app, project.id)
    child = generate(app, project.id, "밤으로 바꿔줘")

    assert root.parent_image_id is None
    assert child.parent_image_id == root.id
    assert app.prompts.inputs == [
        ("create", "소녀를 그려줘"),
        ("refine", root.prompt, "밤으로 바꿔줘"),
    ]
    assert app.repository.active_path(project.id) == [root, child]
    assert app.repository.get_request(child.request_id).base_image_id == root.id


def test_fork_copies_history_through_selected_image_into_an_independent_session(app):
    project = app.create_project()
    root = generate(app, project.id)
    original = generate(app, project.id, "밤으로")
    copied = app.fork(project.id, root.id)
    copied_root = app.repository.conversation(copied.id)[0][1]
    result = generate(app, copied.id, "비가 오게")

    assert copied.id != project.id
    assert app.current_project().id == copied.id
    assert copied_root.id != root.id
    assert copied_root.prompt == root.prompt
    assert copied_root.image_path == root.image_path
    assert result.parent_image_id == copied_root.id
    assert app.repository.active_path(project.id) == [root, original]
    assert len(app.repository.conversation(copied.id)) == 2
    assert app.prompts.inputs[-1] == ("refine", root.prompt, "비가 오게")


def test_forking_a_manual_version_preserves_its_original_request_text(app):
    project = app.create_project()
    root = generate(app, project.id)
    job = app.generate_from_prompt(root.id, "night sky")
    app.scheduler.run_next()
    selected = app.get_job(job.id).image_id
    copied = app.fork(project.id, selected)
    request, image, versions = app.repository.conversation(copied.id)[0]
    assert request.text == "소녀를 그려줘"
    assert image.prompt == "night sky"
    assert len(versions) == 1
    assert len(app.repository.conversation(project.id)[0][2]) == 2


def test_manual_prompt_fork_bypasses_llm_and_preserves_original_prompt(app):
    project = app.create_project()
    root = generate(app, project.id)
    job = app.generate_from_prompt(root.id, "manually edited entire prompt")
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(job.id).image_id)

    assert len(app.prompts.inputs) == 1
    assert image.prompt == "manually edited entire prompt"
    assert image.generation_method == "manual"
    assert image.parent_image_id == root.id
    assert app.repository.get_image(root.id) == root


def test_version_selection_preserves_later_turns_and_becomes_the_next_refinement_base(app):
    project = app.create_project()
    root = generate(app, project.id)
    job = app.generate_from_prompt(root.id, "changed sky")
    app.scheduler.run_next()
    variant = app.repository.get_image(app.get_job(job.id).image_id)
    later = generate(app, project.id, "꽃도 넣어줘")
    app.select_version(project.id, root.id)
    turns = app.repository.conversation(project.id)
    assert [turn[1] for turn in turns] == [root, later]
    assert turns[0][2] == [root, variant]
    result = generate(app, project.id, "처음 장면을 밤으로")
    assert result.parent_image_id == root.id
    assert app.prompts.inputs[-1] == ("refine", root.prompt, "처음 장면을 밤으로")


def test_new_project_starts_empty_without_deleting_old_work(app):
    previous = app.create_project()
    root = generate(app, previous.id)
    app.fork(previous.id, root.id)
    current = app.create_project()

    assert app.current_project() == current
    assert current.fork_image_id is None
    assert app.repository.active_path(current.id) == []
    assert app.repository.active_path(previous.id) == [root]
    assert generate(app, current.id).parent_image_id is None


def test_failed_request_can_retry_same_base_and_settings_without_damaging_tree(app):
    project = app.create_project()
    root = generate(app, project.id)
    app.images.failures = ["GENERATION_FAILED"]
    job = app.submit_request(project.id, "밤으로")
    app.scheduler.run_next()

    assert app.get_job(job.id).error_code == "GENERATION_FAILED"
    assert app.repository.active_path(project.id) == [root]
    app.update_settings(GenerationSettings(width=832, height=1216))
    retry = app.retry_request(job.request_id)
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(retry.id).image_id)
    assert image.request_id == job.request_id
    assert image.parent_image_id == root.id
    assert image.settings.width == 1024
    assert app.repository.unfinished_requests(project.id) == []


def test_auto_seed_is_resolved_only_at_generation_and_saved_with_the_image(app):
    project = app.create_project()
    job = app.submit_request(project.id, "風景")
    assert app.repository.get_request(job.request_id).settings.seed is None
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(job.id).image_id)
    assert image.settings.seed == 42
    assert app.get_settings().seed is None


def test_explicit_seed_and_settings_are_snapshotted_when_request_is_submitted(app):
    app.update_settings(GenerationSettings(seed=123, steps=8))
    project = app.create_project()
    job = app.submit_request(project.id, "風景")
    app.update_settings(GenerationSettings(seed=456, steps=20))
    app.scheduler.run_next()
    image = app.repository.get_image(app.get_job(job.id).image_id)
    assert image.settings.seed == 123
    assert image.settings.steps == 8


def test_fixed_seed_does_not_require_a_random_seed_source(tmp_path):
    from unittest.mock import Mock

    from conftest import FakeImages, FakePrompts, ManualExecutor

    from moru.repository import Repository
    from moru.service import Application

    executor = ManualExecutor()
    random_seed = Mock(side_effect=RuntimeError("random source unavailable"))
    application = Application(
        Repository(tmp_path / "test.db"),
        FakePrompts(),
        FakeImages(),
        tmp_path,
        executor=executor,
        new_seed=random_seed,
    )
    try:
        application.update_settings(GenerationSettings(seed=123))
        project = application.create_project()
        job = application.submit_request(project.id, "girl")
        executor.run_next()
        assert application.get_job(job.id).state == "completed"
        random_seed.assert_not_called()
    finally:
        application.close()


def test_an_existing_image_file_is_preserved_when_a_generated_id_collides(tmp_path):
    from conftest import FakeImages, FakePrompts, ManualExecutor

    from moru.repository import Repository
    from moru.service import Application

    executor = ManualExecutor()
    ids = iter(["project", "request", "job", "existing"])
    images = FakeImages()
    original = tmp_path / "images/existing.png"
    original.parent.mkdir()
    original.write_bytes(b"existing immutable image")
    application = Application(
        Repository(tmp_path / "test.db"),
        FakePrompts(),
        images,
        tmp_path,
        executor=executor,
        new_id=lambda: next(ids),
    )
    try:
        project = application.create_project()
        job = application.submit_request(project.id, "girl")
        executor.run_next()
        assert application.get_job(job.id).error_code == "IMAGE_SAVE_FAILED"
        assert original.read_bytes() == b"existing immutable image"
        assert images.inputs == []
    finally:
        application.close()


def test_cancelling_queued_generation_preserves_history_and_allows_retry(app):
    project = app.create_project()
    job = app.submit_request(project.id, "風景")
    app.cancel_job(job.id)
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "cancelled"
    assert app.repository.active_path(project.id) == []
    assert app.prompts.inputs == []
    retry = app.retry_request(job.request_id)
    app.scheduler.run_next()
    assert app.get_job(retry.id).state == "completed"


def test_oom_unloads_prompt_model_and_retries_image_with_identical_seed(app):
    project = app.create_project()
    app.images.failures = ["CUDA_OOM"]
    generate(app, project.id)
    assert app.prompts.unloads == 1
    assert len(app.images.inputs) == 2
    assert app.images.inputs[0] == app.images.inputs[1]


def test_repeated_oom_fails_explicitly_without_cpu_or_different_model_fallback(app):
    project = app.create_project()
    app.images.failures = ["CUDA_OOM", "CUDA_OOM"]
    job = app.submit_request(project.id, "風景")
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == "CUDA_OOM"
    assert app.repository.active_path(project.id) == []


def test_generations_and_branch_mutations_cannot_overlap(app):
    project = app.create_project()
    app.submit_request(project.id, "風景")
    with pytest.raises(MoruError, match="진행 중"):
        app.submit_request(project.id, "다른 이미지")
    with pytest.raises(MoruError, match="진행 중"):
        app.create_project()
    with pytest.raises(MoruError, match="진행 중"):
        app.fork(project.id, None)


def test_fork_cannot_cross_project_boundaries(app):
    project = app.create_project()
    image = generate(app, project.id)
    other = app.create_project()
    with pytest.raises(MoruError) as error:
        app.fork(other.id, image.id)
    assert error.value.code == "NOT_FOUND"


def test_closing_cancels_work_and_releases_engines_and_database(app):
    project = app.create_project()
    job = app.submit_request(project.id, "風景")
    app.close()
    assert app.get_job(job.id).state == "cancelled"
    assert app.images.closed
    assert app.prompts.unloads == 1
    with pytest.raises(MoruError) as error:
        app.create_project()
    assert error.value.code == "APP_CLOSED"
