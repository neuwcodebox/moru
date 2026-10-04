"""The application owns these narrow contracts, external engines implement them."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from moru.domain import GenerationSettings, PromptSettings

Progress = Callable[[str, int | None, int | None], None]


class PromptGenerator(Protocol):
    def create(self, text: str, settings: PromptSettings) -> str: ...
    def refine(self, prompt: str, text: str, settings: PromptSettings) -> str: ...
    def unload(self) -> None: ...


class ImageGenerator(Protocol):
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
