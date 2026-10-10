"""The application owns these narrow contracts, external engines implement them."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from moru.domain import GenerationSettings, PromptSettings, PromptTurn

Progress = Callable[[str, int | None, int | None], None]
PromptProgress = Callable[[str, str], None]


class PromptGenerator(Protocol):
    """Call on_ready after preparation, before inference; never after load failure/cancellation."""

    def create(
        self,
        text: str,
        settings: PromptSettings,
        cancelled: Event,
        progress: PromptProgress,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
        on_ready: Callable[[], None] | None = None,
    ) -> str: ...
    def refine(
        self,
        prompt: str,
        text: str,
        settings: PromptSettings,
        cancelled: Event,
        progress: PromptProgress,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
        on_ready: Callable[[], None] | None = None,
    ) -> str: ...
    def unload(self) -> None: ...
    def memory_required(self, settings: PromptSettings) -> int:
        """Additional VRAM budget for loading; zero when the requested model is resident."""
        ...


class ImageGenerator(Protocol):
    def reserve_memory(self, required_bytes: int, cancelled: Event) -> None:
        """Release image VRAM as needed before loading the prompt model."""
        ...

    def needs_prompt_unload(self, settings: GenerationSettings, cancelled: Event) -> bool:
        """Compare the image budget to measured free and reclaimable image VRAM."""
        ...

    def generate(
        self,
        prompt: str,
        settings: GenerationSettings,
        output_path: Path,
        progress: Progress,
        cancelled: Event,
    ) -> None:
        """Write a complete PNG to output_path, or raise a MoruError."""
        ...

    def close(self) -> None: ...
