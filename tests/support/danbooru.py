"""Scripted catalog responses, without HTTP requests."""

class Catalog:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []

    def get(self, path, params, cancelled):
        self.calls.append((path, params))
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


def tag(name, **extra):
    return {"name": name, "post_count": 100, "is_deprecated": False, **extra}
