"""Bounded, request-local execution of Responses tag tool calls."""

import json
from threading import Event

from moru.cancellation import check_cancelled
from moru.domain import PromptSource
from moru.errors import MoruError
from moru.ports import SourceProgress

MAX_TOOL_CALLS = 8
MAX_LOOKUP_ROUNDS = 4


class TagToolSession:
    def __init__(self, tools, cancelled: Event, on_source: SourceProgress | None):
        self.tools = tools
        self.cancelled = cancelled
        self.on_source = on_source
        self.calls_used = 0
        self.stop_reason = None

    @property
    def exhausted(self) -> bool:
        return bool(self.stop_reason) or self.calls_used >= MAX_TOOL_CALLS

    def execute_calls(self, calls: list[dict]) -> list[dict]:
        identifiers = [item.get("call_id") for item in calls]
        if any(not isinstance(value, str) or not value for value in identifiers):
            raise MoruError("PROMPT_INVALID_RESPONSE")
        if len(set(identifiers)) != len(identifiers):
            raise MoruError("PROMPT_INVALID_RESPONSE")
        results = []
        for item in calls:
            check_cancelled(self.cancelled)
            if self.stop_reason:
                result = {"error": self.stop_reason}
            elif self.calls_used >= MAX_TOOL_CALLS:
                result = {"error": "lookup_limit"}
            else:
                self.calls_used += 1
                result = self._execute(item)
                if isinstance(result, dict) and result.get("error") == "lookup_unavailable":
                    self.stop_reason = "lookup_unavailable"
            results.append(
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                }
            )
        return results

    def _execute(self, item):
        name = item.get("name")
        if item.get("namespace") not in (None, "danbooru") or not isinstance(name, str):
            return {"error": "unknown_tool"}
        raw = item.get("arguments")
        try:
            if not isinstance(raw, str) or len(raw) > 8192:
                raise ValueError("invalid arguments")
            arguments = json.loads(raw)
        except ValueError:
            return {"error": "invalid_arguments"}
        result = self.tools.execute(name, arguments, self.cancelled)
        invalid = isinstance(result, dict) and result.get("error") in (
            "invalid_arguments",
            "unknown_tool",
        )
        if self.on_source is not None and not invalid:
            field = "query" if name == "search_tags" else "name"
            self.on_source(
                PromptSource(
                    name,
                    arguments[field],
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                )
            )
        check_cancelled(self.cancelled)
        return result
