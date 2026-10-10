"""FLUX.2's resolution-dependent Euler schedule without importing ComfyUI nodes."""

import math


def flux2_sigmas(steps: int, width: int, height: int) -> list[float]:
    # Match Flux2Scheduler at our pinned ComfyUI revision (nodes_flux.py).
    sequence_length = width * height // 256
    long_run = 0.00016927 * sequence_length + 0.45666666
    if sequence_length > 4300:
        mu = long_run
    else:
        short_run = 8.73809524e-05 * sequence_length + 1.89833333
        slope = (long_run - short_run) / 190
        mu = long_run + (steps - 200) * slope
    shift = math.exp(mu)
    return [
        shift * t / (1 + (shift - 1) * t)
        for t in (1 - index / steps for index in range(steps + 1))
    ]
