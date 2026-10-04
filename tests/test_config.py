import json
import shutil

import pytest

from moru.config import ModelPaths
from moru.errors import MoruError


def test_legacy_local_files_are_found_without_renaming_user_models(tmp_path):
    model = tmp_path / "models/anima/anima_turboV11.safetensors"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake model")
    paths = ModelPaths(tmp_path)
    assert paths.get("anima-turbo-v1.1") == model
    assert {item["id"]: item["available"] for item in paths.status()}["anima-turbo-v1.1"]


def test_portable_model_override_survives_moving_the_entire_app_folder(tmp_path):
    root = tmp_path / "original"
    model = root / "custom/prompt.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake model")
    paths = ModelPaths(root)
    paths.set("prompt", model)
    assert json.loads(paths.config_path.read_text())["prompt"] == "custom/prompt.gguf"
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    assert ModelPaths(moved).get("prompt") == moved / "custom/prompt.gguf"


def test_broken_model_configuration_fails_instead_of_ignoring_override(tmp_path):
    paths = ModelPaths(tmp_path)
    paths.config_path.parent.mkdir(parents=True)
    paths.config_path.write_text("not json")
    with pytest.raises(MoruError) as error:
        paths.get("prompt")
    assert error.value.code == "MODEL_LOAD_FAILED"


def test_uncensored_prompt_model_is_discovered_before_the_older_local_model(tmp_path):
    prompt_folder = tmp_path / "models/prompt"
    prompt_folder.mkdir(parents=True)
    preferred = prompt_folder / "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
    preferred.write_bytes(b"selected uncensored model")
    (prompt_folder / "Qwen3.5-4B-Q4_K_M.gguf").write_bytes(b"older model")
    assert ModelPaths(tmp_path).get("prompt") == preferred


def test_model_status_exposes_the_selected_filename_without_its_directory(tmp_path):
    model = tmp_path / "private-directory/my-custom-model.gguf"
    model.parent.mkdir()
    model.write_bytes(b"fake gguf")
    paths = ModelPaths(tmp_path)
    paths.set("prompt", model)
    status = next(item for item in paths.status() if item["id"] == "prompt")
    assert status == {"id": "prompt", "available": True, "filename": "my-custom-model.gguf"}
    missing = next(item for item in paths.status() if item["id"] == "vae")
    assert missing["filename"] is None
