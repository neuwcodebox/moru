"""Two focused text-writing stages for an image edit."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from moru.errors import MoruError
from moru.prompts.text import answer_text, final_prompt

_PROMPT_OUTPUT = (
    "\nReturn only the image prompt for the current user input "
    "as one paragraph of plain English text."
)

REGION_SYSTEM = (
    "Task: write an inpainting prompt for the smallest subject or part identified by "
    "Requested local change, in its final state. "
    "Scene context resolves that target and its existing local properties. "
    "Each output detail must describe the target itself or an immediate physical connection "
    "needed to place or join it to its surroundings. Keep that connection minimal. "
    "For removal, describe the exposed surface. "
    "Output: a short positive English prompt led by comma-separated visual tags for the "
    "edited content. Use lowercase tags with spaces and relevant search results when provided. "
    "Use only the tags needed for this local result; a single tag is sufficient when complete. "
    "Add a brief English sentence only for essential attributes or relations that tags "
    "cannot express.\n"
    "<example>\n"
    "Scene context: A woman in a white coat carries a brown bag decorated with a red "
    "polka dot bow beside a station window.\n"
    "Requested local change: Make the bow blue.\n"
    "Output: blue bow, polka dot\n"
    "</example>"
) + _PROMPT_OUTPUT

SCENE_SYSTEM = (
    "Task: write the complete final scene for the current input. "
    "Scene before editing is its initial state; Requested change specifies the modification; "
    "Edited region prompt describes the resolved local result. Keep unaffected visual details "
    "and make all tags, sentences, actions, counts and absence claims consistent with that result. "
    "Output: the complete positive English description of the resulting scene.\n"
    "<example>\n"
    "Scene before editing: lamp, holding lamp. A sailor carries a brass lamp beside a mast.\n"
    "Requested change: Replace the lamp with a globe.\n"
    "Edited region prompt: globe, holding globe\n"
    "Output: globe, holding globe. A sailor carries a globe beside a mast.\n"
    "</example>"
) + _PROMPT_OUTPUT


@dataclass(frozen=True)
class RegionPrompts:
    region_prompt: str
    scene_prompt: str


RegionPromptProgress = Callable[[Literal["region", "scene"], str, str], None]


def region_messages(scene_prompt: str, change_request: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REGION_SYSTEM},
        {"role": "user", "content": (
            f"Scene context (reference only):\n{scene_prompt}\n\n"
            f"Requested local change:\n{change_request}\n\n"
            "Describe only the resulting edited content:"
        )},
    ]


def scene_messages(
    scene_prompt: str, change_request: str, region_prompt: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SCENE_SYSTEM},
        {"role": "user", "content": (
            f"Scene before editing:\n{scene_prompt}\n\n"
            f"Requested change:\n{change_request}\n\n"
            f"Edited region prompt:\n{region_prompt}\n\n"
            "Write the complete updated scene:"
        )},
    ]


def validate_edit_prompt(content: str) -> str:
    try:
        if not isinstance(content, str):
            raise ValueError("expected text")
        prompt = content.strip()
        if "\n" in prompt or "\r" in prompt or prompt.startswith(("{", "[", "```")):
            raise ValueError("expected one prompt paragraph")
        if final_prompt(prompt) != prompt:
            raise ValueError("unexpected answer wrapper")
        return prompt
    except (ValueError, MoruError) as exc:
        raise MoruError("REGION_INVALID_RESPONSE") from exc


def write_region_prompts(scene_prompt, change_request, write, on_progress=None) -> RegionPrompts:
    """Share stage sequencing across local and cloud writers; each reply is plain text."""
    def region_progress(text):
        if on_progress is not None:
            on_progress("region", answer_text(text), "")

    region = validate_edit_prompt(
        write("region", region_messages(scene_prompt, change_request), region_progress)
    )
    if on_progress is not None:
        on_progress("scene", region, "")

    def scene_progress(text):
        if on_progress is not None:
            on_progress("scene", region, answer_text(text))

    scene = validate_edit_prompt(
        write("scene", scene_messages(scene_prompt, change_request, region), scene_progress)
    )
    return RegionPrompts(region, scene)
