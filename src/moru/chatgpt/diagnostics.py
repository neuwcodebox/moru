"""Allowlisted Responses metadata; never serialize model text or tool arguments."""

import json
from collections import Counter

from moru.chatgpt.http import ERROR_CODES

ITEM_TYPES = frozenset(
    (
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "tool_search_call",
        "tool_search_output",
        "web_search_call",
        "refusal",
        "output_text",
        "input_text",
        "input_image",
    )
)
EVENT_TYPES = frozenset(
    (
        "response.created",
        "response.in_progress",
        "response.completed",
        "response.failed",
        "response.incomplete",
        "error",
        "response.output_item.added",
        "response.output_item.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "response.refusal.delta",
        "response.refusal.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.done",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
        "response.reasoning_text.delta",
        "response.reasoning_text.done",
        "response.custom_tool_call_input.delta",
        "response.custom_tool_call_input.done",
    )
)
TOOL_NAMES = frozenset(("search_tags", "get_tag_info", "get_related_tags"))
STATUSES = frozenset(("completed", "incomplete", "failed", "in_progress", "queued", "cancelled"))


def label(value, allowed):
    if value is None:
        return "missing"
    return value if isinstance(value, str) and value in allowed else "other"


def output_structure(items):
    if not isinstance(items, (list, tuple)):
        return {"shape": "invalid"}
    result = []
    for item in items[:64]:
        if not isinstance(item, dict):
            result.append({"type": "invalid"})
            continue
        entry = {"type": label(item.get("type"), ITEM_TYPES)}
        if "status" in item:
            entry["status"] = label(item["status"], STATUSES)
        if "name" in item:
            entry["tool"] = label(item["name"], TOOL_NAMES)
            entry["namespace"] = label(item.get("namespace"), {"danbooru"})
        if "arguments" in item:
            raw = item["arguments"]
            entry["arguments_chars"] = len(raw) if isinstance(raw, str) else "invalid"
        if "encrypted_content" in item:
            entry["encrypted_reasoning"] = True
        if "content" in item:
            content = item["content"]
            if isinstance(content, list):
                entry["content"] = dict(
                    Counter(
                        label(part.get("type"), ITEM_TYPES) if isinstance(part, dict) else "invalid"
                        for part in content[:64]
                    )
                )
            elif isinstance(content, str):
                entry["content"] = "text"
                entry["content_chars"] = len(content)
            else:
                entry["content"] = "invalid"
        result.append(entry)
    return {"count": len(items), "items": result}


def response_metadata(response):
    if not isinstance(response, dict):
        return {"shape": "invalid"}
    result = {
        "status": label(response.get("status"), STATUSES),
        "output_present": "output" in response,
    }
    if isinstance(response.get("output"), list):
        result["output_count"] = len(response["output"])
    details = response.get("incomplete_details")
    if isinstance(details, dict):
        result["incomplete_reason"] = label(
            details.get("reason"), {"max_output_tokens", "content_filter"}
        )
    error = response.get("error")
    if isinstance(error, dict):
        result["error_code"] = label(error.get("code"), ERROR_CODES)
    usage = response.get("usage")
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                result[key] = value
        details = usage.get("output_tokens_details")
        if isinstance(details, dict):
            value = details.get("reasoning_tokens")
            if type(value) is int and 0 <= value <= 1_000_000_000:
                result["reasoning_tokens"] = value
    return result


def tool_result_metadata(calls, outputs):
    results = []
    for call, output in zip(calls, outputs, strict=True):
        value = json.loads(output["output"])
        results.append(
            {
                "tool": label(call.get("name"), TOOL_NAMES),
                "result_type": "list" if isinstance(value, list) else "object",
                "result_count": len(value) if isinstance(value, (dict, list)) else 0,
                "error": label(
                    value.get("error"),
                    {
                        "lookup_unavailable",
                        "lookup_limit",
                        "invalid_arguments",
                        "unknown_tool",
                    },
                )
                if isinstance(value, dict)
                else "missing",
            }
        )
    return results
