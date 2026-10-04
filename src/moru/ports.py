"""The application owns these narrow contracts, external engines implement them."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from moru.domain import GenerationSettings, PromptSettings, PromptTurn

Progress = Callable[[str, int | None, int | None], None]
PromptProgress = Callable[[str, str], None]


class PromptGenerator(Protocol):
    def create(
        self,
        text: str,
        settings: PromptSettings,
        cancelled: Event,
        progress: PromptProgress,
        *,
        history: tuple[PromptTurn, ...] = (),
        model_id: str = "anima-turbo-v1.1",
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
    ) -> str: ...
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
