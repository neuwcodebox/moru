"""Check the instructions delivered to the LLM, not a snapshot of their full wording."""

import pytest

from moru.domain import PromptTurn
from moru.prompting import prompt_messages


@pytest.mark.parametrize("base", [None, "cat, sleeping"])
def test_writer_receives_a_structured_guide_and_optional_tag_vocabulary(base):
    system = prompt_messages("a cat", base)[0]["content"]
    for section in ("OUTPUT:", "INTENT:", "BUILD:", "TAG OPTIONS", "CHECK:"):
        assert section in system
    assert "these are not a preset" in system
    assert "Plain English is preferable to a fabricated tag" in system
    assert "Do not invent a gender" in system
    assert "no humans" in system
    assert "attach its colors, clothing, action and position" in system
    assert "State counts in words, not repeated tags" in system
    assert "Leave unspecified style, lighting, camera view and clothing unspecified" in system


def test_create_examples_teach_animal_counts_and_binding_each_persons_attributes():
    system = prompt_messages("a landscape")[0]["content"]
    assert "Two black cats" in system
    assert "1girl, 1boy, book" in system
    assert "The man has black hair and wears a blue jacket" in system


def test_refine_example_replaces_time_and_retains_subject_clothing_and_setting():
    system = prompt_messages("make it night", "dog, daytime")[0]["content"]
    assert "Return the entire revised prompt, never a patch" in system
    assert "Replace conflicting old details rather than appending opposites" in system
    assert "A brown dog wearing a red scarf stands in the snow at night" in system
    assert "Two black cats" not in system  # Creation-only examples spend no edit context.


@pytest.mark.parametrize("model_id", ["anima-turbo-v1.1", "anima-aesthetic-v1.1"])
def test_examples_stay_in_system_instructions_and_never_become_fake_user_history(model_id):
    history = (PromptTurn("a forest", "forest, sunlight"),)
    messages = prompt_messages("make it night", "forest, sunlight", history, model_id)
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    assert messages[1:3] == [
        {"role": "user", "content": "a forest"},
        {"role": "assistant", "content": "forest, sunlight"},
    ]
    assert "Anima" not in messages[0]["content"]
    assert (
        "Add rating tags (safe, sensitive, nsfw, explicit) only when requested"
        in (messages[0]["content"])
    )
    assert "Prefix requested artist tags with @" in messages[0]["content"]
