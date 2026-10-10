"""Documented reasoning choices; unknown account model aliases keep their default."""

import re

from moru.domain import PromptSettings
from moru.errors import MoruError

# https://developers.openai.com/api/docs/guides/deployment-checklist
# https://developers.openai.com/api/docs/models/gpt-5.4
# https://developers.openai.com/api/docs/models/gpt-5.5
REASONING_EFFORTS = {
    "gpt-6-astra": ("low", "medium", "high", "xhigh", "max"),
    "gpt-6.1-sol": ("low", "medium", "high", "xhigh", "max"),
    "gpt-6-sol": ("none", "low", "medium", "high", "xhigh", "max"),
    "gpt-6-luna": ("none", "low", "medium", "high", "xhigh", "max"),
    "gpt-5.4": ("none", "low", "medium", "high", "xhigh"),
    "gpt-5.5": ("none", "low", "medium", "high", "xhigh"),
    "o3": ("low", "medium", "high"),
}


def reasoning_efforts(model: str) -> tuple[str, ...]:
    if not isinstance(model, str):
        raise MoruError("INVALID_SETTINGS")
    for name, efforts in REASONING_EFFORTS.items():
        if model == name or re.fullmatch(re.escape(name) + r"-\d{4}-\d{2}-\d{2}", model):
            return efforts
    return ()


def validate_chatgpt_options(settings: PromptSettings) -> None:
    if settings.chatgpt_reasoning_effort != "default" and (
        settings.chatgpt_reasoning_effort not in reasoning_efforts(settings.chatgpt_model)
    ):
        raise MoruError("CHATGPT_UNSUPPORTED")
