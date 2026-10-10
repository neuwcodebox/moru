from io import StringIO
from threading import Event
from unittest.mock import Mock

import pytest

from moru.domain import GenerationSettings
from moru.errors import MoruError
from moru.images.client import ImageWorker


def test_cancellation_wins_when_worker_pipe_closes_during_observation(tmp_path, monkeypatch):
    paths = Mock(root=tmp_path)
    paths.image_payload.return_value = {}
    worker = ImageWorker(paths, tmp_path)
    cancelled = Event()
    process = Mock(stdin=StringIO())
    messages = Mock()
    output = tmp_path / "new.png"

    def closed_pipe(**kwargs):
        output.write_bytes(b"completed before shutdown")
        cancelled.set()
        return None

    messages.get.side_effect = closed_pipe
    monkeypatch.setattr(worker, "_start", lambda: (process, messages))
    monkeypatch.setattr(worker, "_stop", Mock())

    with pytest.raises(MoruError) as error:
        worker.generate("girl", GenerationSettings(seed=1), output, Mock(), cancelled)

    assert error.value.code == "GENERATION_CANCELLED"
    assert not output.exists()


def test_existing_image_is_preserved_without_starting_worker(tmp_path):
    output = tmp_path / "old.png"
    output.write_bytes(b"original")
    paths = Mock(root=tmp_path)
    worker = ImageWorker(paths, tmp_path)

    with pytest.raises(MoruError) as error:
        worker.generate("girl", GenerationSettings(seed=1), output, Mock(), Event())

    assert error.value.code == "IMAGE_SAVE_FAILED"
    assert output.read_bytes() == b"original"
    paths.image_payload.assert_not_called()
