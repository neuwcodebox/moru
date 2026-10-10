"""Route an immutable prompt-settings snapshot to the chosen engine."""

from collections.abc import Callable
from threading import Event

from moru.domain import PromptSettings, PromptTurn
from moru.ports import PromptGenerator, PromptProgress


class PromptProviders:
    def __init__(self, local: PromptGenerator, chatgpt: PromptGenerator):
        self.local, self.chatgpt = local, chatgpt

    def _engine(self, settings: PromptSettings) -> PromptGenerator:
        return self.chatgpt if settings.provider == "chatgpt" else self.local

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
    ) -> str:
        return self._engine(settings).create(
            text,
            settings,
            cancelled,
            progress,
            history=history,
            model_id=model_id,
            on_ready=on_ready,
        )

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
    ) -> str:
        return self._engine(settings).refine(
            prompt,
            text,
            settings,
            cancelled,
            progress,
            history=history,
            model_id=model_id,
            on_ready=on_ready,
        )

    def memory_required(self, settings: PromptSettings) -> int:
        if settings.provider == "chatgpt":
            self.local.unload()
        return self._engine(settings).memory_required(settings)

    def unload(self) -> None:
        self.local.unload()
        self.chatgpt.unload()
