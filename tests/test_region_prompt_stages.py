from threading import Event

import pytest

from moru.errors import MoruError
from moru.prompts.region import (
    RegionPrompts,
    region_messages,
    scene_messages,
    validate_edit_prompt,
    write_region_prompts,
)


def local_region_writer(tmp_path, monkeypatch, replies, *, tag_search=None):
    from types import SimpleNamespace

    from support.llama import completion

    from moru.config import ModelPaths
    from moru.prompts.local import LlamaPrompts

    calls, responses = [], iter(replies)

    def complete(**options):
        calls.append(options)
        return completion(list("</think>" + next(responses)))

    writer = LlamaPrompts(ModelPaths(tmp_path), tag_search=tag_search)
    monkeypatch.setattr(writer, "_load", lambda _: SimpleNamespace(
        create_chat_completion=complete, tokenize=lambda text, **_: list(text),
        token_eos=lambda: -1,
    ))
    monkeypatch.setattr(writer, "_configure_thinking", lambda *_: None)
    monkeypatch.setattr(writer, "_count_tokens", lambda *_: 100)
    return writer, calls


def test_each_stage_receives_its_own_complete_text_task():
    source, request = "A woman holds a white cup.", "Change this cup to blue"
    region = region_messages(source, request)
    scene = scene_messages(source, request, "blue cup")
    assert region[1:] == [{
        "role": "user",
        "content": (
            f"Scene context (reference only):\n{source}\n\n"
            f"Requested local change:\n{request}\n\nDescribe only the resulting edited content:"
        ),
    }]
    assert scene[1:] == [{
        "role": "user", "content": (
            f"Scene before editing:\n{source}\n\nRequested change:\n{request}\n\n"
            "Edited region prompt:\nblue cup\n\nWrite the complete updated scene:"
        ),
    }]
    assert region[0]["content"] != scene[0]["content"]


def test_examples_end_before_the_output_contract_for_the_current_input():
    tasks = [
        region_messages("A woman holds a white cup.", "Make the cup blue"),
        scene_messages("A woman holds a white cup.", "Make the cup blue", "blue cup"),
    ]
    for messages in tasks:
        assert messages[0]["content"].count("<example>") == 1
        assert messages[0]["content"].count("</example>") == 1
        instructions, example_start, remainder = messages[0]["content"].partition("<example>")
        example, example_end, contract = remainder.rpartition("</example>")
        assert instructions and example_start and example_end and example
        assert "current user input" in contract
        assert "plain English text" in contract
        assert "only the image prompt" in contract and "one paragraph" in contract
        assert len(messages) == 2


def test_region_task_prioritizes_visual_tags_and_limits_supplemental_prose():
    instructions = region_messages("A woman wears a white scarf.", "Make the scarf blue")[0][
        "content"
    ]
    assert "led by comma-separated visual tags for the edited content" in instructions
    assert "lowercase tags with spaces" in instructions
    assert "relevant search results when provided" in instructions
    assert (
        "Add a brief English sentence only for essential attributes or relations that tags "
        "cannot express."
    ) in instructions
    example = instructions.split("<example>\n", 1)[1].split("</example>", 1)[0]
    assert "Requested local change: Make the bow blue.\n" in example
    assert "Output: blue bow, polka dot\n" in example


def test_region_scope_is_the_requested_part_and_only_necessary_immediate_context():
    instructions = region_messages(
        "A woman in a white coat holds a leather bag by a station window.",
        "Make the buckle gold",
    )[0]["content"]
    assert "smallest subject or part identified by Requested local change" in instructions
    assert "Scene context resolves that target and its existing local properties" in instructions
    assert (
        "Each output detail must describe the target itself or an immediate physical connection "
        "needed to place or join it to its surroundings. Keep that connection minimal."
    ) in instructions
    assert "a single tag is sufficient when complete" in instructions


