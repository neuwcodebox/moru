"""Supported text-to-image workflows using ComfyUI core, without nodes or servers."""

import logging
import os
import sys
from pathlib import Path
from threading import Event

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.images.schedule import flux2_sigmas
from moru.memory_budget import image_memory_required
from moru.models import image_model
from moru.ports import Progress

log = logging.getLogger(__name__)


def image_frame(decoded):
    # Qwen's Wan VAE returns [batch, time, height, width, channels] even for still images.
    if decoded.ndim == 5 and decoded.shape[0:2] == (1, 1):
        return decoded[0, 0]
    if decoded.ndim == 4 and decoded.shape[0] == 1:
        return decoded[0]
    raise MoruError("GENERATION_FAILED")


def zero_conditioning(positive, zeros_like):
    negative = []
    for embedding, metadata in positive:
        values = dict(metadata)
        if values.get("pooled_output") is not None:
            values["pooled_output"] = zeros_like(values["pooled_output"])
        negative.append([zeros_like(embedding), values])
    return negative


def _save_png(pixels, output_path: Path, temporary: Path):
    import numpy as np
    from PIL import Image

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("wb") as image_file:
            Image.fromarray(np.clip(pixels * 255, 0, 255).astype(np.uint8)).save(
                image_file, format="PNG",
            )
            image_file.flush()
            os.fsync(image_file.fileno())
        os.replace(temporary, output_path)
    except OSError as exc:
        raise MoruError("IMAGE_SAVE_FAILED") from exc


