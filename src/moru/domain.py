"""Conversation records and generation settings independent of inference runtimes."""

import math
from dataclasses import dataclass, replace
from typing import Literal

from moru.errors import MoruError

MODEL_IDS = ("anima-turbo-v1.1", "anima-aesthetic-v1.1")
RequestKind = Literal["create", "refine", "manual"]
RequestStatus = Literal["pending", "completed", "failed", "cancelled"]


@dataclass(frozen=True)
class PromptSettings:
    context_size: int = 2048
    max_tokens: int = 1024
    thinking: bool = False
    history_turns: int = 4

    def __post_init__(self):
        if type(self.context_size) is not int or not 1024 <= self.context_size <= 32768:
            raise MoruError("INVALID_SETTINGS")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens < self.context_size:
            raise MoruError("INVALID_SETTINGS")
        if type(self.thinking) is not bool:
            raise MoruError("INVALID_SETTINGS")
        if type(self.history_turns) is not int or not 0 <= self.history_turns <= 20:
            raise MoruError("INVALID_SETTINGS")


@dataclass(frozen=True)
class PromptTurn:
    text: str
    prompt: str


@dataclass(frozen=True)
class GenerationSettings:
    model_id: str = MODEL_IDS[0]
    width: int = 1024
    height: int = 1024
    steps: int = 10
    cfg: float = 1.0
    seed: int | None = None

    def __post_init__(self):
        if self.model_id not in MODEL_IDS:
            raise MoruError("INVALID_SETTINGS")
        for value in (self.width, self.height):
            if type(value) is not int or not 64 <= value <= 4096 or value % 16:
                raise MoruError("INVALID_SETTINGS")
        if type(self.steps) is not int or not 1 <= self.steps <= 150:
            raise MoruError("INVALID_SETTINGS")
        if (
            type(self.cfg) not in (int, float)
            or not math.isfinite(self.cfg)
            or not 0 <= self.cfg <= 30
        ):
            raise MoruError("INVALID_SETTINGS")
        if self.seed is not None and (type(self.seed) is not int or not 0 <= self.seed < 2**63):
            raise MoruError("INVALID_SETTINGS")

    def resolve_seed(self, seed: int) -> "GenerationSettings":
        return replace(self, seed=seed) if self.seed is None else self


@dataclass(frozen=True)
class Project:
    id: str
    created_at: str
    active_leaf_id: str | None = None
    fork_image_id: str | None = None


@dataclass(frozen=True)
class Request:
    id: str
    project_id: str
    text: str
    created_at: str
    base_image_id: str | None
    kind: RequestKind
    settings: GenerationSettings
    status: RequestStatus = "pending"
    error_code: str | None = None
    turn_id: str | None = None


@dataclass(frozen=True)
class Image:
    id: str
    project_id: str
    request_id: str
    parent_image_id: str | None
    prompt: str
    image_path: str
    settings: GenerationSettings
    created_at: str
    generation_method: RequestKind