def test_cloud_region_writer_streams_two_text_tasks_without_images_or_tools():
    from support.chatgpt import SETTINGS, Auth, Responses, completed, delta

    from moru.chatgpt.prompts import ChatGPTPrompts

    region, scene = "cup, blue cup", "A woman holds a blue cup."
    http = Responses(
        [*[delta(char) for char in region], completed()],
        [*[delta(char) for char in scene], completed()],
    )
    previews, ready = [], []
    result = ChatGPTPrompts(Auth(), http).edit_region(
        "A woman holds a white cup.", "Change this cup to blue", SETTINGS, Event(),
        on_progress=lambda *p: previews.append(p), on_ready=lambda: ready.append(True),
    )
    assert result == RegionPrompts(region, scene)
    assert ready == [True]
    assert len(http.calls) == 2
    assert http.calls[0][1]["input"] == region_messages(
        "A woman holds a white cup.", "Change this cup to blue",
    )[1:]
    assert http.calls[1][1]["input"] == scene_messages(
        "A woman holds a white cup.", "Change this cup to blue", region,
    )[1:]
    assert all("tools" not in payload and "text" not in payload for _, payload in http.calls)
    assert ("scene", region, "") in previews
    assert previews[-1] == ("scene", region, scene)
    assert http.closed == 2


@pytest.mark.parametrize("thinking", [False, True])
def test_local_writer_uses_two_plain_text_calls_and_passes_the_resolved_region_forward(
    tmp_path, monkeypatch, thinking,
):
    from moru.domain import PromptSettings

    source = "A woman in an orange scarf holds a white cup."
    region, scene = "cup, blue cup", "A woman in an orange scarf holds a blue cup."
    writer, calls = local_region_writer(tmp_path, monkeypatch, [region, scene])
    previews, ready = [], []
    configured = []
    monkeypatch.setattr(writer, "_configure_thinking", lambda _, value: configured.append(value))
    result = writer.edit_region(
        source, "Make the cup blue", PromptSettings(thinking=thinking), Event(),
        on_ready=lambda: ready.append(True), on_progress=lambda *p: previews.append(p),
    )
    assert result == RegionPrompts(region, scene)
    assert ready == [True]
    assert configured == [thinking, thinking]
    assert len(calls) == 2
    assert calls[0]["messages"] == region_messages(source, "Make the cup blue")
    assert calls[1]["messages"] == scene_messages(source, "Make the cup blue", region)
    assert all("response_format" not in call and "grammar" not in call for call in calls)
    assert previews[-1] == ("scene", region, scene)
    assert ("scene", region, "") in previews
    assert any(stage == "region" and text and not full for stage, text, full in previews)


@pytest.mark.parametrize("source,change_request,region,scene", [
    ("camera, holding camera. A girl holds a camera.", "Replace the camera with a console",
     "game console held by a girl", "game console, holding game console. A girl holds a console."),
    ("A round red ceramic cup with a gold rim.", "Make the cup blue",
     "round blue ceramic cup with a gold rim", "A round blue ceramic cup with a gold rim."),
    ("red cup, red cup", "Make the second cup blue", "blue cup on the right", "red cup, blue cup"),
    ("Three dogs sit beside a green sofa.", "Replace the dogs with a cat",
     "a cat beside a green sofa", "A cat sits beside a green sofa."),
    ("(caf\u00e9:1.2), 1girl. A white cup.", "Make the cup blue", "blue cup",
     "(caf\u00e9:1.2), 1girl. A blue cup."),
    ('A sign reads "OPEN". Watercolor.', "Change the lettering to CLOSED",
     '"CLOSED" lettering', 'A sign reads "CLOSED". Watercolor.'),
    ("A white wall beside a shelf.", "Add a painting", "framed painting on a white wall",
     "A framed painting hangs on a white wall beside a shelf."),
    ("no people, A quiet park.", "Add a woman", "a woman in a park",
     "A woman stands in a quiet park."),
    ("A silver key lies on a wooden desk.", "Remove the key", "wooden desk surface",
     "A bare wooden desk."),
])
def test_each_stage_receives_its_context_and_returns_the_complete_prompt(
    source, change_request, region, scene,
):
    calls = []

    def write(stage, messages, progress):
        calls.append((stage, messages))
        text = region if stage == "region" else scene
        progress(text)
        return text

    assert write_region_prompts(source, change_request, write) == RegionPrompts(region, scene)
    assert calls == [
        ("region", region_messages(source, change_request)),
        ("scene", scene_messages(source, change_request, region)),
    ]


@pytest.mark.parametrize("reply", [
    "", " ", None, {}, "blue\ncup", "blue\rcup", '{"region_prompt":"blue cup"}',
    chr(96) * 3 + "blue cup" + chr(96) * 3, "Final answer: blue cup",
    "\uD30C\uB780 \uCEF5", "<think>blue cup",
])
def test_invalid_text_replies_fail_instead_of_using_the_original_prompt(reply):
    with pytest.raises(MoruError) as failure:
        validate_edit_prompt(reply)
    assert failure.value.code == "REGION_INVALID_RESPONSE"


