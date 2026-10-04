"""Conversation records and generation settings independent of inference runtimes."""

import math
from dataclasses import dataclass, replace
from typing import Literal

from moru.errors import MoruError

MODEL_DEFAULTS = {
    "anima-turbo-v1.1": {"steps": 10, "cfg": 1.0},
    "anima-aesthetic-v1.1": {"steps": 40, "cfg": 4.5},
}
MODEL_IDS = tuple(MODEL_DEFAULTS)
# This is an LLM output reserve, not a hard input limit of the image model.
FINAL_PROMPT_TOKEN_RESERVE = 512 + 128
REASONING_SHARES = {"low": 0.5, "medium": 0.75, "high": 1.0}
RequestKind = Literal["create", "refine", "manual"]
RequestStatus = Literal["pending", "completed", "failed", "cancelled"]


@dataclass(frozen=True)
class PromptSettings:
    context_size: int = 4096
    max_tokens: int = 2048
    thinking: bool = True
    history_turns: int = 4
    reasoning_level: Literal["low", "medium", "high"] = "medium"

    def __post_init__(self):
        if type(self.context_size) is not int or not 1024 <= self.context_size <= 32768:
            raise MoruError("INVALID_SETTINGS")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens < self.context_size:
            raise MoruError("INVALID_SETTINGS")
        if type(self.thinking) is not bool:
            raise MoruError("INVALID_SETTINGS")
        if type(self.history_turns) is not int or not 0 <= self.history_turns <= 20:
            raise MoruError("INVALID_SETTINGS")
        if (
            not isinstance(self.reasoning_level, str)
            or self.reasoning_level not in REASONING_SHARES
        ):
            raise MoruError("INVALID_SETTINGS")

    @property
    def thinking_budget(self) -> int:
        if not self.thinking:
            return 0
        available = max(0, self.max_tokens - FINAL_PROMPT_TOKEN_RESERVE)
        return int(available * REASONING_SHARES[self.reasoning_level])


@dataclass(frozen=True)
class PromptTurn:
    text: str
    prompt: str


@dataclass(frozen=True)
class GenerationSettings:
    model_id: str = MODEL_IDS[0]
    width: int = 1024
    height: int = 1024
    steps: int | None = None
    cfg: float | None = None
    seed: int | None = None

    def __post_init__(self):
        if self.model_id not in MODEL_IDS:
            raise MoruError("INVALID_SETTINGS")
        for field in ("steps", "cfg"):
            if getattr(self, field) is None:
                object.__setattr__(self, field, MODEL_DEFAULTS[self.model_id][field])
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
