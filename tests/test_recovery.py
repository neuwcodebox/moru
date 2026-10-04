from test_conversation import generate

from moru.domain import GenerationSettings
from moru.repository import Repository


def test_restart_recovers_current_project_path_fork_settings_and_all_branches(app, tmp_path):
    project = app.create_project()
    root = generate(app, project.id)
    first = generate(app, project.id)
    app.fork(project.id, root.id)
    sibling = generate(app, project.id)
    app.select_branch(project.id, first.id)
    app.fork(project.id, root.id)
    app.update_settings(GenerationSettings(seed=123))
    app.close()

    repository = Repository(tmp_path / "anima.db")
    try:
        assert repository.get_preference("current_project") == project.id
        assert repository.get_preference("settings")["seed"] == 123
        assert repository.active_path(project.id) == [root, first]
        assert repository.get_project(project.id).fork_image_id == root.id
        assert repository.children(project.id, root.id) == [first, sibling]
        assert repository.get_request(root.request_id).text == "소녀를 그려줘"
        assert not repository.get_image(root.id).image_path.startswith(str(tmp_path))
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
