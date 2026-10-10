import sqlite3

import pytest
from PIL import Image
from support.application import generate


def test_failed_database_commit_rolls_back_image_and_preserves_previous_branch(
    persistent_app, tmp_path,
):
    project = persistent_app.create_project()
    root = generate(persistent_app, project.id)
    with sqlite3.connect(tmp_path / "anima.db") as database:
        database.executescript("""
            CREATE TRIGGER simulated_disk_failure BEFORE UPDATE OF active_leaf_id ON projects
            BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END;
        """)
    job = persistent_app.submit_request(project.id, "밤으로")
    persistent_app.scheduler.run_next()
    assert persistent_app.get_job(job.id).error_code == "DATABASE_FAILED"
    assert persistent_app.repository.active_path(project.id) == [root]
    assert persistent_app.repository.children(project.id, root.id) == []
    assert persistent_app.repository.get_request(job.request_id).status == "failed"
    assert list((tmp_path / "images").glob("*.png")) == [tmp_path / root.image_path]


def test_corrupt_image_is_not_saved_as_a_successful_history_record(app, tmp_path):
    project = app.create_project()

    def corrupt_result(prompt, settings, path, progress, cancel):
        path.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")

    app.images.generate = corrupt_result
    job = app.submit_request(project.id, "風景")
    app.scheduler.run_next()
    assert app.get_job(job.id).error_code == "IMAGE_SAVE_FAILED"
    assert app.repository.active_path(project.id) == []
    assert list((tmp_path / "images").glob("*.png")) == []


@pytest.mark.parametrize("image_format, size", [("JPEG", (1024, 1024)), ("PNG", (64, 64))])
def test_wrong_image_format_or_dimensions_preserve_existing_history(
    app, tmp_path, image_format, size
):
    project = app.create_project()
    previous = generate(app, project.id)

    def wrong_result(prompt, settings, path, progress, cancel):
        Image.new("RGB", size).save(path, format=image_format)

    app.images.generate = wrong_result
    job = app.submit_request(project.id, "a new scene")
    app.scheduler.run_next()

    assert app.get_job(job.id).error_code == "IMAGE_SAVE_FAILED"
    assert app.repository.active_path(project.id) == [previous]
    assert list((tmp_path / "images").glob("*.png")) == [tmp_path / previous.image_path]
