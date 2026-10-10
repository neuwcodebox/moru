import hashlib
from io import BytesIO
from threading import Event
from unittest.mock import Mock

import pytest
from support.application import ManualExecutor

from moru.config import ModelPaths
from moru.downloads import ModelAsset, ModelDownloads, download_model, model_manifest
from moru.errors import MoruError


def asset(content=b"verified model"):
    return ModelAsset(
        "https://models.example/model", hashlib.sha256(content).hexdigest(), len(content)
    )


def test_verified_download_atomically_replaces_existing_file_and_reports_progress(tmp_path):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"previous model")
    progress = Mock()
    download_model(
        asset(), target, progress, Event(), open_url=lambda *a, **k: BytesIO(b"verified model")
    )
    assert target.read_bytes() == b"verified model"
    assert not target.with_suffix(".gguf.part").exists()
    progress.assert_any_call(0, 14)
    progress.assert_any_call(14, 14)


@pytest.mark.parametrize("content", [b"wrong checksum", b"truncated", b"too long invalid download"])
def test_invalid_download_preserves_previous_valid_model(tmp_path, content):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"previous valid model")
    with pytest.raises(MoruError) as error:
        download_model(asset(), target, Mock(), Event(), open_url=lambda *a, **k: BytesIO(content))
    assert error.value.code == "MODEL_CHECKSUM_FAILED"
    assert target.read_bytes() == b"previous valid model"
    assert not target.with_suffix(".gguf.part").exists()


def test_cancellation_does_not_touch_previous_model_or_contact_network(tmp_path):
    cancelled = Event()
    cancelled.set()
    target = tmp_path / "model.gguf"
    target.write_bytes(b"previous valid model")
    open_url = Mock()
    with pytest.raises(MoruError) as error:
        download_model(asset(), target, Mock(), cancelled, open_url=open_url)
    assert error.value.code == "MODEL_DOWNLOAD_CANCELLED"
    assert target.read_bytes() == b"previous valid model"
    open_url.assert_not_called()


def test_network_failure_is_explicit_and_preserves_existing_model(tmp_path):
    target = tmp_path / "model.gguf"
    target.write_bytes(b"previous valid model")
    open_url = Mock(side_effect=OSError("network down"))
    with pytest.raises(MoruError) as error:
        download_model(asset(), target, Mock(), Event(), open_url=open_url)
    assert error.value.code == "MODEL_DOWNLOAD_FAILED"
    assert target.read_bytes() == b"previous valid model"


def test_background_download_installs_builtin_model_without_overwriting_user_override(tmp_path):
    paths = ModelPaths(tmp_path)
    custom = tmp_path / "custom/model.gguf"
    custom.parent.mkdir()
    custom.write_bytes(b"custom model")
    paths.set("prompt", custom)
    executor = ManualExecutor()
    downloads = ModelDownloads(
        paths,
        manifest={"prompt": asset()},
        executor=executor,
        open_url=lambda *a, **k: BytesIO(b"verified model"),
    )
    downloads.start("prompt")
    assert paths.get("prompt") == custom
    executor.run_next()
    assert paths.get("prompt") == tmp_path / "models/prompt/prompt-model.gguf"
    assert custom.read_bytes() == b"custom model"
    status = next(item for item in downloads.status() if item["id"] == "prompt")
    assert status["available"]
    assert status["download"]["state"] == "completed"
    downloads.close()


def test_bundled_manifest_covers_all_runtime_models_with_fixed_revisions_and_sha256():
    manifest = model_manifest()
    assert set(manifest) == {
        "prompt",
        "anima-turbo-v1.1",
        "anima-aesthetic-v1.1",
        "text_encoder",
        "vae",
        "flux2-klein-4b",
        "flux2_text_encoder",
        "flux2_vae",
    }
    for item in manifest.values():
        assert "/resolve/main/" not in item.url
        assert len(item.sha256) == 64


def test_manual_download_guidance_remains_available_after_network_failure(tmp_path):
    executor = ManualExecutor()
    downloads = ModelDownloads(
        ModelPaths(tmp_path),
        executor=executor,
        open_url=Mock(side_effect=OSError("network down")),
    )
    before = next(item for item in downloads.status() if item["id"] == "prompt")
    downloads.start("prompt")
    executor.run_next()

    failed = next(item for item in downloads.status() if item["id"] == "prompt")
    assert failed["download"]["state"] == "failed"
    assert failed["download"]["error_code"] == "MODEL_DOWNLOAD_FAILED"
    assert failed["manual_download"] == before["manual_download"]
    assert failed["manual_download"]["filename"].endswith("Q4_K_M.gguf")


def test_default_generation_settings_match_requested_cfg_and_steps():
    from moru.domain import GenerationSettings

    defaults = GenerationSettings()
    assert defaults.cfg == 1.0
    assert defaults.steps == 10
