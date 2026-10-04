from threading import Event
from unittest.mock import Mock

import pytest

from moru.config import ModelPaths
from moru.domain import PromptSettings
from moru.errors import MoruError
from moru.prompting import (
    CREATE_SYSTEM,
    REFINE_SYSTEM,
    LlamaPrompts,
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
    llm = Mock()
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
    llm = Mock()
    llm.create_chat_completion.side_effect = lambda **kwargs: completion(content)
    prompts = LlamaPrompts(paths, load_llama=Mock(return_value=llm))
    assert prompts.create("girl", PromptSettings(thinking=True)) == "night, girl"


def test_truncated_llm_output_is_not_used_as_a_complete_image_prompt(tmp_path):
    paths = ModelPaths(tmp_path)
    model = paths.get("prompt")
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fake gguf")
    llm = Mock()
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
    llm = Mock(metadata={})
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
    llm = Mock(metadata={"tokenizer.chat_template": template})
    llm.token_eos.return_value = 2
    llm.token_bos.return_value = -1
    llm.detokenize.return_value = b"<eos>"
    llm.create_chat_completion.side_effect = lambda **kwargs: completion("girl")
    formatter = Mock(side_effect=lambda **kwargs: Mock(to_chat_handler=lambda: kwargs))
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
    llm = Mock(metadata={})
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

    llm = Mock(metadata={})
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
    llm = Mock(metadata={})
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
