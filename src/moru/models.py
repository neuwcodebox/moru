"""Supported image models and the files required by each generation choice."""

from dataclasses import dataclass

from moru.errors import MoruError

DEFAULT_MODEL_FILES = {
    "prompt": (
        "prompt/prompt-model.gguf",
        "prompt/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
        "prompt/Qwen3.5-4B-Q4_K_M.gguf",
    ),
    "anima-turbo-v1.1": (
        "anima/diffusion_models/anima-turbo-v1.1.safetensors",
        "anima/anima_turboV11.safetensors",
    ),
    "anima-aesthetic-v1.1": (
        "anima/diffusion_models/anima-aesthetic-v1.1.safetensors",
        "anima/anima-aesthetic-v1.1.safetensors",
    ),
    "text_encoder": (
        "anima/text_encoders/qwen_3_06b_base.safetensors",
        "anima/qwen_3_600m.safetensors",
    ),
    "vae": ("anima/vae/qwen_image_vae.safetensors", "anima/qwen_image_vae.safetensors"),
    "flux2-klein-4b": ("flux2/diffusion_models/flux-2-klein-4b-fp8.safetensors",),
    "flux2_text_encoder": (
        "flux2/text_encoders/qwen_3_4b_fp4_flux2.safetensors",
        "flux2/text_encoders/qwen_3_4b.safetensors",
    ),
    "flux2_vae": ("flux2/vae/flux2-vae.safetensors",),
}


@dataclass(frozen=True)
class ImageModel:
    id: str
    name: str
    family: str
    family_name: str
    variant_name: str
    files: tuple[tuple[str, str], ...]
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    prompt_suffix: str = ""
    natural_prompt: bool = False


IMAGE_MODELS = {
    "anima-turbo-v1.1": ImageModel(
        id="anima-turbo-v1.1",
        name="Anima Turbo",
        family="anima",
        family_name="Anima",
        variant_name="Turbo",
        files=(("diffusion", "anima-turbo-v1.1"), ("text_encoder", "text_encoder"), ("vae", "vae")),
        steps=10,
        cfg=1.0,
        sampler="euler",
        scheduler="simple",
    ),
    "anima-aesthetic-v1.1": ImageModel(
        id="anima-aesthetic-v1.1",
        name="Anima Aesthetic",
        family="anima",
        family_name="Anima",
        variant_name="Aesthetic",
        files=(
            ("diffusion", "anima-aesthetic-v1.1"),
            ("text_encoder", "text_encoder"),
            ("vae", "vae"),
        ),
        steps=40,
        cfg=4.5,
        sampler="euler",
        scheduler="simple",
        prompt_suffix=" Omit score_* tags. Quality tags are optional.",
    ),
    "flux2-klein-4b": ImageModel(
        id="flux2-klein-4b",
        name="FLUX.2 klein 4B",
        family="flux2",
        family_name="FLUX.2",
        variant_name="klein 4B",
        files=(("diffusion", "flux2-klein-4b"), ("text_encoder", "flux2_text_encoder"),
               ("vae", "flux2_vae")),
        steps=4,
        cfg=1.0,
        sampler="euler",
        scheduler="simple",
        natural_prompt=True,
    ),
}
# Read old immutable records without offering the retired model for generation.
RETIRED_MODELS = {"sdxl-base-1.0": {"name": "SDXL Base 1.0", "steps": 30, "cfg": 7.0}}
MODEL_DEFAULTS = {
    key: {"steps": model.steps, "cfg": model.cfg} for key, model in IMAGE_MODELS.items()
}


def image_model(model_id: str) -> ImageModel:
    if not isinstance(model_id, str) or model_id not in IMAGE_MODELS:
        raise MoruError("INVALID_SETTINGS")
    return IMAGE_MODELS[model_id]


def image_model_catalog() -> list[dict]:
    return [
        {
            "id": model.id,
            "name": model.name,
            "family": model.family,
            "family_name": model.family_name,
            "variant_name": model.variant_name,
            "asset_ids": [asset_id for _, asset_id in model.files],
            "defaults": {"steps": model.steps, "cfg": model.cfg},
        }
        for model in IMAGE_MODELS.values()
    ]
