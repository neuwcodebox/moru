from unittest.mock import Mock

import pytest

from moru.errors import MoruError
from moru.images.engine import image_frame


class DecodedPixels:
    def __init__(self, shape, expected_index):
        self.shape = shape
        self.ndim = len(shape)
        self.frame = Mock()
        self.expected_index = expected_index

    def __getitem__(self, index):
        assert index == self.expected_index
        return self.frame


def test_qwen_vae_single_frame_becomes_a_two_dimensional_rgb_image():
    decoded = DecodedPixels((1, 1, 512, 512, 3), (0, 0))
    assert image_frame(decoded) is decoded.frame


def test_regular_image_vae_output_also_preserves_rgb_image():
    decoded = DecodedPixels((1, 512, 512, 3), 0)
    assert image_frame(decoded) is decoded.frame


def test_unexpected_batch_or_video_output_fails_explicitly():
    decoded = DecodedPixels((1, 2, 512, 512, 3), None)
    with pytest.raises(MoruError) as error:
        image_frame(decoded)
    assert error.value.code == "GENERATION_FAILED"
