from itertools import count
from pathlib import Path

import pytest
from support.application import FakeImages, FakePrompts, ManualExecutor

from moru.repository import Repository
from moru.service import Application


@pytest.fixture
def make_app(tmp_path):
    applications = []

    def create(*, database=None, **options):
        numbers = count(1)
        executor = ManualExecutor()
        defaults = {
            "new_id": lambda: str(next(numbers)),
            "now": lambda: "2026-10-04T08:00:00+00:00",
            "new_seed": lambda: 42,
        }
        application = Application(
            Repository(database if database is not None else Path(":memory:")),
            FakePrompts(),
            FakeImages(),
            tmp_path,
            executor=executor,
            **(defaults | options),
        )
        application.scheduler = executor
        applications.append(application)
        return application

    yield create
    for application in reversed(applications):
        application.close()


@pytest.fixture
def app(make_app):
    """Use real SQLite without disk synchronization for application behavior."""
    return make_app()


@pytest.fixture
def persistent_app(make_app, tmp_path):
    """Use a file database when restart, schema or disk failures are the contract."""
    return make_app(database=tmp_path / "anima.db")
