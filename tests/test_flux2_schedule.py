import pytest

from moru.flux2_schedule import flux2_sigmas


def test_four_step_schedule_matches_the_official_1024_square_workflow():
    # Reference values evaluated from the pinned ComfyUI Flux2Scheduler.
    assert flux2_sigmas(4, 1024, 1024) == pytest.approx(
        [1.0, 0.96738404, 0.90814388, 0.76719993, 0.0], abs=0.000001
    )


@pytest.mark.parametrize("width,height", [(832, 1216), (2048, 1024)])
def test_schedule_keeps_full_denoising_endpoints_for_other_resolutions(width, height):
    values = flux2_sigmas(7, width, height)
    assert len(values) == 8
    assert values[0] == 1
    assert values[-1] == 0
    assert all(left > right for left, right in zip(values, values[1:], strict=False))
    assert values != flux2_sigmas(7, 1024, 1024)


def test_swapping_width_and_height_preserves_the_schedule():
    assert flux2_sigmas(4, 832, 1216) == flux2_sigmas(4, 1216, 832)
