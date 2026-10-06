"""Conservative preflight budgets; real allocation failures remain authoritative."""

from pathlib import Path

from moru.domain import GenerationSettings, PromptSettings

GIB = 1024 ** 3


def prompt_memory_required(path: Path, settings: PromptSettings) -> int:
    # Cover weights, context-dependent KV/work buffers and CUDA overhead before loading.
    return int(path.stat().st_size * 1.1) + settings.context_size * 256 * 1024 + GIB


def image_memory_required(paths: dict[str, str], settings: GenerationSettings) -> int:
    # Budget for retaining all image weights, avoiding reliance on aggressive CPU offloading.
    weights = sum(Path(path).stat().st_size for path in paths.values())
    workspace = max(GIB, 2 * GIB * settings.width * settings.height // (1024 * 1024))
    return int(weights * 1.1) + workspace + GIB
