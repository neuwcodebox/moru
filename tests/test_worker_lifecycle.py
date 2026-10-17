import json
from threading import Event
from unittest.mock import Mock

import pytest
from support.worker import install_workers, result

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.images.client import ImageWorker


@pytest.mark.parametrize("operation", ["generate", "inpaint"])
def test_generation_command_sends_original_paths_only_for_inpainting(
    tmp_path, monkeypatch, operation,
):
    output = tmp_path / "new.png"
    worker, processes, _ = install_workers(tmp_path, monkeypatch, [result(output)])
    region = (tmp_path / "source.png", tmp_path / "mask.png") if operation == "inpaint" else ()
    try:
        getattr(worker, operation)("blue cup", GenerationSettings(seed=1), output, Mock(), Event(),
                                   *region)
        sent = json.loads(processes[0].stdin.getvalue())
        assert sent["type"] == operation
        assert sent["payload"]["prompt"] == "blue cup"
        assert sent["payload"]["output_path"] == str(output.resolve())
        if region:
            assert sent["payload"]["original_path"] == str(region[0].resolve())
            assert sent["payload"]["mask_path"] == str(region[1].resolve())
        else:
            assert "original_path" not in sent["payload"]
            assert "mask_path" not in sent["payload"]
    finally:
        worker.close()


@pytest.mark.parametrize("operation", ["generate", "inpaint"])
@pytest.mark.parametrize("mismatch", [{"seed": 2}, {"image_path": "wrong.png"}])
def test_generation_rejects_mismatched_results_and_removes_temporary_output(
    tmp_path, monkeypatch, operation, mismatch,
):
    output = tmp_path / "new.png"
    temporary = output.with_suffix(".png.part")
    temporary.write_bytes(b"partial")
    reply = result(output)
    reply["payload"].update(mismatch)
    worker, processes, _ = install_workers(tmp_path, monkeypatch, [reply])
    region = (tmp_path / "source.png", tmp_path / "mask.png") if operation == "inpaint" else ()
    try:
        with pytest.raises(MoruError) as error:
            getattr(worker, operation)("cup", GenerationSettings(seed=1), output, Mock(), Event(),
                                       *region)
        assert error.value.code == "GENERATION_FAILED"
        assert processes[0].stdin.closed
        assert not temporary.exists()
    finally:
        worker.close()


def test_restarting_an_exited_worker_releases_its_pipes_and_windows_job(tmp_path, monkeypatch):
    first_path, second_path = tmp_path / "first.png", tmp_path / "second.png"
    worker, processes, jobs = install_workers(
        tmp_path, monkeypatch, [result(first_path), result(second_path)]
    )
    try:
        worker.generate("girl", GenerationSettings(seed=1), first_path, Mock(), Event())
        processes[0].poll.return_value = 0
        worker.generate("girl", GenerationSettings(seed=1), second_path, Mock(), Event())
        assert processes[0].stdin.closed
        assert processes[0].stdout.closed
        jobs[0].close.assert_called_once()
    finally:
        worker.close()


@pytest.mark.parametrize("release", [True, False])
def test_worker_client_uses_measured_budget_decision(tmp_path, monkeypatch, release):
    reply = {"id": "request", "type": "result", "payload": {"release_prompt": release}}
    worker, processes, _ = install_workers(tmp_path, monkeypatch, [reply])
    try:
        assert worker.needs_prompt_unload(GenerationSettings(), Event()) is release
        sent = json.loads(processes[0].stdin.getvalue())
        assert sent["type"] == "memory_budget"
        assert sent["payload"]["settings"]["width"] == 1024
    finally:
        worker.close()


def test_worker_client_rejects_an_invalid_budget_response(tmp_path, monkeypatch):
    reply = {"id": "request", "type": "result", "payload": {"release_prompt": "false"}}
    worker, processes, _ = install_workers(tmp_path, monkeypatch, [reply])
    with pytest.raises(MoruError) as error:
        worker.needs_prompt_unload(GenerationSettings(), Event())
    assert error.value.code == "GENERATION_FAILED"
    assert processes[0].stdin.closed


def test_resident_prompt_does_not_start_worker_to_reserve_zero_bytes(tmp_path, monkeypatch):
    worker = ImageWorker(Mock(root=tmp_path), tmp_path)
    start = Mock()
    monkeypatch.setattr("moru.images.client.subprocess.Popen", start)
    worker.reserve_memory(0, Event())
    start.assert_not_called()


def test_progress_callback_failure_stops_the_worker_and_has_a_stable_error(tmp_path, monkeypatch):
    response = {"id": "request", "type": "progress", "payload": {"state": "generating"}}
    worker, processes, jobs = install_workers(tmp_path, monkeypatch, [response])
    try:
        with pytest.raises(MoruError) as error:
            worker.generate(
                "girl",
                GenerationSettings(seed=1),
                tmp_path / "new.png",
                Mock(side_effect=RuntimeError("consumer failure")),
                Event(),
            )
        assert error.value.code == "GENERATION_FAILED"
        assert processes[0].stdin.closed
        assert processes[0].stdout.closed
        jobs[0].close.assert_called_once()
    finally:
        worker.close()


def test_cancellation_during_a_callback_error_removes_the_new_image(tmp_path, monkeypatch):
    response = {"id": "request", "type": "progress", "payload": {"state": "generating"}}
    worker, _, _ = install_workers(tmp_path, monkeypatch, [response])
    output = tmp_path / "new.png"
    cancelled = Event()

    def cancel_after_output(state, step, total):
        output.write_bytes(b"new image")
        cancelled.set()
        raise OSError("pipe closed during cancellation")

    try:
        with pytest.raises(MoruError) as error:
            worker.generate(
                "girl", GenerationSettings(seed=1), output, cancel_after_output, cancelled
            )
        assert error.value.code == "GENERATION_CANCELLED"
        assert not output.exists()
    finally:
        worker.close()
