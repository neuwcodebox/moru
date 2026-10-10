"""Diagnostics explain failures without storing response or request contents."""

import logging
from threading import Event

import pytest
from test_chatgpt_prompts import SETTINGS, Auth, delta
from test_chatgpt_tag_tools import Responses, Tools, call, completed, final_turn

from moru.chatgpt.http import ChatGPTHttpError
from moru.chatgpt.prompts import ChatGPTPrompts
from moru.errors import MoruError


def generate(http, *, tools=None):
    return ChatGPTPrompts(Auth(), http, tag_tools=tools).create(
        "PRIVATE_USER_REQUEST", SETTINGS, Event(), lambda *_: None
    )


def test_empty_final_response_identifies_reasoning_only_output_and_token_usage(caplog):
    event = completed({"type": "reasoning", "encrypted_content": "PRIVATE_REASONING"})
    event["response"]["usage"] = {
        "input_tokens": 42,
        "output_tokens": 91,
        "total_tokens": 133,
        "output_tokens_details": {"reasoning_tokens": 91},
    }
    with caplog.at_level(logging.INFO), pytest.raises(MoruError) as error:
        generate(Responses([event]), tools=Tools())
    assert error.value.code == "PROMPT_EMPTY_RESPONSE"
    response = next(r.message for r in caplog.records if "ChatGPT response" in r.message)
    rejected = next(r.message for r in caplog.records if "final prompt rejected" in r.message)
    assert '"type": "reasoning"' in response
    assert '"reasoning_tokens": 91' in response
    assert '"status": "completed"' in response and "text_chars=0" in response
    assert "blank=True" in rejected and "calls_used=0" in rejected
    assert "PRIVATE_USER_REQUEST" not in caplog.text
    assert "PRIVATE_REASONING" not in caplog.text


def test_tool_rounds_and_final_response_share_one_request_without_logging_contents(caplog):
    function = call(arguments={"query": "PRIVATE_QUERY", "limit": 20})
    http = Responses([completed(function)], [delta("PRIVATE_FINAL_PROMPT"), completed()])
    with caplog.at_level(logging.INFO):
        assert generate(http, tools=Tools(["PRIVATE_TAG_RESULT"])) == "PRIVATE_FINAL_PROMPT"
    requests = [r.message for r in caplog.records if "ChatGPT request trace=" in r.message]
    traces = [message.split("trace=", 1)[1].split()[0].split(":") for message in requests]
    assert len(traces) == 2
    assert traces[0][0] == traces[1][0] and traces[0][1:] == ["1", "1"]
    assert traces[1][1:] == ["2", "1"]
    assert '"tool": "search_tags"' in caplog.text
    assert '"namespace": "danbooru"' in caplog.text
    assert '"result_count": 1' in caplog.text and "calls_used=1" in caplog.text
    for private in (
        "PRIVATE_USER_REQUEST",
        "PRIVATE_QUERY",
        "PRIVATE_FINAL_PROMPT",
        "PRIVATE_TAG_RESULT",
        "access",
    ):
        assert private not in caplog.text


def test_stream_interruption_retains_partial_event_counts_without_partial_text(caplog):
    with caplog.at_level(logging.INFO), pytest.raises(MoruError) as error:
        generate(Responses([delta("PRIVATE_PARTIAL_RESPONSE")]))
    assert error.value.code == "PROMPT_RESPONSE_INTERRUPTED"
    assert '"response.output_text.delta": 1' in caplog.text
    assert "outcome=PROMPT_RESPONSE_INTERRUPTED" in caplog.text
    assert "PRIVATE_PARTIAL_RESPONSE" not in caplog.text


def test_malformed_output_logs_shape_before_validation_fails(caplog):
    event = completed()
    event["response"]["output"] = "PRIVATE_MALFORMED_OUTPUT"
    with caplog.at_level(logging.INFO), pytest.raises(MoruError) as error:
        generate(Responses([event]))
    assert error.value.code == "PROMPT_INVALID_RESPONSE"
    assert 'output={"shape": "invalid"}' in caplog.text
    assert "phase=parse_output" in caplog.text
    assert "PRIVATE_MALFORMED_OUTPUT" not in caplog.text


def test_untrusted_metadata_and_error_messages_are_not_logged(caplog):
    event = completed(
        {
            "type": "PRIVATE_TYPE",
            "name": "PRIVATE_NAME",
            "namespace": "PRIVATE_NAMESPACE",
            "arguments": "PRIVATE_ARGUMENTS",
            "status": "PRIVATE_STATUS",
            "content": [{"type": "PRIVATE_CONTENT_TYPE", "text": "PRIVATE_CONTENT"}],
        }
    )
    event["response"]["status"] = "PRIVATE_RESPONSE_STATUS"
    with caplog.at_level(logging.INFO), pytest.raises(MoruError):
        generate(Responses([event]))
    assert "PRIVATE_" not in caplog.text
    assert '"status": "other"' in caplog.text


def test_admission_retry_records_http_status_without_remote_details_or_tokens(caplog):
    with caplog.at_level(logging.INFO):
        generate(Responses(ChatGPTHttpError(401, "PRIVATE_REMOTE_ERROR"), final_turn()))
    assert "status=401" in caplog.text and "refresh_retry=True" in caplog.text
    assert "remote_code=other" in caplog.text
    assert "PRIVATE_REMOTE_ERROR" not in caplog.text
    assert "renewed" not in caplog.text and "access" not in caplog.text


def test_lookup_failure_is_visible_and_final_prompt_still_completes(caplog):
    with caplog.at_level(logging.INFO):
        generate(
            Responses([completed(call())], final_turn()),
            tools=Tools({"error": "lookup_unavailable"}),
        )
    assert '"error": "lookup_unavailable"' in caplog.text
    assert "stopped=lookup_unavailable" in caplog.text
    assert "ChatGPT prompt completed" in caplog.text


def test_empty_completion_array_and_preserved_streamed_items_remain_distinct_in_logs(caplog):
    with caplog.at_level(logging.INFO):
        generate(
            Responses(
                [
                    {"type": "response.output_item.done", "item": call()},
                    completed(),
                ],
                final_turn(),
            ),
            tools=Tools(),
        )
    assert '"output_count": 0' in caplog.text
    assert 'output={"count": 1,' in caplog.text
    assert 'done_items={"count": 1,' in caplog.text


def test_nonempty_response_that_fails_final_extraction_is_distinguished_from_missing_text(caplog):
    with caplog.at_level(logging.INFO), pytest.raises(MoruError) as error:
        generate(Responses([delta("Final image prompt:"), completed()]))
    assert error.value.code == "PROMPT_EMPTY_RESPONSE"
    assert "blank=False" in caplog.text
    assert "text_chars=19" in caplog.text
