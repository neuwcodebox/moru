import json
from io import StringIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.worker_client import ImageWorker


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def install_workers(tmp_path, monkeypatch, responses):
    processes = [
        Mock(stdin=StringIO(), stdout=StringIO(json.dumps(response) + "\n"))
        for response in responses
    ]
    for process in processes:
        process.poll.return_value = None
    jobs = [Mock() for _ in processes]
    monkeypatch.setattr("moru.worker_client.Thread", InlineThread)
    monkeypatch.setattr("moru.worker_client.WindowsJob", Mock(side_effect=jobs))
    monkeypatch.setattr("moru.worker_client.subprocess.Popen", Mock(side_effect=processes))
    monkeypatch.setattr("moru.worker_client.uuid.uuid4", lambda: SimpleNamespace(hex="request"))
    paths = Mock(root=tmp_path)
    paths.image_payload.return_value = {}
    return ImageWorker(paths, tmp_path), processes, jobs


def result(path):
    return {"id": "request", "type": "result", "payload": {"image_path": str(path), "seed": 1}}


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
