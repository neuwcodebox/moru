from test_conversation import generate

from moru.domain import GenerationSettings
from moru.repository import Repository


def test_restart_recovers_copied_sessions_selected_versions_and_settings(app, tmp_path):
    project = app.create_project()
    root = generate(app, project.id)
    job = app.generate_from_prompt(root.id, "manual version")
    app.scheduler.run_next()
    variant = app.get_job(job.id).image_id
    app.select_version(project.id, root.id)
    copied = app.fork(project.id, root.id)
    app.update_settings(GenerationSettings(seed=123))
    app.close()

    repository = Repository(tmp_path / "anima.db")
    try:
        assert repository.get_preference("current_project") == copied.id
        assert repository.get_preference("settings")["seed"] == 123
        original = repository.conversation(project.id)[0]
        assert original[1] == root
        assert [image.id for image in original[2]] == [root.id, variant]
        duplicate = repository.conversation(copied.id)[0]
        assert duplicate[0].text == "소녀를 그려줘"
        assert duplicate[1].image_path == root.image_path
        assert duplicate[1].id != root.id
        assert len(duplicate[2]) == 1
    finally:
        repository.close()


def test_interrupted_requests_become_retryable_on_restart(app, tmp_path):
    project = app.create_project()
    job = app.submit_request(project.id, "風景")
    # A second connection simulates opening the DB after an abrupt process termination.
    repository = Repository(tmp_path / "anima.db")
    try:
        request = repository.get_request(job.request_id)
        assert request.status == "failed"
        assert request.error_code == "GENERATION_INTERRUPTED"
        assert repository.active_path(project.id) == []
    finally:
        repository.close()