@pytest.mark.parametrize("stage", ["region", "scene"])
def test_invalid_stage_output_stops_without_a_repair_call(tmp_path, monkeypatch, stage):
    from moru.domain import PromptSettings

    writer, calls = local_region_writer(
        tmp_path, monkeypatch, ["{}"] if stage == "region" else ["blue cup", "{}"],
    )
    with pytest.raises(MoruError) as failure:
        writer.edit_region("A red cup.", "Make it blue", PromptSettings(), Event())
    assert failure.value.code == "REGION_INVALID_RESPONSE"
    assert len(calls) == (1 if stage == "region" else 2)


@pytest.mark.parametrize("provider", ["local", "chatgpt"])
def test_cancellation_between_stages_prevents_the_second_inference(
    tmp_path, monkeypatch, provider,
):
    from support.chatgpt import SETTINGS, Auth, Responses, completed, delta

    from moru.chatgpt.prompts import ChatGPTPrompts
    from moru.domain import PromptSettings

    if provider == "local":
        writer, calls = local_region_writer(tmp_path, monkeypatch, ["blue cup"])
        settings = PromptSettings()
    else:
        http = Responses([delta("blue cup"), completed()])
        writer, calls, settings = ChatGPTPrompts(Auth(), http), http.calls, SETTINGS
    cancelled = Event()

    def progress(stage, *_):
        if stage == "scene":
            cancelled.set()

    with pytest.raises(MoruError) as failure:
        writer.edit_region(
            "A white cup.", "Make it blue", settings, cancelled, on_progress=progress,
        )
    assert failure.value.code == "GENERATION_CANCELLED"
    assert len(calls) == 1


def test_second_stage_context_is_checked_before_inference(tmp_path, monkeypatch):
    from moru.domain import PromptSettings

    writer, calls = local_region_writer(tmp_path, monkeypatch, ["blue cup"])
    monkeypatch.setattr(
        writer, "_count_tokens",
        lambda _, messages, __: 4096 if "Edited region prompt:" in messages[-1]["content"] else 100,
    )
    ready = []
    with pytest.raises(MoruError) as failure:
        writer.edit_region(
            "A white cup.", "Make it blue", PromptSettings(), Event(),
            on_ready=lambda: ready.append(True),
        )
    assert failure.value.code == "PROMPT_CONTEXT_TOO_LONG"
    assert len(calls) == 1
    assert ready == [True]


@pytest.mark.parametrize("stage", ["region", "scene"])
def test_truncation_in_either_stage_fails_without_returning_a_partial_pair(
    tmp_path, monkeypatch, stage,
):
    from types import SimpleNamespace

    from support.llama import completion

    from moru.domain import PromptSettings

    writer, calls = local_region_writer(tmp_path, monkeypatch, [])
    responses = iter([completion("blue cup", "length")] if stage == "region" else [
        completion("blue cup"), completion("A woman holds", "length"),
    ])

    def complete(**options):
        calls.append(options)
        return next(responses)

    monkeypatch.setattr(writer, "_load", lambda _: SimpleNamespace(
        create_chat_completion=complete, tokenize=lambda text, **_: list(text),
        token_eos=lambda: -1,
    ))
    with pytest.raises(MoruError) as failure:
        writer.edit_region("A white cup.", "Make it blue", PromptSettings(), Event())
    assert failure.value.code == "PROMPT_OUTPUT_TOO_LONG"
    assert len(calls) == (1 if stage == "region" else 2)


