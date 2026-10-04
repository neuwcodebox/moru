"""Traceback locations and types without inference exception messages containing user content."""

import logging
import traceback


class PrivateTracebackFormatter(logging.Formatter):
    def formatException(self, exception_info):
        _, exception, _ = exception_info
        parts = []
        seen = set()
        while exception is not None and id(exception) not in seen:
            seen.add(id(exception))
            parts.append("".join(traceback.format_tb(exception.__traceback__)))
            parts.append(f"{type(exception).__module__}.{type(exception).__name__}\n")
            exception = exception.__cause__ or exception.__context__
        return "".join(parts).rstrip()
