"""Scripted Responses streams and authentication at the HTTP boundary."""

import copy
import json
from contextlib import contextmanager

from moru.chatgpt.tools import DanbooruTools
from moru.domain import PromptSettings

SETTINGS = PromptSettings(provider="chatgpt", chatgpt_model="account-model")


class Auth:
    def __init__(self):
        self.refreshes = []

    def access_token(self, *, rejected_token=None):
        self.refreshes.append(rejected_token)
        return "renewed" if rejected_token else "access"


class StreamHttp:
    def __init__(self, events):
        self.events = events
        self.calls = []
        self.closed = False

    @contextmanager
    def stream(self, token, payload, cancelled):
        self.calls.append((token, payload))
        try:
            if isinstance(self.events, Exception):
                raise self.events
            yield iter(self.events)
        finally:
            self.closed = True


def delta(text="1girl, silver hair, moonlight"):
    return {"type": "response.output_text.delta", "delta": text}


class Responses:
    def __init__(self, *turns):
        self.turns = iter(turns)
        self.calls = []
        self.closed = 0

    @contextmanager
    def stream(self, token, payload, cancelled):
        self.calls.append((token, copy.deepcopy(payload)))
        try:
            events = next(self.turns)
            if isinstance(events, Exception):
                raise events
            yield iter(events)
        finally:
            self.closed += 1


class Tools:
    def __init__(self, result=None):
        self.calls = []
        self.result = ["crossed_arms"] if result is None else result

    def definitions(self):
        return DanbooruTools(None).definitions()

    def execute(self, name, arguments, cancelled):
        self.calls.append((name, arguments))
        return self.result


def call(name="search_tags", arguments=None, *, call_id="call_1", namespace="danbooru"):
    return {
        "type": "function_call",
        "id": "fc_1",
        "call_id": call_id,
        "namespace": namespace,
        "name": name,
        "arguments": json.dumps(
            {"query": "arms crossed", "limit": 20} if arguments is None else arguments
        ),
        "status": "completed",
    }


def completed(*items):
    return {
        "type": "response.completed",
        "response": {"status": "completed", "output": list(items)},
    }


def final_turn():
    return [delta("1girl, crossed_arms, grey_hair"), completed()]