class ComfyEngine:
    def __init__(self, comfy_root: Path):
        self._comfy_root = comfy_root
        self._model = None
        self._clip = None
        self._vae = None
        self._loaded_paths = None
        self._runtime = None

    def _load_runtime(self):
        if self._runtime is not None:
            return self._runtime
        if not (self._comfy_root / "comfy/sd.py").is_file():
            raise MoruError("MODEL_LOAD_FAILED")
        sys.path.insert(0, str(self._comfy_root))
        # Tokenizers and encoders must resolve exclusively from bundled local resources.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch

        if not torch.cuda.is_available():
            raise MoruError("MODEL_LOAD_FAILED")
        from comfy.cli_args import args

        args.disable_dynamic_vram = True
        args.disable_cuda_graphs = True
        import comfy.model_base
        import comfy.model_management
        import comfy.sample
        import comfy.sd
        import comfy.utils

        self._runtime = (
            torch, comfy.sd, comfy.sample, comfy.model_management, comfy.utils, comfy.model_base
        )
        return self._runtime

    def reserve_memory(self, required_bytes: int):
        torch, _, _, management, _, _ = self._load_runtime()
        device = management.get_torch_device()
        before = management.get_free_memory(device)
        if before < required_bytes:
            management.free_memory(required_bytes, device)
        # llama.cpp cannot reuse memory held by PyTorch's allocator.
        management.soft_empty_cache()
        after = torch.cuda.mem_get_info(device)[0]
        log.info("prompt VRAM preflight required=%s free_before=%s free_after=%s",
                 required_bytes, before, after)

    def needs_prompt_unload(self, settings: GenerationSettings, paths: dict[str, str]) -> bool:
        torch, _, _, management, _, _ = self._load_runtime()
        required = image_memory_required(paths, settings)
        device = management.get_torch_device()
        # ComfyUI may evict this worker's resident weights; other processes are not reclaimable.
        available = management.get_free_memory(device) + torch.cuda.memory_allocated(device)
        release = available < required
        log.info("image VRAM preflight required=%s available=%s release_prompt=%s",
                 required, available, release)
        return release

    def _load_models(self, family, paths):
        torch, sd, _, management, utils, model_base = self._load_runtime()
        if (family, paths) == self._loaded_paths:
            return
        if any(not Path(path).is_file() for path in paths.values()):
            raise MoruError("IMAGE_MODEL_NOT_FOUND")
        self._model = self._clip = self._vae = None
        management.unload_all_models()
        management.soft_empty_cache()
        self._loaded_paths = None
        try:
            if family not in ("anima", "flux2"):
                raise MoruError("INVALID_SETTINGS")
            expected_type = model_base.Anima if family == "anima" else model_base.Flux2
            self._model = sd.load_diffusion_model(paths["diffusion"])
            self._clip = sd.load_clip(
                [paths["text_encoder"]],
                clip_type=(sd.CLIPType.STABLE_DIFFUSION if family == "anima" else sd.CLIPType.FLUX2)
            )
            self._vae = sd.VAE(sd=utils.load_torch_file(paths["vae"]))
            if (
                self._model is None or self._clip is None or self._vae is None
                or not isinstance(self._model.model, expected_type)
            ):
                raise MoruError("MODEL_LOAD_FAILED")
            if family == "flux2" and (
                self._vae.latent_channels != 128 or self._vae.downscale_ratio != 16
            ):
                raise MoruError("MODEL_LOAD_FAILED")
        except (MoruError, torch.cuda.OutOfMemoryError):
            raise
        except Exception as exc:
            raise MoruError("MODEL_LOAD_FAILED") from exc
        self._loaded_paths = (family, dict(paths))
        log.info("image models loaded")

    def _conditioning(self, text):
        return self._clip.encode_from_tokens_scheduled(
            self._clip.tokenize(text), show_pbar=False
        )

    def generate(
        self,
        prompt: str,
        settings: GenerationSettings,
        output_path: Path,
        progress: Progress,
        cancelled: Event,
        paths: dict[str, str],
    ):
        temporary = output_path.with_suffix(".png.part")
        try:
            progress("loading_model", None, None)
            model = image_model(settings.model_id)
            self._load_models(model.family, paths)
            torch, _, sample, management, _, _ = self._runtime
            with torch.inference_mode():
                positive = self._conditioning(prompt)
                if model.family == "flux2":
                    negative = zero_conditioning(positive, torch.zeros_like)
                    channels, downscale = 128, 16
                    sampling_options = {"sigmas": torch.tensor(
                        flux2_sigmas(settings.steps, settings.width, settings.height),
                        dtype=torch.float32,
                    )}
                else:
                    negative = self._conditioning(
                        "worst quality, low quality, blurry, jpeg artifacts"
                    )
                    channels, downscale = 4, 8
                    sampling_options = {}
                latent = torch.zeros(
                    (1, channels, settings.height // downscale, settings.width // downscale),
                    device=management.intermediate_device(),
                )
                latent = sample.fix_empty_latent_channels(self._model, latent, downscale)
                noise = sample.prepare_noise(latent, settings.seed)

                def step_progress(step, _denoised, _latent, total):
                    if cancelled.is_set():
                        raise MoruError("GENERATION_CANCELLED")
                    progress("generating", step + 1, total)

                progress("generating", 0, settings.steps)
                samples = sample.sample(
                    self._model,
                    noise,
                    settings.steps,
                    settings.cfg,
                    model.sampler,
                    model.scheduler,
                    positive,
                    negative,
                    latent,
                    callback=step_progress,
                    disable_pbar=True,
                    seed=settings.seed,
                    **sampling_options,
                )
                if cancelled.is_set():
                    raise MoruError("GENERATION_CANCELLED")
                pixels = image_frame(self._vae.decode(samples)).detach().cpu().numpy()
            _save_png(pixels, output_path, temporary)
            # Return unused generation buffers while keeping reusable model weights resident.
            management.soft_empty_cache()
        except MoruError:
            raise
        except Exception as exc:
            if self._runtime and isinstance(exc, self._runtime[0].cuda.OutOfMemoryError):
                self._runtime[3].unload_all_models()
                self._runtime[3].soft_empty_cache()
                raise MoruError("CUDA_OOM") from exc
            raise MoruError("GENERATION_FAILED") from exc
        finally:
            temporary.unlink(missing_ok=True)
