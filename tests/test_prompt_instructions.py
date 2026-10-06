"""Check the instructions delivered to the LLM, not a snapshot of their full wording."""

import pytest

from moru.domain import PromptTurn
from moru.prompt_instructions import TAG_REFERENCE
from moru.prompting import prompt_messages


@pytest.mark.parametrize("base", [None, "cat, sleeping"])
def test_writer_receives_a_structured_guide_and_optional_tag_vocabulary(base):
    system = prompt_messages("a cat", base)[0]["content"]
    for section in ("OUTPUT:", "INTENT:", "ENHANCE:", "BUILD:", "TAG OPTIONS", "CHECK:"):
        assert section in system
    assert "these are not a preset" in system
    assert "Plain English is preferable to a fabricated tag" in system
    assert "Do not invent a gender" in system
    assert "no humans" in system
    assert "attach its colors, clothing, action and position" in system
    assert "State counts in words, not repeated tags" in system


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


@pytest.mark.parametrize("base", [None, "forest, day"])
def test_create_and_refine_receive_the_same_optional_reference_in_system_only(base):
    messages = prompt_messages("night", base)
    assert TAG_REFERENCE in messages[0]["content"]
    assert "not a preset or exhaustive whitelist" in messages[0]["content"]
    assert all(TAG_REFERENCE not in item["content"] for item in messages[1:])
    assert "\n" not in messages[0]["content"]


@pytest.mark.parametrize(
    "section",
    [
        "Roles:", "Food:", "Vehicles:", "Weapons:", "Instruments:", "Events:",
        "Background:", "Underwear:", "Anatomy:", "Adult acts:", "Adult positions:",
        "Adult objects:", "Fluids:", "Adult state:", "Adult context:", "Visibility:",
    ],
)
def test_reference_covers_previously_missing_subject_and_adult_categories(section):
    assert section in prompt_messages("request")[0]["content"]


def test_body_and_clothing_reference_does_not_prescribe_adult_content():
    system = prompt_messages("a coat")[0]["content"]
    assert "categories do not imply one another" in system
    assert "only when explicitly requested for adults" in system
    assert "do not infer it from clothing or anatomy" in system


def test_medium_reference_uses_plain_names_instead_of_engine_weighting_parentheses():
    assert "Medium: watercolor, oil painting, pixel art, sketch." in TAG_REFERENCE
    assert "(medium)" not in TAG_REFERENCE


@pytest.mark.parametrize("base", [None, "cat, watercolor"])
def test_writer_can_enhance_presentation_while_preserving_requested_scene(base):
    system = prompt_messages("cat", base)[0]["content"]
    assert "ENHANCE: Enrich a sparse request" in system
    assert "lighting, texture, composition and a fitting visual style" in system
    assert "Preserve explicit counts, colors, clothing, actions, relationships" in system
    assert "enhance only the requested change unless broader enhancement is requested" in system
    assert "Leave unspecified style" not in system


@pytest.mark.parametrize("base", [None, "1girl, red hair, book"])
def test_flux_writer_uses_visual_sentences_and_preserves_tagged_edit_context(base):
    messages = prompt_messages("make it night", base, model_id="flux2-klein-4b")
    system = messages[0]["content"]
    assert "natural English rather than booru tags" in system
    assert TAG_REFERENCE not in system
    assert "TAG OPTIONS" not in system
    assert "FLUX" not in system
    assert "INTENT:" in system and "ENHANCE:" in system
    assert "attach" in system.lower()
    if base:
        assert "retain its visual meaning in natural English" in system
        assert "Return the entire revised prompt, never a patch" in system
        assert base in messages[-1]["content"]
        assert "Two black cats" not in system


def test_flux_writer_keeps_real_history_and_never_inserts_examples_as_turns():
    history = (PromptTurn("a forest", "forest, sunlight"),)
    messages = prompt_messages("night", "forest, sunlight", history, "flux2-klein-4b")
    assert [item["role"] for item in messages] == ["system", "user", "assistant", "user"]
    assert messages[1:3] == [
        {"role": "user", "content": "a forest"},
        {"role": "assistant", "content": "forest, sunlight"},
    ]
    assert "forest, sunlight" in messages[-1]["content"]
