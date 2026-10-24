"""Engine-independent conversation text and final image-prompt validation."""

import unicodedata

from moru.domain import PromptTurn
from moru.errors import MoruError


def conversation_messages(
    text: str, base_prompt: str | None = None, history: tuple[PromptTurn, ...] = ()
) -> list[dict[str, str]]:
    messages = []
    for turn in history:
        messages.extend(
            [{"role": "user", "content": turn.text}, {"role": "assistant", "content": turn.prompt}]
        )
    content = (
        text
        if base_prompt is None
        else (f"Existing image prompt:\n{base_prompt}\n\nChange request:\n{text}")
    )
    messages.append({"role": "user", "content": content})
    return messages


def final_prompt(content: str) -> str:
    prompt = content.strip()
    if not prompt:
        raise MoruError("PROMPT_EMPTY_RESPONSE")
    if "<think>" in prompt or prompt.startswith("Thinking Process:"):
        raise MoruError("PROMPT_INVALID_RESPONSE")
    if any(char.isalpha() and "LATIN" not in unicodedata.name(char, "") for char in prompt):
        raise MoruError("PROMPT_NON_ENGLISH_RESPONSE")
    return prompt
