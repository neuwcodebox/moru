import json
import sqlite3
from dataclasses import replace

import pytest
from support.application import FakePrompts, generate

from moru.api import Api
from moru.domain import PromptSource
from moru.repository import Repository

SOURCE = PromptSource(
    "get_tag_info",
    "gray_hair",
    json.dumps(
        {
            "name": "grey_hair",
            "description": "Grey-colored hair.",
        }
    ),
)


class ReferencingPrompts(FakePrompts):
    def create(self, *args, on_source=None, **context):
        if on_source is not None:
            on_source(SOURCE)
        return super().create(*args, **context)

    def refine(self, *args, on_source=None, **context):
        if on_source is not None:
            on_source(SOURCE)
        return super().refine(*args, **context)


@pytest.mark.parametrize("operation", ["create", "refine"])
def test_reference_information_is_saved_with_the_generated_image_and_exposed_by_api(app, operation):
    app.prompts = ReferencingPrompts()
    project = app.create_project()
    image = generate(app, project.id)
    if operation == "refine":
        image = generate(app, project.id, "night")
    assert image.sources == (SOURCE,)
    assert Api(app).get_image_sources(image.id) == {
        "ok": True,
        "value": [
            {
                "tool": "get_tag_info",
                "query": "gray_hair",
                "result": {"name": "grey_hair", "description": "Grey-colored hair."},
            }
        ],
    }


def test_sources_survive_repository_reopening_and_session_forks(persistent_app):
    persistent_app.prompts = ReferencingPrompts()
    project = persistent_app.create_project()
    image = generate(persistent_app, project.id)
    fork = persistent_app.fork(project.id, image.id)
    copied = persistent_app.repository.get_image(fork.active_leaf_id)
    assert copied.id != image.id and copied.sources == image.sources
    path = persistent_app.data_dir / "anima.db"
    persistent_app.repository.close()
    persistent_app.repository = Repository(path)
    assert persistent_app.repository.get_image(image.id).sources == (SOURCE,)
    assert persistent_app.repository.get_image(copied.id).sources == (SOURCE,)


def test_regeneration_preserves_references_for_the_same_prompt_and_edits_start_without_them(app):
    app.prompts = ReferencingPrompts()
    project = app.create_project()
    original = generate(app, project.id)
    job = app.regenerate(original.id)
    app.scheduler.run_next()
    regenerated = app.repository.get_image(app.get_job(job.id).image_id)
    assert regenerated.sources == original.sources
    job = app.generate_from_prompt(original.id, "different hand-written prompt")
    app.scheduler.run_next()
    edited = app.repository.get_image(app.get_job(job.id).image_id)
    assert edited.sources == ()
    assert app.repository.get_image(original.id).sources == (SOURCE,)


def test_new_images_and_old_history_without_references_return_an_empty_source_list(app):
    image = generate(app, app.create_project().id)
    assert image.sources == ()
    assert Api(app).get_image_sources(image.id) == {"ok": True, "value": []}


def test_existing_database_adds_sources_without_rewriting_immutable_images(persistent_app):
    image = generate(persistent_app, persistent_app.create_project().id)
    path = persistent_app.data_dir / "anima.db"
    persistent_app.repository.close()
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE images DROP COLUMN sources")
    persistent_app.repository = Repository(path)
    restored = persistent_app.repository.get_image(image.id)
    assert restored == replace(image, sources=())
    assert Api(persistent_app).get_image_sources(image.id)["value"] == []
