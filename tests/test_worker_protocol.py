import json
import sys
from io import StringIO
from unittest.mock import Mock

import pytest

from moru.errors import MoruError
from moru.images.client import parse_worker_message, worker_command
from moru.images.worker import serve


def message(tmp_path, **changes):
    payload = {
        "model_id": "anima-turbo-v1.1",
        "width": 1024,
        "height": 1024,
        "steps": 10,
        "cfg": 1.0,
        "seed": 123,
        "prompt": "girl",
        "output_path": str(tmp_path / "images/new.png"),
        "paths": {"diffusion": "model", "text_encoder": "clip", "vae": "vae"},
    }
    payload.update(changes)
    return json.dumps({"id": "job-1", "type": "generate", "payload": payload}) + "\n"


def test_worker_returns_step_progress_and_result_with_actual_seed(tmp_path):
    engine = Mock()
    engine.generate.side_effect = lambda prompt, settings, output, progress, cancel, paths: (
        progress("generating", 4, 10)
    )
    output = StringIO()
    serve(StringIO(message(tmp_path)), output, engine, tmp_path)
    progress, result = [json.loads(line) for line in output.getvalue().splitlines()]
    assert progress == {
        "id": "job-1",
        "type": "progress",
        "payload": {
            "state": "generating",
            "step": 4,
            "total": 10,
        },
    }
    assert result["type"] == "result"
    assert result["payload"]["seed"] == 123
    assert result["payload"]["image_path"] == str((tmp_path / "images/new.png").resolve())


def test_worker_reports_budget_and_reserves_memory_without_generating_an_image(tmp_path):
    engine = Mock()
    engine.needs_prompt_unload.return_value = True
    requests = [
        {"id": "reserve", "type": "reserve_memory", "payload": {"required_bytes": 4096}},
        {"id": "budget", "type": "memory_budget", "payload": {
            "settings": {"model_id": "flux2-klein-4b", "width": 832, "height": 1216},
            "paths": {"diffusion": "fp8", "text_encoder": "fp4", "vae": "vae"},
        }},
    ]
    output = StringIO()
    serve(StringIO("".join(json.dumps(request) + "\n" for request in requests)),
          output, engine, tmp_path)
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert replies[0] == {"id": "reserve", "type": "result", "payload": {}}
    assert replies[1] == {"id": "budget", "type": "result",
                          "payload": {"release_prompt": True}}
    engine.reserve_memory.assert_called_once_with(4096)
    settings, paths = engine.needs_prompt_unload.call_args.args
    assert (settings.model_id, settings.width, settings.height) == ("flux2-klein-4b", 832, 1216)
    assert paths["text_encoder"] == "fp4"
    engine.generate.assert_not_called()


@pytest.mark.parametrize("required", [True, -1, 0, "1024"])
def test_invalid_memory_reservation_is_rejected(tmp_path, required):
    engine = Mock()
    output = StringIO()
    request = {"id": "reserve", "type": "reserve_memory",
               "payload": {"required_bytes": required}}
    serve(StringIO(json.dumps(request) + "\n"), output, engine, tmp_path)
    assert json.loads(output.getvalue())["payload"]["code"] == "INVALID_REQUEST"
    engine.reserve_memory.assert_not_called()


def test_worker_failure_has_stable_code_and_no_traceback_or_prompt_in_protocol(tmp_path):
    engine = Mock()
    engine.generate.side_effect = MoruError("CUDA_OOM")
    output = StringIO()
    serve(StringIO(message(tmp_path)), output, engine, tmp_path)
    assert json.loads(output.getvalue()) == {
        "id": "job-1",
        "type": "error",
        "payload": {"code": "CUDA_OOM"},
    }


def test_worker_cannot_overwrite_an_existing_image_or_escape_image_folder(tmp_path):
    engine = Mock()
    original = tmp_path / "images/old.png"
    original.parent.mkdir()
    original.write_bytes(b"immutable image")
    for path in (original, tmp_path / "elsewhere.png"):
        output = StringIO()
        serve(StringIO(message(tmp_path, output_path=str(path))), output, engine, tmp_path)
        assert json.loads(output.getvalue())["payload"]["code"] == "IMAGE_SAVE_FAILED"
    engine.generate.assert_not_called()
    assert original.read_bytes() == b"immutable image"


@pytest.mark.parametrize(
    "line", ["not json", "[]", '{"id":"another-job","type":"result","payload":{}}']
)
def test_invalid_or_unrelated_worker_response_is_not_accepted_as_success(line):
    with pytest.raises(MoruError) as error:
        parse_worker_message(line, "job-1")
    assert error.value.code == "GENERATION_FAILED"


def test_packaged_worker_spawns_same_executable_without_a_server(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = worker_command(tmp_path, tmp_path / "runtime/comfyui", 123)
    assert command[0] == sys.executable
    assert command[1] == "--internal-image-worker"
    assert command[command.index("--parent-pid") + 1] == "123"
    assert "-m" not in command
