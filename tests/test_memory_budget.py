"""VRAM decisions use controlled sizes and measurements, never real inference."""

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from support.comfy import install_runtime

from moru.domain import GenerationSettings, PromptSettings
from moru.images.engine import ComfyEngine
from moru.memory_budget import GIB, image_memory_required, prompt_memory_required


def test_image_budget_accounts_for_selected_files_and_resolution(tmp_path):
    small, large = tmp_path / "fp4", tmp_path / "fp16"
    small.write_bytes(b"x" * 40)
    large.write_bytes(b"x" * 80)
    settings = GenerationSettings()
    small_budget = image_memory_required({"text_encoder": str(small)}, settings)
    assert small_budget < image_memory_required({"text_encoder": str(large)}, settings)
    assert small_budget < image_memory_required(
        {"text_encoder": str(small)}, GenerationSettings(width=2048, height=1024)
    )


def test_prompt_budget_increases_with_context_and_file_size(tmp_path):
    path = tmp_path / "prompt.gguf"
    path.write_bytes(b"gguf")
    small = prompt_memory_required(path, PromptSettings(context_size=4096))
    assert small < prompt_memory_required(path, PromptSettings(context_size=8192))
    path.write_bytes(b"gguf" * 100)
    assert small < prompt_memory_required(path, PromptSettings(context_size=4096))


@pytest.mark.parametrize("available,allocated,expected", [
    (GIB, 0, True), (4 * GIB, 0, False), (GIB, 3 * GIB, False),
])
def test_image_preflight_counts_its_reclaimable_weights_not_just_free_vram(
    tmp_path, monkeypatch, available, allocated, expected
):
    path = tmp_path / "model"
    path.write_bytes(b"fake weights")
    torch = SimpleNamespace(cuda=SimpleNamespace(memory_allocated=lambda _: allocated))
    management = SimpleNamespace(get_torch_device=lambda: "gpu",
                                 get_free_memory=lambda _: available)
    engine = ComfyEngine(tmp_path)
    install_runtime(monkeypatch, tmp_path, torch=torch, management=management)
    assert engine.needs_prompt_unload(GenerationSettings(), {"diffusion": str(path)}) is expected


@pytest.mark.parametrize("free,evicted", [(GIB, True), (8 * GIB, False)])
def test_prompt_reservation_evicts_only_when_needed_and_returns_allocator_cache(
    tmp_path, monkeypatch, free, evicted
):
    management = SimpleNamespace(get_torch_device=lambda: "gpu", get_free_memory=lambda _: free,
                                 free_memory=Mock(), soft_empty_cache=Mock())
    torch = SimpleNamespace(cuda=SimpleNamespace(mem_get_info=lambda _: (8 * GIB, 12 * GIB)))
    engine = ComfyEngine(tmp_path)
    install_runtime(monkeypatch, tmp_path, torch=torch, management=management)
    engine.reserve_memory(4 * GIB)
    assert management.free_memory.called is evicted
    management.soft_empty_cache.assert_called_once()


def test_insufficient_vram_unloads_prompt_before_first_image_attempt(app):
    project = app.create_project()
    app.images.release_prompt = True
    original = app.images.generate

    def generate(*args):
        assert app.prompts.unloads == 1
        original(*args)

    app.images.generate = generate
    job = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert len(app.images.inputs) == 1


def test_sufficient_vram_keeps_prompt_model_resident(app):
    project = app.create_project()
    job = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"
    assert app.prompts.unloads == 0


def test_prompt_loading_reserves_image_vram_before_inference(app):
    project = app.create_project()
    app.prompts.required_memory = 4 * GIB
    original = app.prompts.create

    def create(*args, **kwargs):
        assert app.images.reservations == [4 * GIB]
        return original(*args, **kwargs)

    app.prompts.create = create
    job = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "completed"


def test_manual_generation_does_not_reserve_memory_for_prompt_loading(app):
    project = app.create_project()
    job = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    app.images.reservations.clear()
    retry = app.regenerate(app.get_job(job.id).image_id)
    app.scheduler.run_next()
    assert app.get_job(retry.id).state == "completed"
    assert app.images.reservations == []


def test_cancellation_after_memory_reservation_does_not_start_prompt_inference(app):
    project = app.create_project()
    app.images.reserve_memory = lambda required, cancelled: cancelled.set()
    job = app.submit_request(project.id, "a cat")
    app.scheduler.run_next()
    assert app.get_job(job.id).state == "cancelled"
    assert app.prompts.inputs == []


def test_cancelled_preflight_does_not_start_an_image_worker(tmp_path, monkeypatch):
    from moru.config import ModelPaths
    from moru.errors import MoruError
    from moru.images.client import ImageWorker

    worker = ImageWorker(ModelPaths(tmp_path), tmp_path)
    start = Mock()
    monkeypatch.setattr("moru.images.client.subprocess.Popen", start)
    cancelled = Event()
    cancelled.set()
    with pytest.raises(MoruError) as error:
        worker.reserve_memory(GIB, cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    start.assert_not_called()
