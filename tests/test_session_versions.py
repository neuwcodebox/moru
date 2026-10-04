import sqlite3

import pytest
from test_conversation import generate

from moru.api import Api
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.repository import Repository


def variant(app, image, prompt):
    job = app.generate_from_prompt(image.id, prompt)
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    return app.repository.get_image(app.get_job(job.id).image_id)


def test_regeneration_adds_a_version_without_a_new_conversation_turn_or_llm_call(app):
    project = app.create_project()
    root = generate(app, project.id)
    job = app.regenerate(root.id)
    assert job.turn_id == root.request_id
    assert (
        Api(app).get_project(project.id)["value"]["unfinished_requests"][0]["turn_id"]
        == job.turn_id
    )
    app.scheduler.run_next()
    rows = app.repository.conversation(project.id)
    assert len(rows) == 1
    request, selected, versions = rows[0]
    assert request.text == "소녀를 그려줘"
    assert selected.prompt == root.prompt
    assert [image.id for image in versions] == [root.id, selected.id]
    assert len(app.prompts.inputs) == 1
    assert selected.settings.seed is not None


def test_recent_context_uses_selected_versions_and_limits_the_number_of_requests(app):
    project = app.create_project()
    root = generate(app, project.id, "숲에서")
    revised = variant(app, root, "forest, moonlight")
    second = generate(app, project.id, "꽃도")
    third = generate(app, project.id, "노란 꽃")
    app.update_settings(app.get_settings(), PromptSettings(history_turns=2))
    generate(app, project.id, "아까 꽃을 다시")
    assert app.prompts.contexts[-1]["history"] == (
        PromptTurn("꽃도", second.prompt),
        PromptTurn("노란 꽃", third.prompt),
    )
    assert app.prompts.contexts[1]["history"] == (PromptTurn("숲에서", revised.prompt),)


def test_disabling_history_still_refines_the_selected_canonical_prompt(app):
    project = app.create_project()
    root = generate(app, project.id)
    app.update_settings(app.get_settings(), PromptSettings(history_turns=0))
    generate(app, project.id, "밤으로")
    assert app.prompts.contexts[-1]["history"] == ()
    assert app.prompts.inputs[-1] == ("refine", root.prompt, "밤으로")


def test_retry_uses_its_original_base_even_after_another_version_is_selected(app):
    project = app.create_project()
    root = generate(app, project.id)
    revised = variant(app, root, "new version")
    app.select_version(project.id, root.id)
    app.images.failures = ["GENERATION_FAILED"]
    job = app.submit_request(project.id, "밤으로")
    app.scheduler.run_next()
    app.select_version(project.id, revised.id)
    app.retry_request(job.request_id)
    app.scheduler.run_next()
    assert app.prompts.inputs[-1] == ("refine", root.prompt, "밤으로")
    assert app.prompts.contexts[-1]["history"] == (PromptTurn("소녀를 그려줘", root.prompt),)


def test_a_failed_version_preserves_the_selected_image_and_retries_in_the_same_turn(app):
    project = app.create_project()
    root = generate(app, project.id)
    app.images.failures = ["GENERATION_FAILED"]
    job = app.generate_from_prompt(root.id, "night")
    app.scheduler.run_next()
    assert app.repository.conversation(project.id)[0][1] == root
    retry = app.retry_request(job.request_id)
    assert retry.turn_id == root.request_id
    app.scheduler.run_next()
    assert len(app.repository.conversation(project.id)) == 1
    assert len(app.repository.conversation(project.id)[0][2]) == 2


def test_copying_through_a_later_turn_preserves_previous_version_choices_and_settings(app):
    project = app.create_project()
    root = generate(app, project.id, "숲")
    revised = variant(app, root, "moonlit forest")
    second = generate(app, project.id, "꽃")
    generate(app, project.id, "나비")
    app.select_version(project.id, root.id)
    copied = app.fork(project.id, second.id)
    turns = app.repository.conversation(copied.id)
    assert len(turns) == 2
    assert turns[0][1].prompt == root.prompt
    assert [image.prompt for image in turns[0][2]] == [root.prompt, revised.prompt]
    assert turns[1][1].settings == second.settings
    assert app.repository.get_project(copied.id).active_leaf_id == turns[1][1].id
    assert all(image.project_id == copied.id for _, _, versions in turns for image in versions)
    assert len(app.repository.conversation(project.id)) == 3


def test_failed_session_copy_rolls_back_the_new_session_and_current_project(tmp_path):
    from conftest import FakeImages, FakePrompts, ManualExecutor

    from moru.service import Application

    ids = iter(["project", "request", "job", "image", "copy", "request", "copied-image"])
    scheduler = ManualExecutor()
    app = Application(
        Repository(tmp_path / "test.db"),
        FakePrompts(),
        FakeImages(),
        tmp_path,
        executor=scheduler,
        new_id=lambda: next(ids),
    )
    try:
        project = app.create_project()
        job = app.submit_request(project.id, "forest")
        scheduler.run_next()
        with pytest.raises(MoruError) as failure:
            app.fork(project.id, app.get_job(job.id).image_id)
        assert failure.value.code == "DATABASE_FAILED"
        assert [item.id for item in app.repository.list_projects()] == [project.id]
        assert app.current_project().id == project.id
    finally:
        app.close()


def test_latest_schema_restores_selected_versions_without_migrating_records(app, tmp_path):
    project = app.create_project()
    root = generate(app, project.id)
    revised = variant(app, root, "moonlight")
    app.close()
    database = tmp_path / "anima.db"
    repository = Repository(database)
    try:
        request, selected, versions = repository.conversation(project.id)[0]
        assert request.id == root.request_id
        assert selected == revised
        assert versions == [root, revised]
        assert repository.get_image(root.id) == root
    finally:
        repository.close()


@pytest.mark.parametrize("value", [-1, 21, True, 1.5, "4"])
def test_invalid_history_counts_are_rejected(value):
    with pytest.raises(MoruError):
        PromptSettings(history_turns=value)


def test_incompatible_schema_fails_explicitly_without_rewriting_history(app, tmp_path):
    project = app.create_project()
    root = generate(app, project.id)
    app.close()
    database = tmp_path / "anima.db"
    with sqlite3.connect(database) as db:
        db.execute("ALTER TABLE requests DROP COLUMN turn_id")
    with pytest.raises(MoruError) as failure:
        Repository(database)
    assert failure.value.code == "DATABASE_FAILED"
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(requests)")}
        assert "turn_id" not in columns
        assert (
            db.execute("SELECT prompt FROM images WHERE id=?", (root.id,)).fetchone()[0]
            == root.prompt
        )
