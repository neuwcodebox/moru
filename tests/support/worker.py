"""Scripted stdio processes at the worker subprocess boundary."""

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

from moru.images.client import ImageWorker


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
    monkeypatch.setattr("moru.images.client.Thread", InlineThread)
    monkeypatch.setattr("moru.images.client.WindowsJob", Mock(side_effect=jobs))
    monkeypatch.setattr("moru.images.client.subprocess.Popen", Mock(side_effect=processes))
    monkeypatch.setattr("moru.images.client.uuid.uuid4", lambda: SimpleNamespace(hex="request"))
    paths = Mock(root=tmp_path)
    paths.image_payload.return_value = {}
    return ImageWorker(paths, tmp_path), processes, jobs


def result(path):
    return {"id": "request", "type": "result", "payload": {"image_path": str(path), "seed": 1}}
