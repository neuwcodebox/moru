"""Read a completed Responses turn without exposing tool-round commentary."""

import json
import logging
from collections import Counter
from dataclasses import dataclass
from time import monotonic

from moru.chatgpt_diagnostics import EVENT_TYPES, label, output_structure, response_metadata
from moru.chatgpt_http import response_error
from moru.errors import MoruError
from moru.prompt_text import check_cancelled


@dataclass(frozen=True)
class PromptReply:
    text: str
    output: tuple[dict, ...]


def read_prompt_reply(
    http, token, payload, cancelled, progress, *, trace="untracked", on_stage=None
):
    started = monotonic()
    event_counts = Counter()
    metadata = {}
    done_items = []
    delta_chars = 0
    done_text_chars = 0
    outcome = "unexpected_error"
    phase = "stream"
    text = ""
    completed = False
    output = []
    answer_message = True
    buffered = bool(payload.get("tools")) and payload.get("tool_choice") != "none"
    try:
        with http.stream(token, payload, cancelled) as events:
            for event in events:
                check_cancelled(cancelled)
                kind = event.get("type")
                event_counts[label(kind, EVENT_TYPES)] += 1
                if kind in ("response.output_item.added", "response.output_item.done"):
                    item = event.get("item")
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        if on_stage is not None:
                            on_stage("searching_tags")
                    elif isinstance(item, dict) and item.get("type") == "message":
                        answer_message = item.get("phase") != "commentary"
                        if answer_message and on_stage is not None:
                            on_stage("prompting")
                if kind == "response.output_text.done" and isinstance(event.get("text"), str):
                    done_text_chars += len(event["text"])
                if "response" in event:
                    metadata = response_metadata(event["response"])
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise MoruError("PROMPT_INVALID_RESPONSE")
                    if delta and answer_message and on_stage is not None:
                        on_stage("prompting")
                    delta_chars += len(delta)
                    text += delta
                    if len(text) > 65536:
                        raise MoruError("PROMPT_OUTPUT_TOO_LONG")
                    if not buffered:
                        progress("", text)
                elif kind == "response.output_item.done":
                    output.append(event.get("item"))
                    done_items.append(event.get("item"))
                elif kind in ("response.refusal.delta", "response.refusal.done"):
                    raise MoruError("CHATGPT_REFUSED")
                elif kind in ("response.failed", "error"):
                    metadata = response_metadata(event.get("response", event))
                    error = response_error(0, event.get("response", event))
                    raise MoruError(error.code)
                elif kind == "response.incomplete":
                    raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
                elif kind == "response.completed":
                    response = event.get("response", {})
                    if not isinstance(response, dict):
                        raise MoruError("PROMPT_INVALID_RESPONSE")
                    if response.get("status", "completed") != "completed":
                        raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
                    completed_output = response.get("output", output)
                    # SIWC may omit completed items from the final output array.
                    output = done_items if completed_output == [] else completed_output
                    completed = True
                    break
        phase = "parse_output"
        check_cancelled(cancelled)
        if not completed:
            raise MoruError("PROMPT_RESPONSE_INTERRUPTED")
        if not isinstance(output, list) or len(output) > 64:
            raise MoruError("PROMPT_INVALID_RESPONSE")
        answer = []
        for item in output:
            if not isinstance(item, dict):
                raise MoruError("PROMPT_INVALID_RESPONSE")
            if item.get("type") == "message" or "content" in item:
                content = item.get("content", [])
                if not isinstance(content, list) or any(
                    not isinstance(part, dict) for part in content
                ):
                    raise MoruError("PROMPT_INVALID_RESPONSE")
                for part in content:
                    if part.get("type") == "refusal":
                        raise MoruError("CHATGPT_REFUSED")
                    if part.get("type") == "output_text":
                        if not isinstance(part.get("text"), str):
                            raise MoruError("PROMPT_INVALID_RESPONSE")
                        answer.append(part["text"])
        if answer:
            final_text = "".join(answer)
            if len(final_text) > 65536:
                raise MoruError("PROMPT_OUTPUT_TOO_LONG")
            if final_text != text and not buffered:
                progress("", final_text)
            text = final_text
        outcome = "completed"
        return PromptReply(text, tuple(output))
    except MoruError as exc:
        outcome = exc.code
        raise
    finally:
        logging.getLogger(__name__).log(
            logging.INFO if outcome == "completed" else logging.WARNING,
            "ChatGPT response trace=%s outcome=%s phase=%s elapsed_ms=%d "
            "text_chars=%d delta_chars=%d done_text_chars=%d buffered=%s "
            "events=%s response=%s output=%s done_items=%s",
            trace,
            outcome,
            phase,
            int((monotonic() - started) * 1000),
            len(text),
            delta_chars,
            done_text_chars,
            buffered,
            json.dumps(dict(event_counts), sort_keys=True),
            json.dumps(metadata, sort_keys=True),
            json.dumps(output_structure(output), sort_keys=True),
            json.dumps(output_structure(done_items), sort_keys=True),
        )
