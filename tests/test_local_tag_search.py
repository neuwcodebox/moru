import json
from threading import Event
from unittest.mock import Mock

import pytest
from support.llama import completion

from moru.api import Api
from moru.config import ModelPaths
from moru.danbooru.http import TagLookupError
from moru.domain import PromptSettings, PromptTurn
from moru.errors import MoruError
from moru.prompts.local import LlamaPrompts, prompt_messages
from moru.prompts.tag_search import TagSearch, add_tag_references, parse_queries


class Llama:
    metadata = {}

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def tokenize(self, text, **options):
        return [0] * max(1, len(text) // 16)

    def token_eos(self):
        return -1

    def create_chat_completion(self, **options):
        self.calls.append(options)
        reply = self.replies.pop(0)
        return reply() if callable(reply) else completion(reply)

    def close(self):
        pass


class Tags:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def search_tags(self, query, limit, cancelled):
        self.calls.append((query, limit))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result() if callable(result) else result


def writer(tmp_path, llm, tags):
    paths = ModelPaths(tmp_path)
    paths.get("prompt").parent.mkdir(parents=True, exist_ok=True)
    paths.get("prompt").write_bytes(b"fake gguf")
    load = Mock(return_value=llm)
    return LlamaPrompts(paths, load_llama=load, tag_search=TagSearch(tags)), load


@pytest.mark.parametrize("base", [None, "silver hair, daytime"])
def test_search_and_writing_share_the_request_state_but_not_generated_query_history(tmp_path, base):
    llm = Llama("<think>private query reasoning</think>\nsilver hair, night", "silver hair, night")
    tags = Tags(["silver_hair", "grey_hair"], ["night", "night_sky"])
    prompts, load = writer(tmp_path, llm, tags)
    history = (PromptTurn("a girl", "silver hair, daytime"),)
    ready, snapshots, sources, stages = Mock(), [], [], []
    context = dict(
        history=history,
        on_ready=ready,
        on_source=sources.append,
        on_stage=lambda *event: stages.append(event),
    )
    arguments = ("make it night", PromptSettings(), Event(), lambda *event: snapshots.append(event))
    result = (
        prompts.create(*arguments, **context)
        if base is None
        else prompts.refine(base, *arguments, **context)
    )

    assert result == "silver hair, night"
    assert len(llm.calls) == 2
    assert llm.calls[0]["messages"][1:] == llm.calls[1]["messages"][1:]
    assert llm.calls[1]["messages"][1:] == prompt_messages("make it night", base, history)[1:]
    query_system = llm.calls[0]["messages"][0]["content"]
    assert "separated by commas" in query_system and "TAG OPTIONS" not in query_system
    final_system = llm.calls[1]["messages"][0]["content"]
    assert "silver_hair" in final_system and "night_sky" in final_system
    assert '"silver_hair"' in final_system and '"night"' in final_system
    assert "private query reasoning" not in str(llm.calls[1]["messages"])
    assert all("private query reasoning" not in str(event) for event in snapshots)
    assert stages == [
        ("searching_tags", 0),
        ("searching_tags", 2),
        ("searching_tags", 4),
        ("prompting", 4),
    ]
    assert [(source.tool, source.query, json.loads(source.result_json)) for source in sources] == [
        ("search_tags", "silver_hair", ["silver_hair", "grey_hair"]),
        ("search_tags", "night", ["night", "night_sky"]),
    ]
    ready.assert_called_once()
    load.assert_called_once()
    assert llm.calls[0]["max_tokens"] == llm.calls[1]["max_tokens"] == 2048


@pytest.mark.parametrize("base", [None, "daytime city"])
def test_disabling_tag_search_writes_directly_without_queries_sources_or_search_progress(
    tmp_path, base
):
    llm = Llama("night, city")
    tags, sources, stages = Tags(), [], []
    prompts, _ = writer(tmp_path, llm, tags)
    settings = PromptSettings(tag_search_enabled=False)
    history = (PromptTurn("city", "daytime city"),)
    context = dict(
        history=history, on_source=sources.append, on_stage=lambda *event: stages.append(event)
    )
    result = (
        prompts.create("make it night", settings, **context)
        if base is None
        else prompts.refine(base, "make it night", settings, **context)
    )
    assert result == "night, city"
    assert len(llm.calls) == 1
    assert llm.calls[0]["messages"] == prompt_messages("make it night", base, history)
    assert tags.calls == [] and sources == [] and stages == []


def test_query_plan_is_normalized_deduplicated_and_limited():
    assert parse_queries("silver hair, Silver_Hair, night, sky, city, hat, coat") == (
        "silver_hair",
        "night",
        "sky",
        "city",
        "hat",
    )
    assert parse_queries("none") == ()
    assert parse_queries("") == ()


@pytest.mark.parametrize(
    "content",
    [
        '{"queries":["night"]}',
        '["night"]',
        "```night```",
        "rating:safe",
        "한글",
        "*",
        "night\nsky",
        "x" * 81,
        "night,,sky",
        "<think>unclosed reasoning night",
    ],
)
def test_invalid_query_output_is_not_a_search_plan(content):
    with pytest.raises(ValueError):
        parse_queries(content)


@pytest.mark.parametrize("query_reply", ["*", "none", "", "한글", "<think>unfinished reasoning"])
def test_invalid_or_empty_plan_continues_with_the_original_writing_guide(
    tmp_path, query_reply, caplog
):
    llm = Llama(query_reply, "night, city")
    tags = Tags()
    prompts, _ = writer(tmp_path, llm, tags)
    assert prompts.create("night city") == "night, city"
    assert tags.calls == []
    assert llm.calls[-1]["messages"][0]["content"] == prompt_messages("night city")[0]["content"]
    if query_reply != "none":
        assert "query plan rejected" in caplog.text
        if query_reply:
            assert query_reply not in caplog.text


def test_query_token_limit_is_optional_but_final_prompt_truncation_still_fails(tmp_path, caplog):
    llm = Llama(lambda: completion("night", "length"), "night")
    prompts, _ = writer(tmp_path, llm, Tags(["night"]))
    assert prompts.create("night") == "night"
    assert "PROMPT_OUTPUT_TOO_LONG" in caplog.text
    llm.replies.extend(["night", lambda: completion("night", "length")])
    with pytest.raises(MoruError) as failure:
        prompts.create("night")
    assert failure.value.code == "PROMPT_OUTPUT_TOO_LONG"


def test_lookup_failure_stops_further_searches_and_keeps_successful_references(tmp_path, caplog):
    llm = Llama("night, sky, city", "night, sky")
    tags = Tags(["night"], TagLookupError(), ["city"])
    sources, stages = [], []
    prompts, _ = writer(tmp_path, llm, tags)
    assert (
        prompts.create(
            "night city", on_source=sources.append, on_stage=lambda *event: stages.append(event)
        )
        == "night, sky"
    )
    assert len(tags.calls) == 2
    assert json.loads(sources[1].result_json) == {"error": "lookup_unavailable"}
    assert stages == [
        ("searching_tags", 0),
        ("searching_tags", 1),
        ("searching_tags", 1),
        ("prompting", 1),
    ]
    assert '"night"' in llm.calls[-1]["messages"][0]["content"]
    assert "lookup unavailable" in caplog.text


def test_empty_and_repeated_results_count_only_distinct_returned_names(tmp_path):
    llm = Llama("night, sky, city", "night, city")
    tags = Tags(["night", "night_sky", "night"], ["night_sky", "city"], [])
    prompts, _ = writer(tmp_path, llm, tags)
    stages = []
    prompts.create("night city", on_stage=lambda *event: stages.append(event))
    assert stages == [
        ("searching_tags", 0),
        ("searching_tags", 2),
        ("searching_tags", 3),
        ("searching_tags", 3),
        ("prompting", 3),
    ]
    final_system = llm.calls[-1]["messages"][0]["content"]
    assert final_system.count('"night_sky"') == 1


@pytest.mark.parametrize("cancel_at", ["query", "lookup", "source", "final"])
def test_cancellation_stops_the_two_stage_flow_without_hiding_it_as_optional_failure(
    tmp_path, cancel_at
):
    cancelled = Event()

    def cancel_query():
        cancelled.set()
        return completion("night")

    def lookup():
        if cancel_at == "lookup":
            cancelled.set()
        return ["night"]

    def source(_source):
        if cancel_at == "source":
            cancelled.set()

    def stage(name, _count):
        if name == "prompting" and cancel_at == "final":
            cancelled.set()

    llm = Llama(cancel_query if cancel_at == "query" else "night", "night")
    tags = Tags(lookup)
    prompts, _ = writer(tmp_path, llm, tags)
    with pytest.raises(MoruError) as failure:
        prompts.create("night", cancelled=cancelled, on_source=source, on_stage=stage)
    assert failure.value.code == "GENERATION_CANCELLED"
    assert len(llm.calls) == 1


def test_loading_failure_does_not_start_query_generation_or_report_readiness(tmp_path):
    prompts, load = writer(tmp_path, Llama(), Tags())
    load.side_effect = RuntimeError("load failed")
    ready, stage = Mock(), Mock()
    with pytest.raises(MoruError) as failure:
        prompts.create("night", on_ready=ready, on_stage=stage)
    assert failure.value.code == "MODEL_LOAD_FAILED"
    ready.assert_not_called()
    stage.assert_not_called()


def test_flux_keeps_single_pass_natural_language_writing_without_tag_search(tmp_path):
    llm = Llama("A city at night.")
    tags = Tags()
    prompts, _ = writer(tmp_path, llm, tags)
    assert prompts.create("night city", model_id="flux2-klein-4b") == "A city at night."
    assert len(llm.calls) == 1 and not tags.calls


def test_reference_budget_preserves_the_entire_request_and_retained_history():
    messages = [
        {"role": "system", "content": "guide"},
        {"role": "user", "content": "old request"},
        {"role": "assistant", "content": "old prompt"},
        {"role": "user", "content": "canonical state and new request"},
    ]

    def count(items):
        return sum(len(item["content"]) for item in items)

    baseline = count(messages)
    references = (
        ("night", ("night", "night_sky", "city_lights")),
        ("sky", ("starry_sky", "night_sky")),
    )
    augmented = add_tag_references(messages, references, count, baseline + 180, max_tokens=180)
    assert count(augmented) <= baseline + 180
    assert augmented[1:] == messages[1:]
    assert messages[0]["content"] == "guide"
    assert "night" in augmented[0]["content"]
    assert add_tag_references(messages, references, count, baseline) == messages


def test_both_llm_calls_respect_token_budget_and_share_trimmed_history(tmp_path):
    llm = Llama("night", "night")
    tags = Tags(["night", "night_sky"])
    prompts, _ = writer(tmp_path, llm, tags)
    history = tuple(PromptTurn("old " * 500, "old prompt " * 200) for _ in range(4))
    settings = PromptSettings(context_size=1024, max_tokens=256)
    assert prompts.refine("daytime", "make it night", settings, history=history) == "night"
    for call in llm.calls:
        assert (
            sum(len(llm.tokenize(item["content"].encode())) + 16 for item in call["messages"])
            <= settings.context_size - call["max_tokens"]
        )
    assert llm.calls[0]["messages"][1:] == llm.calls[1]["messages"][1:]
    assert llm.calls[-1]["messages"][-1]["content"].endswith("make it night")


@pytest.mark.parametrize("fails", [False, True])
def test_local_lookup_sources_and_phase_counts_reach_the_completed_image(app, tmp_path, fails):
    llm = Llama("night", "night")
    tags = Tags(TagLookupError() if fails else ["night", "night_sky"])
    prompts, _ = writer(tmp_path, llm, tags)
    app.prompts = prompts
    states = []
    api = Api(app)
    original_search = tags.search_tags

    def search(*arguments):
        states.append(api.get_job(job.id)["value"])
        return original_search(*arguments)

    tags.search_tags = search
    job = app.submit_request(app.create_project().id, "night")
    app.scheduler.run_next()
    completed = app.get_job(job.id)
    assert completed.state == "completed"
    assert states[0]["state"] == "searching_tags" and states[0]["prompt_text"] == ""
    expected = {"error": "lookup_unavailable"} if fails else ["night", "night_sky"]
    assert api.get_image_sources(completed.image_id)["value"] == [
        {"tool": "search_tags", "query": "night", "result": expected},
    ]
    assert completed.found_tag_count == (0 if fails else 2)


@pytest.mark.parametrize("failure_code", ["PROMPT_RESPONSE_INTERRUPTED", "PROMPT_LLM_FAILED"])
def test_query_inference_failure_remains_a_generation_failure(tmp_path, failure_code):
    def fail():
        if failure_code == "PROMPT_LLM_FAILED":
            raise RuntimeError("inference failed")
        return completion("night", None)

    llm = Llama(fail, "night")
    tags = Tags()
    prompts, _ = writer(tmp_path, llm, tags)
    with pytest.raises(MoruError) as failure:
        prompts.create("night")
    assert failure.value.code == failure_code
    assert len(llm.calls) == 1 and not tags.calls


def test_query_answer_uses_the_same_single_line_output_as_image_prompts(tmp_path):
    llm = Llama("night, sky\n\nExplanation follows.", "night, sky")
    tags = Tags(["night"], ["sky"])
    prompts, _ = writer(tmp_path, llm, tags)
    assert prompts.create("night sky") == "night, sky"
    assert [query for query, _limit in tags.calls] == ["night", "sky"]


def test_tag_counts_reset_for_each_request_and_the_loaded_model_is_reused(tmp_path):
    llm = Llama("night", "night", "city", "city")
    tags = Tags(["night", "night_sky"], ["city"])
    prompts, load = writer(tmp_path, llm, tags)
    first, second = [], []
    prompts.create("night", on_stage=lambda *event: first.append(event))
    prompts.refine("night", "city", on_stage=lambda *event: second.append(event))
    assert first[-1] == ("prompting", 2)
    assert second == [("searching_tags", 0), ("searching_tags", 1), ("prompting", 1)]
    load.assert_called_once()


@pytest.mark.parametrize("result", [[None], ["injected\ntext"], {"name": "night"}])
def test_invalid_catalog_results_are_recorded_as_failed_lookups(tmp_path, result):
    llm = Llama("night", "night")
    sources = []
    prompts, _ = writer(tmp_path, llm, Tags(result))
    assert prompts.create("night", on_source=sources.append) == "night"
    assert json.loads(sources[0].result_json) == {"error": "lookup_unavailable"}


def test_lookup_and_logging_do_not_receive_full_requests_or_private_model_output(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    llm = Llama("<think>private query reasoning</think>night", "night")
    tags = Tags(["night"])
    prompts, _ = writer(tmp_path, llm, tags)
    prompts.refine(
        "private current prompt",
        "private user request",
        history=(PromptTurn("private past request", "private past prompt"),),
    )
    assert tags.calls == [("night", 8)]
    for text in (
        "private query reasoning",
        "private current prompt",
        "private user request",
        "private past request",
        "private past prompt",
    ):
        assert text not in caplog.text
    assert "query_count=1" in caplog.text and "found_tags=1" in caplog.text


@pytest.mark.parametrize("exception", [ValueError, RuntimeError])
def test_query_engine_exceptions_are_not_hidden_as_bad_query_format(tmp_path, exception):
    def fail():
        raise exception("engine failed")

    llm = Llama(fail, "night")
    prompts, _ = writer(tmp_path, llm, Tags())
    with pytest.raises(MoruError) as failure:
        prompts.create("night")
    assert failure.value.code == "PROMPT_LLM_FAILED"
    assert len(llm.calls) == 1


def test_both_passes_budget_the_rendered_model_template_including_special_tokens(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    class Formatter:
        def __init__(self, **options):
            pass

        def to_chat_handler(self):
            return self

        def __call__(self, *, messages):
            return SimpleNamespace(
                prompt="template padding " * 100 + json.dumps(messages) + "<assistant><think>",
                added_special=True,
            )

    monkeypatch.setitem(
        sys.modules, "llama_cpp.llama_chat_format", SimpleNamespace(Jinja2ChatFormatter=Formatter)
    )
    llm = Llama("night", "night")
    llm.metadata = {"tokenizer.chat_template": "{% if enable_thinking %}<think>{% endif %}"}
    llm.token_bos = lambda: -1
    prompts, _ = writer(tmp_path, llm, Tags(["night", "night_sky"]))
    settings = PromptSettings(context_size=1024, max_tokens=256)
    history = tuple(PromptTurn("old scene " * 300, "old prompt " * 300) for _ in range(3))
    assert prompts.refine("daytime", "make it night", settings, history=history) == "night"
    for call in llm.calls:
        rendered = llm.chat_handler(messages=call["messages"])
        tokens = len(llm.tokenize(rendered.prompt.encode(), add_bos=False, special=True))
        assert tokens + call["max_tokens"] <= settings.context_size
    assert llm.calls[0]["messages"][1:] == llm.calls[1]["messages"][1:]
    assert '"night_sky"' in llm.calls[1]["messages"][0]["content"]


@pytest.mark.parametrize("thinking", [True, False])
@pytest.mark.parametrize("truncated", [True, False])
def test_queries_and_final_writing_use_the_same_inference_settings(
    tmp_path, monkeypatch, thinking, truncated
):
    import sys
    from types import SimpleNamespace

    class Formatter:
        def __init__(self, *, template, **options):
            self.thinking = "enable_thinking = true" in template

        def to_chat_handler(self):
            return self

        def __call__(self, *, messages):
            return SimpleNamespace(prompt=json.dumps(messages), added_special=True)

    monkeypatch.setitem(
        sys.modules, "llama_cpp.llama_chat_format", SimpleNamespace(Jinja2ChatFormatter=Formatter)
    )
    query_reply = (lambda: completion("night", "length")) if truncated else "night"
    llm = Llama(query_reply, "night")
    llm.metadata = {"tokenizer.chat_template": "{% if enable_thinking %}<think>{% endif %}"}
    llm.token_bos = lambda: -1
    original_completion = llm.create_chat_completion
    modes = []

    def capture(**options):
        modes.append(llm.chat_handler.thinking)
        return original_completion(**options)

    llm.create_chat_completion = capture
    prompts, _ = writer(tmp_path, llm, Tags(["night"]))
    assert prompts.create("night", PromptSettings(thinking=thinking)) == "night"
    query, final = llm.calls
    assert modes == [thinking, thinking]
    assert "response_format" not in query and "grammar" not in query
    assert "response_format" not in final and "grammar" not in final
    for option in ("max_tokens", "temperature", "top_p", "top_k", "min_p", "repeat_penalty"):
        assert query[option] == final[option]
    assert bool(query["logits_processor"]) == bool(final["logits_processor"]) == thinking
    assert [type(processor) for processor in query["logits_processor"] or []] == [
        type(processor) for processor in final["logits_processor"] or []
    ]
    assert llm.chat_handler.thinking == thinking


def test_sentence_ending_is_not_part_of_a_search_term():
    assert parse_queries("night, sky.") == ("night", "sky")
    assert parse_queries("none.") == ()
