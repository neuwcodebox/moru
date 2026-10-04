"""Fixed Anima workflow using ComfyUI core only, never nodes, server or plugins."""

import logging
import os
import sys
from pathlib import Path
from threading import Event

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.ports import Progress

log = logging.getLogger(__name__)
PRESETS = {
    "anima-turbo-v1.1": ("euler", "simple"),
    "anima-aesthetic-v1.1": ("euler", "simple"),
}


def image_frame(decoded):
    # Qwen's Wan VAE returns [batch, time, height, width, channels] even for still images.
    if decoded.ndim == 5 and decoded.shape[0:2] == (1, 1):
        return decoded[0, 0]
    if decoded.ndim == 4 and decoded.shape[0] == 1:
        return decoded[0]
    raise MoruError("GENERATION_FAILED")


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
        import comfy.model_management
        import comfy.sample
        import comfy.sd
        import comfy.utils

        self._runtime = (torch, comfy.sd, comfy.sample, comfy.model_management, comfy.utils)
        return self._runtime

    def _load_models(self, paths):
        torch, sd, _, management, utils = self._load_runtime()
        if paths == self._loaded_paths:
            return
        if any(not Path(path).is_file() for path in paths.values()):
            raise MoruError("IMAGE_MODEL_NOT_FOUND")
        self._model = self._clip = self._vae = None
        management.unload_all_models()
        management.soft_empty_cache()
        self._loaded_paths = None
        self._model = sd.load_diffusion_model(paths["diffusion"])
        self._clip = sd.load_clip([paths["text_encoder"]], clip_type=sd.CLIPType.STABLE_DIFFUSION)
        self._vae = sd.VAE(sd=utils.load_torch_file(paths["vae"]))
        self._loaded_paths = dict(paths)
        log.info("image models loaded")

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
            self._load_models(paths)
            torch, _, sample, management, _ = self._runtime
            with torch.inference_mode():
                positive = self._clip.encode_from_tokens_scheduled(
                    self._clip.tokenize(prompt),
                    show_pbar=False,
                )
                negative = self._clip.encode_from_tokens_scheduled(
                    self._clip.tokenize("worst quality, low quality, blurry, jpeg artifacts"),
                    show_pbar=False,
                )
                latent = torch.zeros(
                    (1, 4, settings.height // 8, settings.width // 8),
                    device=management.intermediate_device(),
                )
                latent = sample.fix_empty_latent_channels(self._model, latent, 8)
                noise = sample.prepare_noise(latent, settings.seed)
                sampler, scheduler = PRESETS[settings.model_id]

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
                    sampler,
                    scheduler,
                    positive,
                    negative,
                    latent,
                    callback=step_progress,
                    disable_pbar=True,
                    seed=settings.seed,
                )
                if cancelled.is_set():
                    raise MoruError("GENERATION_CANCELLED")
                pixels = image_frame(self._vae.decode(samples)).detach().cpu().numpy()
            import numpy as np
            from PIL import Image

            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with temporary.open("wb") as image_file:
                    Image.fromarray(np.clip(pixels * 255, 0, 255).astype(np.uint8)).save(
                        image_file,
                        format="PNG",
                    )
                    image_file.flush()
                    os.fsync(image_file.fileno())
                os.replace(temporary, output_path)
            except OSError as exc:
                raise MoruError("IMAGE_SAVE_FAILED") from exc
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
