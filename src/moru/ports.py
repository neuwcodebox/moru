"""The application owns these narrow contracts, external engines implement them."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Literal, Protocol

from moru.domain import GenerationSettings, PromptSettings, PromptSource, PromptTurn

Progress = Callable[[str, int | None, int | None], None]
PromptProgress = Callable[[str, str], None]
SourceProgress = Callable[[PromptSource], None]
PromptStage = Literal["searching_tags", "prompting"]
PromptStageProgress = Callable[[PromptStage, int], None]


class PromptGenerator(Protocol):
    """Report readiness before inference and actual lookup references through on_source.

    on_stage reports the phase and cumulative distinct tag count, without exposing reasoning.
    Never report readiness after load failure/cancellation or expose private reasoning as a source.
    """

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
        on_source: SourceProgress | None = None,
        on_stage: PromptStageProgress | None = None,
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
        on_source: SourceProgress | None = None,
        on_stage: PromptStageProgress | None = None,
    ) -> str: ...
    def unload(self) -> None: ...
    def memory_required(self, settings: PromptSettings) -> int:
        """Additional VRAM budget for loading; zero when the requested model is resident."""
        ...


class TagSearcher(Protocol):
    def search_tags(self, query: str, limit: int, cancelled: Event) -> list[str]: ...


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