@pytest.mark.parametrize("enabled", [False, True])
def test_region_writer_searches_tags_before_local_writing_and_reuses_the_result(
    tmp_path, monkeypatch, enabled,
):
    import json
    from types import SimpleNamespace

    from moru.domain import PromptSettings
    from moru.prompts.tag_search import TagSearch

    queries = []

    def search(query, _limit, _cancelled):
        queries.append(query)
        return ["blue_cup"]

    replies = ["blue cup", "A woman holds a blue cup."]
    if enabled:
        replies.insert(0, "cup, blue")
    writer, calls = local_region_writer(
        tmp_path, monkeypatch, replies,
        tag_search=TagSearch(SimpleNamespace(search_tags=search)),
    )
    sources, stages, previews = [], [], []
    result = writer.edit_region(
        "A woman holds a red cup.", "Make the cup blue",
        PromptSettings(tag_search_enabled=enabled), Event(),
        on_source=sources.append, on_stage=lambda *p: stages.append(p),
        on_progress=lambda *p: previews.append(p),
    )
    assert result == RegionPrompts("blue cup", "A woman holds a blue cup.")
    assert len(calls) == (3 if enabled else 2)
    if enabled:
        assert queries == ["cup", "blue"]
        assert calls[0]["messages"][1:] == calls[1]["messages"][1:]
        assert "blue_cup" in calls[1]["messages"][0]["content"]
        assert calls[1]["messages"][0]["content"].startswith(
            region_messages("A woman holds a red cup.", "Make the cup blue")[0]["content"],
        )
        assert "blue_cup" not in calls[2]["messages"][0]["content"]
        assert [json.loads(s.result_json) for s in sources] == [["blue_cup"], ["blue_cup"]]
        assert stages[0] == ("searching_tags", 0)
        assert stages[-1] == ("prompting", 1)
        assert not any(text == "cup, blue" for _, text, _ in previews)
    else:
        assert queries == sources == stages == []
    assert previews[-1] == ("scene", result.region_prompt, result.scene_prompt)


@pytest.mark.parametrize("unavailable", [False, True])
def test_region_cloud_writer_uses_the_existing_tool_loop_only_for_the_local_prompt(unavailable):
    import json

    from support.chatgpt import SETTINGS, Auth, Responses, Tools, call, completed, delta

    from moru.chatgpt.instructions import TAG_GUIDANCE
    from moru.chatgpt.prompts import ChatGPTPrompts

    function = call(arguments={"query": "blue cup", "limit": 20})
    http = Responses(
        [delta("I'll look up the tag."), completed(function)],
        [delta("blue cup" + chr(96)), completed()],
        [delta("A woman holds a blue cup." + chr(96)), completed()],
    )
    tools = Tools({"error": "lookup_unavailable"} if unavailable else ["blue_cup"])
    sources, stages, previews = [], [], []
    result = ChatGPTPrompts(Auth(), http, tag_tools=tools).edit_region(
        "A woman holds a red cup.", "Make the cup blue", SETTINGS, Event(),
        on_source=sources.append, on_stage=lambda *p: stages.append(p),
        on_progress=lambda *p: previews.append(p),
    )
    assert result == RegionPrompts("blue cup", "A woman holds a blue cup.")
    assert len(http.calls) == 3
    assert tools.calls == [("search_tags", {"query": "blue cup", "limit": 20})]
    first, tool_reply, scene = [payload for _, payload in http.calls]
    assert first["instructions"] == (
        region_messages("A woman holds a red cup.", "Make the cup blue")[0]["content"]
        + TAG_GUIDANCE
    )
    assert tool_reply["instructions"].startswith(first["instructions"])
    assert first["tools"] == tools.definitions()
    assert tool_reply["input"][-1]["type"] == "function_call_output"
    assert json.loads(tool_reply["input"][-1]["output"]) == tools.result
    assert "tools" not in scene
    assert scene["input"] == scene_messages(
        "A woman holds a red cup.", "Make the cup blue", "blue cup",
    )[1:]
    assert len(sources) == 1
    assert json.loads(sources[0].result_json) == tools.result
    assert ("searching_tags", 0) in stages
    assert stages[-1] == ("prompting", 0 if unavailable else 1)
    assert not any("I'll look up" in region for _, region, _ in previews)
    assert previews[-1] == ("scene", result.region_prompt, result.scene_prompt)


def test_region_lookup_cancellation_does_not_start_prompt_writing(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from moru.domain import PromptSettings
    from moru.prompts.tag_search import TagSearch

    cancelled = Event()

    def search(*_):
        cancelled.set()
        return ["blue_cup"]

    writer, calls = local_region_writer(
        tmp_path, monkeypatch, ["cup"],
        tag_search=TagSearch(SimpleNamespace(search_tags=search)),
    )
    with pytest.raises(MoruError) as failure:
        writer.edit_region("A red cup.", "Make the cup blue", PromptSettings(), cancelled)
    assert failure.value.code == "GENERATION_CANCELLED"
    assert len(calls) == 1
