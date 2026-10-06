from concurrent.futures import Executor, Future
from itertools import count

import pytest
from PIL import Image

from moru.errors import MoruError
from moru.repository import Repository
from moru.service import Application


class ManualExecutor(Executor):
    """A controlled scheduler, no threads, sleeps, clocks or inference engines."""

    def __init__(self):
        self.tasks = []

    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        self.tasks.append((future, fn, args, kwargs))
        return future

    def run_next(self):
        future, fn, args, kwargs = self.tasks.pop(0)
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future.result()

    def shutdown(self, wait=True, *, cancel_futures=False):
        while self.tasks:
            self.run_next()


class FakePrompts:
    def __init__(self):
        self.inputs = []
        self.unloads = 0
        self.settings = []
        self.contexts = []
        self.required_memory = 0

    def memory_required(self, settings):
        return self.required_memory

    def create(self, text, settings, cancelled, progress, **context):
        self.contexts.append(context)
        self.settings.append(settings)
        self.inputs.append(("create", text))
        return "silver-haired girl, daytime"

    def refine(self, prompt, text, settings, cancelled, progress, **context):
        self.contexts.append(context)
        self.settings.append(settings)
        self.inputs.append(("refine", prompt, text))
        return "silver-haired girl, nighttime"

    def unload(self):
        self.unloads += 1


class FakeImages:
    def __init__(self):
        self.inputs = []
        self.failures = []
        self.closed = False
        self.reservations = []
        self.release_prompt = False

    def reserve_memory(self, required_bytes, cancelled):
        self.reservations.append(required_bytes)

    def needs_prompt_unload(self, settings, cancelled):
        return self.release_prompt

    def generate(self, prompt, settings, output_path, progress, cancelled):
        self.inputs.append((prompt, settings))
        if self.failures:
            raise MoruError(self.failures.pop(0))
        progress("generating", settings.steps, settings.steps)
        Image.new("RGB", (settings.width, settings.height), (20, 40, 60)).save(output_path)

    def close(self):
        self.closed = True


@pytest.fixture
def app(tmp_path):
    numbers = count(1)
    repository = Repository(tmp_path / "anima.db")
    prompts, images, executor = FakePrompts(), FakeImages(), ManualExecutor()
    application = Application(
        repository,
        prompts,
        images,
        tmp_path,
        executor=executor,
        new_id=lambda: str(next(numbers)),
        now=lambda: "2026-10-04T08:00:00+00:00",
        new_seed=lambda: 42,
    )
    application.scheduler = executor
    yield application
    application.close()
