"""Exercise workflow contracts with a fake ComfyUI runtime, without inference dependencies."""

import sys
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from support.comfy import install_runtime

from moru.config import ModelPaths
from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.images.engine import ComfyEngine


class Anima:
    pass



class Flux2:
    pass


class OutOfMemoryError(Exception):
    pass


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    clip = SimpleNamespace(tokenize=Mock(side_effect=lambda text: text),
                           encode_from_tokens_scheduled=Mock(return_value="conditioning"))
    pixels = Mock()
    pixels.detach.return_value.cpu.return_value.numpy.return_value = pixels
    pixels.__mul__ = Mock(return_value=pixels)
    decoded = SimpleNamespace(ndim=4, shape=(1, 1216, 832, 3))

    class Decoded:
        ndim, shape = decoded.ndim, decoded.shape

        def __getitem__(self, index):
            return pixels

    vae = SimpleNamespace(
        decode=Mock(return_value=Decoded()), latent_channels=128, downscale_ratio=16,
    )
    torch = SimpleNamespace(
        cuda=SimpleNamespace(OutOfMemoryError=OutOfMemoryError),
        inference_mode=nullcontext, zeros=Mock(return_value="latent"),
        zeros_like=Mock(side_effect=lambda value: f"zero({value})"),
        tensor=Mock(side_effect=lambda value, **kwargs: value), float32="float32",
    )
    sd = SimpleNamespace(
        CLIPType=SimpleNamespace(STABLE_DIFFUSION="stable_diffusion", FLUX2="flux2"),
        load_diffusion_model=Mock(return_value=SimpleNamespace(model=Anima())),
        load_clip=Mock(return_value=clip), VAE=Mock(return_value=vae),
    )
    sample = SimpleNamespace(
        fix_empty_latent_channels=Mock(return_value="latent"),
        prepare_noise=Mock(return_value="noise"), sample=Mock(return_value="samples"),
    )
    management = SimpleNamespace(
        unload_all_models=Mock(), soft_empty_cache=Mock(), intermediate_device=lambda: "cpu",
    )
    engine = ComfyEngine(tmp_path)
    install_runtime(
        monkeypatch, tmp_path, torch=torch, sd=sd, sample=sample, management=management,
        utils=SimpleNamespace(load_torch_file=Mock()),
        model_base=SimpleNamespace(Anima=Anima, Flux2=Flux2),
    )
    monkeypatch.setitem(
        sys.modules, "numpy", SimpleNamespace(clip=Mock(return_value=pixels), uint8="uint8")
    )
    monkeypatch.setattr(Image, "fromarray", lambda _: Image.new("RGB", (832, 1216)))
    paths = ModelPaths(tmp_path)
    for asset_id in ("anima-turbo-v1.1", "text_encoder", "vae", "anima-aesthetic-v1.1",
                     "flux2-klein-4b", "flux2_text_encoder", "flux2_vae"):
        path = paths.get(asset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake weights")
    return SimpleNamespace(engine=engine, paths=paths, sd=sd, clip=clip, sample=sample,
                           management=management, torch=torch, vae=vae, root=tmp_path)


def generate(workflow, model_id, name="result", cancelled=None):
    output = workflow.root / f"{name}.png"
    settings = GenerationSettings(model_id=model_id, width=832, height=1216, seed=123)
    workflow.engine.generate("Two cats on a green sofa.", settings, output, Mock(),
                             cancelled or Event(), workflow.paths.image_payload(model_id))
    return output


def test_aesthetic_uses_its_weights_and_defaults_and_saves_the_requested_dimensions(workflow):
    output = generate(workflow, "anima-aesthetic-v1.1")
    workflow.sd.load_diffusion_model.assert_called_once_with(
        str(workflow.paths.get("anima-aesthetic-v1.1"))
    )
    assert workflow.sample.sample.call_args.args[2:6] == (40, 4.5, "euler", "simple")
    with Image.open(output) as image:
        assert image.size == (832, 1216)

def test_anima_keeps_its_split_file_loading_and_sampling_contract(workflow):
    generate(workflow, "anima-turbo-v1.1")
    workflow.sd.load_diffusion_model.assert_called_once_with(
        str(workflow.paths.get("anima-turbo-v1.1"))
    )
    assert "add_dict" not in workflow.clip.encode_from_tokens_scheduled.call_args.kwargs
    assert workflow.sample.sample.call_args.args[2:6] == (10, 1.0, "euler", "simple")


def test_completed_generation_returns_unused_cuda_cache_without_reloading_weights(workflow):
    generate(workflow, "anima-turbo-v1.1", "first")
    workflow.management.soft_empty_cache.reset_mock()
    generate(workflow, "anima-turbo-v1.1", "second")
    workflow.management.soft_empty_cache.assert_called_once()
    workflow.sd.load_diffusion_model.assert_called_once()


@pytest.mark.parametrize("model_id", ["anima-turbo-v1.1", "flux2-klein-4b"])
@pytest.mark.parametrize("failure", ["encoding", "publishing"])
def test_failed_image_save_preserves_existing_output_and_removes_partial_file(
    workflow, monkeypatch, model_id, failure,
):
    if model_id == "flux2-klein-4b":
        use_flux(workflow)
    output = workflow.root / "result.png"
    output.write_bytes(b"existing image")

    if failure == "encoding":
        def fail_save(self, image_file, **kwargs):
            image_file.write(b"partial image")
            raise OSError("disk full")

        monkeypatch.setattr(Image.Image, "save", fail_save)
    else:
        monkeypatch.setattr("moru.images.engine.os.replace", Mock(side_effect=OSError("locked")))

    with pytest.raises(MoruError) as error:
        generate(workflow, model_id)

    assert error.value.code == "IMAGE_SAVE_FAILED"
    assert output.read_bytes() == b"existing image"
    assert not output.with_suffix(".png.part").exists()


def test_switching_variants_loads_the_new_model_and_reuses_it_for_the_next_generation(workflow):
    generate(workflow, "anima-turbo-v1.1", "anima")
    generate(workflow, "anima-aesthetic-v1.1", "aesthetic")
    generate(workflow, "anima-aesthetic-v1.1", "aesthetic-again")
    assert workflow.sd.load_diffusion_model.call_count == 2
    assert workflow.management.unload_all_models.call_count == 2


@pytest.mark.parametrize("missing", ["load_diffusion_model", "load_clip", "VAE"])
def test_a_missing_model_component_fails_before_sampling(workflow, missing):
    getattr(workflow.sd, missing).return_value = None
    with pytest.raises(MoruError) as error:
        generate(workflow, "anima-aesthetic-v1.1")
    assert error.value.code == "MODEL_LOAD_FAILED"
    workflow.sample.sample.assert_not_called()
    assert not (workflow.root / "result.png").exists()

def test_selecting_weights_from_another_architecture_fails_explicitly(workflow):
    workflow.sd.load_diffusion_model.return_value = SimpleNamespace(model=object())
    with pytest.raises(MoruError) as error:
        generate(workflow, "anima-aesthetic-v1.1")
    assert error.value.code == "MODEL_LOAD_FAILED"
    workflow.sample.sample.assert_not_called()


def test_loader_errors_are_reported_as_model_load_failures(workflow):
    workflow.sd.load_diffusion_model.side_effect = ValueError("invalid weights")
    with pytest.raises(MoruError) as error:
        generate(workflow, "anima-aesthetic-v1.1")
    assert error.value.code == "MODEL_LOAD_FAILED"


def test_anima_oom_keeps_the_cuda_failure_contract(workflow):
    workflow.sample.sample.side_effect = OutOfMemoryError()
    with pytest.raises(MoruError) as error:
        generate(workflow, "anima-aesthetic-v1.1")
    assert error.value.code == "CUDA_OOM"
    assert not (workflow.root / "result.png").exists()


def test_cancellation_prevents_saving_output(workflow):
    cancelled = Event()
    cancelled.set()
    with pytest.raises(MoruError) as error:
        generate(workflow, "anima-aesthetic-v1.1", cancelled=cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert not (workflow.root / "result.png").exists()


def use_flux(workflow):
    workflow.sd.load_diffusion_model.return_value = SimpleNamespace(model=Flux2())
    workflow.clip.encode_from_tokens_scheduled.return_value = [
        ["embedding", {"pooled_output": "pooled", "start_percent": 0}],
    ]


def test_flux_uses_its_encoder_latent_shape_and_explicit_euler_schedule(workflow):
    use_flux(workflow)
    output = generate(workflow, "flux2-klein-4b")
    workflow.sd.load_clip.assert_called_once_with(
        [str(workflow.paths.get("flux2_text_encoder"))], clip_type="flux2",
    )
    workflow.torch.zeros.assert_called_once_with((1, 128, 76, 52), device="cpu")
    assert workflow.sample.fix_empty_latent_channels.call_args.args[-1] == 16
    call = workflow.sample.sample.call_args
    assert call.args[2:6] == (4, 1, "euler", "simple")
    assert call.kwargs["seed"] == 123
    assert len(call.kwargs["sigmas"]) == 5
    assert (call.kwargs["sigmas"][0], call.kwargs["sigmas"][-1]) == (1, 0)
    assert call.args[7] == [
        ["zero(embedding)", {"pooled_output": "zero(pooled)", "start_percent": 0}],
    ]
    assert workflow.clip.encode_from_tokens_scheduled.call_count == 1
    positive = workflow.clip.encode_from_tokens_scheduled.return_value
    assert positive[0][1]["pooled_output"] == "pooled"
    with Image.open(output) as image:
        assert image.size == (832, 1216)


def test_switching_to_flux_releases_anima_and_caches_only_the_selected_files(workflow):
    generate(workflow, "anima-turbo-v1.1", "anima")
    use_flux(workflow)
    generate(workflow, "flux2-klein-4b", "flux")
    generate(workflow, "flux2-klein-4b", "flux-again")
    assert workflow.management.unload_all_models.call_count == 2
    assert workflow.sd.load_diffusion_model.call_count == 2
    workflow.sd.load_diffusion_model.return_value = SimpleNamespace(model=Anima())
    workflow.clip.encode_from_tokens_scheduled.return_value = "conditioning"
    generate(workflow, "anima-turbo-v1.1", "anima-again")
    assert workflow.management.unload_all_models.call_count == 3
    assert workflow.sd.load_diffusion_model.call_args.args == (
        str(workflow.paths.get("anima-turbo-v1.1")),
    )


@pytest.mark.parametrize("attribute,value", [("latent_channels", 16), ("downscale_ratio", 8)])
def test_flux_rejects_a_vae_from_another_architecture_before_sampling(workflow, attribute, value):
    use_flux(workflow)
    setattr(workflow.vae, attribute, value)
    with pytest.raises(MoruError) as error:
        generate(workflow, "flux2-klein-4b")
    assert error.value.code == "MODEL_LOAD_FAILED"
    workflow.sample.sample.assert_not_called()


def test_flux_rejects_anima_weights_before_sampling(workflow):
    with pytest.raises(MoruError) as error:
        generate(workflow, "flux2-klein-4b")
    assert error.value.code == "MODEL_LOAD_FAILED"
    workflow.sample.sample.assert_not_called()


def test_flux_oom_cleans_up_without_saving_a_partial_image(workflow):
    use_flux(workflow)
    workflow.sample.sample.side_effect = OutOfMemoryError()
    with pytest.raises(MoruError) as error:
        generate(workflow, "flux2-klein-4b")
    assert error.value.code == "CUDA_OOM"
    assert not (workflow.root / "result.png").exists()
    assert not (workflow.root / "result.png.part").exists()


def test_flux_cancellation_stops_sampling_without_saving_an_image(workflow):
    use_flux(workflow)
    cancelled = Event()

    def sample(*args, callback, **kwargs):
        cancelled.set()
        callback(0, None, None, 4)

    workflow.sample.sample.side_effect = sample
    with pytest.raises(MoruError) as error:
        generate(workflow, "flux2-klein-4b", cancelled=cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert not (workflow.root / "result.png").exists()
