"""Portable locations and explicit model path overrides."""

import json
import os
import sys
from pathlib import Path

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
}


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class ModelPaths:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config_path = self.root / "data" / "model-paths.json"

    def _overrides(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            overrides = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(overrides, dict) or any(
                key not in DEFAULT_MODEL_FILES or not isinstance(value, str)
                for key, value in overrides.items()
            ):
                raise ValueError("invalid model path configuration")
            return overrides
        except (ValueError, OSError) as exc:
            raise MoruError("MODEL_LOAD_FAILED") from exc

    def get(self, model_id: str) -> Path:
        if model_id not in DEFAULT_MODEL_FILES:
            raise MoruError("INVALID_SETTINGS")
        override = self._overrides().get(model_id)
        if override is not None:
            return (self.root / override).resolve()
        candidates = [self.root / "models" / name for name in DEFAULT_MODEL_FILES[model_id]]
        return next((path for path in candidates if path.is_file()), candidates[0])

    def set(self, model_id: str, path: Path):
        if model_id not in DEFAULT_MODEL_FILES:
            raise MoruError("INVALID_SETTINGS")
        path = path.resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise MoruError(
                "PROMPT_MODEL_NOT_FOUND" if model_id == "prompt" else "IMAGE_MODEL_NOT_FOUND"
            )
        overrides = self._overrides()
        overrides[model_id] = (
            path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path)
        )
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".json.part")
        try:
            temporary.write_text(
                json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, self.config_path)
        except OSError as exc:
            raise MoruError("IMAGE_SAVE_FAILED") from exc

    def status(self) -> list[dict]:
        result = []
        for key in DEFAULT_MODEL_FILES:
            path = self.get(key)
            available = path.is_file()
            result.append(
                {"id": key, "available": available, "filename": path.name if available else None}
            )
        return result

    def image_payload(self, model_id: str) -> dict[str, str]:
        paths = {
            "diffusion": self.get(model_id),
            "text_encoder": self.get("text_encoder"),
            "vae": self.get("vae"),
        }
        if any(not path.is_file() for path in paths.values()):
            raise MoruError("IMAGE_MODEL_NOT_FOUND")
        return {key: str(path) for key, path in paths.items()}
