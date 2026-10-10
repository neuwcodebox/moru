"""Minimal llama.cpp stream and logits fakes; no models or GPU."""


def completion(content, finish_reason="stop"):
    chunks = [content] if isinstance(content, str) else content
    for chunk in chunks:
        yield {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
    yield {"choices": [{"delta": {}, "finish_reason": finish_reason}]}


class Scores(list):
    """Small stand-in for the mutable logit array, without inference dependencies."""

    def __setitem__(self, key, value):
        super().__setitem__(key, [value] * len(self) if isinstance(key, slice) else value)

    def argmax(self):
        return max(range(len(self)), key=self.__getitem__)
