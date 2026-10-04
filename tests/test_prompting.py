from threading import Event
from unittest.mock import Mock

import pytest

from moru.config import ModelPaths
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.prompting import (
    CREATE_SYSTEM,
    REFINE_SYSTEM,
    LlamaPrompts,
    ThinkingBudget,
    fit_messages,
    prompt_messages,
    read_completion,
)


def completion(content, finish_reason="stop"):
    yield {"choices": [{"delta": {"content": content}, "finish_reason": None}]}
    yield {"choices": [{"delta": {}, "finish_reason": finish_reason}]}


def test_create_receives_only_system_and_new_request():
    assert prompt_messages("은발 소녀") == [
        {"role": "system", "content": CREATE_SYSTEM},
        {"role": "user", "content": "은발 소녀"},
    ]


def test_refinement_receives_canonical_prompt_and_change_not_conversation_history():
    messages = prompt_messages("밤으로", "silver hair, daytime")
    assert messages == [
        {"role": "system", "content": REFINE_SYSTEM},
        {
            "role": "user",
            "content": "Existing image prompt:\nsilver hair, daytime\n\nChange request:\n밤으로",
        },
    ]


def test_model_load_is_lazy_cuda_and_reload_follows_unload(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("night, girl")
    load = Mock(return_value=llm)
    prompts = LlamaPrompts(paths, load_llama=load)
    load.assert_not_called()
    assert prompts.create("girl", PromptSettings(thinking=True)) == "night, girl"
    assert prompts.refine("girl", "night", PromptSettings(thinking=True)) == "night, girl"
    load.assert_called_once_with(model_path=str(model), n_gpu_layers=-1, n_ctx=2048, verbose=False)
    prompts.unload()
    llm.close.assert_called_once()
    prompts.create("girl", PromptSettings(thinking=True))
    assert load.call_count == 2


def test_missing_model_is_explicit_and_does_not_call_another_model(tmp_path):
    load = Mock()
    with pytest.raises(MoruError) as error:
        LlamaPrompts(ModelPaths(tmp_path), load_llama=load).create(
            "girl", PromptSettings(thinking=True)
        )
    assert error.value.code == "PROMPT_MODEL_NOT_FOUND"
    load.assert_not_called()


@pytest.mark.parametrize(
    "content",
    ["<think>private reasoning</think>\nnight, girl", "private reasoning</think>\nnight, girl"],
)
def test_reasoning_is_not_forwarded_as_an_image_prompt(tmp_path, content):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: completion(content)
    prompts = LlamaPrompts(paths, load_llama=Mock(return_value=llm))
    assert prompts.create("girl", PromptSettings(thinking=True)) == "night, girl"


def test_truncated_llm_output_is_not_used_as_a_complete_image_prompt(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: completion(
        "Thinking Process: ...", "length"
    )
    with pytest.raises(MoruError) as error:
        LlamaPrompts(paths, load_llama=Mock(return_value=llm)).create(
            "girl", PromptSettings(thinking=True)
        )
    assert error.value.code == "PROMPT_LLM_FAILED"


def test_context_change_reloads_the_model_but_output_limit_change_reuses_it(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(metadata={}, tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("girl")
    load = Mock(return_value=llm)
    prompts = LlamaPrompts(paths, load_llama=load)
    prompts.create("girl", PromptSettings(thinking=True))
    prompts.create("girl", PromptSettings(max_tokens=1536, thinking=True))
    assert load.call_count == 1
    assert llm.create_chat_completion.call_args.kwargs["max_tokens"] == 1536
    prompts.create("girl", PromptSettings(context_size=4096, max_tokens=2048, thinking=True))
    llm.close.assert_called_once()
    assert load.call_count == 2
    assert load.call_args.kwargs["n_ctx"] == 4096


def test_thinking_toggle_uses_the_model_template_and_can_be_enabled_again(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    template = "{% if enable_thinking %}<think>{% else %}</think>{% endif %}"
    llm = Mock(metadata={"tokenizer.chat_template": template}, tokenize=lambda *args, **kwargs: [0])
    llm.token_eos.return_value = 2
    llm.token_bos.return_value = -1
    llm.detokenize.return_value = b"<eos>"
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("girl")
    formatter = Mock(
        side_effect=lambda **kwargs: Mock(
            to_chat_handler=lambda: kwargs,
            return_value=SimpleNamespace(prompt="formatted", added_special=True),
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "llama_cpp.llama_chat_format",
        SimpleNamespace(
            Jinja2ChatFormatter=formatter,
        ),
    )
    load = Mock(return_value=llm)
    prompts = LlamaPrompts(paths, load_llama=load)
    prompts.create("girl", PromptSettings(thinking=False))
    assert llm.chat_handler["template"] == "{% set enable_thinking = false %}\n" + template
    assert llm.chat_handler["stop_token_ids"] == [2]
    prompts.refine("girl", "night", PromptSettings(thinking=True))
    assert llm.chat_handler["template"] == "{% set enable_thinking = true %}\n" + template
    load.assert_called_once()


def test_disabling_thinking_on_an_unsupported_model_fails_explicitly(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(metadata={}, tokenize=lambda *args, **kwargs: [0])
    prompts = LlamaPrompts(paths, load_llama=Mock(return_value=llm))
    with pytest.raises(MoruError) as error:
        prompts.create("girl", PromptSettings(thinking=False))
    assert error.value.code == "THINKING_UNSUPPORTED"
    llm.create_chat_completion.assert_not_called()


def test_cancelling_thinking_stops_reading_tokens_and_closes_the_completion(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    cancelled = Event()
    consumed = []
    closed = []

    def tokens():
        try:
            consumed.append("first")
            yield {"choices": [{"delta": {"content": "<think>reasoning"}, "finish_reason": None}]}
            cancelled.set()
            consumed.append("second")
            yield {"choices": [{"delta": {"content": " more reasoning"}, "finish_reason": None}]}
            consumed.append("unwanted")
        finally:
            closed.append(True)

    llm = Mock(metadata={}, tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: tokens()
    prompts = LlamaPrompts(paths, load_llama=Mock(return_value=llm))
    with pytest.raises(MoruError) as error:
        prompts.create("girl", PromptSettings(thinking=True), cancelled=cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert consumed == ["first", "second"]
    assert closed == [True]


def test_a_cancelled_prompt_does_not_load_the_model(tmp_path):
    load = Mock()
    cancelled = Event()
    cancelled.set()
    with pytest.raises(MoruError) as error:
        LlamaPrompts(ModelPaths(tmp_path), load_llama=load).create(
            "girl", PromptSettings(thinking=True), cancelled=cancelled
        )
    assert error.value.code == "GENERATION_CANCELLED"
    load.assert_not_called()


def test_a_stream_without_a_normal_end_is_not_used_as_a_finished_prompt(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(metadata={}, tokenize=lambda *args, **kwargs: [0])
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("girl", None)
    with pytest.raises(MoruError) as error:
        LlamaPrompts(paths, load_llama=Mock(return_value=llm)).create(
            "girl", PromptSettings(thinking=True)
        )
    assert error.value.code == "PROMPT_LLM_FAILED"


def test_live_thinking_and_prompt_are_separated_when_control_tags_span_tokens():
    snapshots = []

    def chunks():
        for token in ("<thi", "nk>choose the scene", "</thi", "nk>silver hair, ", "night"):
            yield {"choices": [{"delta": {"content": token}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    result = read_completion(
        chunks(), Event(), True, lambda thought, prompt: snapshots.append((thought, prompt))
    )
    assert result == "silver hair, night"
    assert ("choose the scene", "") in snapshots
    assert ("choose the scene", "silver hair,") in snapshots
    assert snapshots[-1] == ("choose the scene", result)
    assert not any("<" in thought or "<" in prompt for thought, prompt in snapshots)


def test_disabling_thinking_streams_the_prompt_directly():
    snapshots = []
    assert (
        read_completion(
            completion("night, girl"),
            Event(),
            False,
            lambda thought, prompt: snapshots.append((thought, prompt)),
        )
        == "night, girl"
    )
    assert snapshots == [("", "night, girl"), ("", "night, girl")]


def test_recent_requests_and_selected_prompts_are_real_chat_turns_before_the_latest_request():
    messages = prompt_messages(
        "처음 분위기로",
        "moonlight",
        (PromptTurn("따뜻하게", "warm sunlight"), PromptTurn("밤으로", "moonlight")),
    )
    assert messages[1:5] == [
        {"role": "user", "content": "따뜻하게"},
        {"role": "assistant", "content": "warm sunlight"},
        {"role": "user", "content": "밤으로"},
        {"role": "assistant", "content": "moonlight"},
    ]
    assert (
        messages[-1]["content"]
        == "Existing image prompt:\nmoonlight\n\nChange request:\n처음 분위기로"
    )
    assert "Anima" not in messages[0]["content"]


def test_aesthetic_instructions_omit_score_tags_without_naming_the_model():
    system = prompt_messages("forest", model_id="anima-aesthetic-v1.1")[0]["content"]
    assert "Omit score_* tags" in system
    assert "Anima" not in system


def test_context_budget_removes_oldest_complete_turns_but_preserves_current_state():
    messages = [
        {"role": "system", "content": "guide"},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "old result"},
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent result"},
        {"role": "user", "content": "canonical state and latest request"},
    ]
    fitted = fit_messages(messages, lambda items: len(items) * 10, 40)
    assert fitted == [messages[0], messages[3], messages[4], messages[5]]
    assert len(messages) == 6


def test_oversized_current_state_fails_explicitly_instead_of_being_truncated():
    with pytest.raises(MoruError) as failure:
        fit_messages(prompt_messages("new", "canonical"), lambda items: 101, 100)
    assert failure.value.code == "PROMPT_CONTEXT_TOO_LONG"


@pytest.mark.parametrize("content", ["은발 소녀, night", "少女, night", "девушка"])
def test_non_english_script_is_not_forwarded_to_the_image_model(content):
    with pytest.raises(MoruError):
        read_completion(completion(content), Event())


class Scores(list):
    """Small stand-in for the mutable logit array, without inference dependencies."""

    def __setitem__(self, key, value):
        super().__setitem__(key, [value] * len(self) if isinstance(key, slice) else value)


def test_reasoning_budget_closes_thinking_and_leaves_final_prompt_tokens_unrestricted():
    processor = ThinkingBudget([3], 2)
    scores = Scores([1.0] * 5)
    assert processor([9, 3], scores) == [1.0] * 5  # A history marker isn't generated reasoning.
    assert processor([9, 3, 1], scores) == [1.0] * 5
    assert processor([9, 3, 1, 2], scores) == [float("-inf")] * 3 + [0.0, float("-inf")]
    final_scores = Scores([1.0] * 5)
    assert processor([9, 3, 1, 2, 3, 4], final_scores) == [1.0] * 5


def test_naturally_completed_thinking_is_not_extended_to_fill_the_budget():
    processor = ThinkingBudget([3], 10)
    processor([9], Scores([1.0] * 5))
    assert processor([9, 1, 3, 2], Scores([1.0] * 5)) == [1.0] * 5


def test_a_multi_token_thinking_marker_is_completed_in_order():
    processor = ThinkingBudget([3, 4], 1)
    processor([9], Scores([1.0] * 5))
    assert processor([9, 1], Scores([1.0] * 5))[3] == 0.0
    assert processor([9, 1, 3], Scores([1.0] * 5))[4] == 0.0
    assert processor([9, 1, 3, 4], Scores([1.0] * 5)) == [1.0] * 5


def test_forced_reasoning_end_completes_the_final_answer_cue_before_releasing_sampling():
    processor = ThinkingBudget([3], 1, [4])
    processor([9], Scores([1.0] * 5))
    assert processor([9, 1], Scores([1.0] * 5))[3] == 0.0
    assert processor([9, 1, 3], Scores([1.0] * 5))[4] == 0.0
    assert processor([9, 1, 3, 4], Scores([1.0] * 5)) == [1.0] * 5


def test_final_answer_cue_is_removed_from_both_live_text_and_the_image_prompt():
    snapshots = []

    def chunks():
        for token in ("reasoning</think>\n\nFinal", " image prompt:\n", "black cat, moonlight"):
            yield {"choices": [{"delta": {"content": token}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    result = read_completion(chunks(), Event(), True, lambda *text: snapshots.append(text))
    assert result == "black cat, moonlight"
    assert snapshots[:2] == [("reasoning", ""), ("reasoning", "")]
    assert snapshots[-1] == ("reasoning", result)


def test_reasoning_level_changes_the_completion_budget_without_reloading_the_model(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock(
        metadata={},
        tokenize=lambda text, **kwargs: [3] if text == b"</think>" else [4],
    )
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("girl")
    load = Mock(return_value=llm)
    prompts = LlamaPrompts(paths, load_llama=load)
    for level, budget in (("low", 128), ("high", 512)):
        prompts.create("girl", PromptSettings(reasoning_level=level))
        processor = llm.create_chat_completion.call_args.kwargs["logits_processor"][0]
        processor([9], Scores([1.0] * 5))
        assert processor([9] + [1] * (budget - 2), Scores([1.0] * 5))[3] == 0.0
    load.assert_called_once()
