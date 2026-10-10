"""Bounded, cached and cancellable read-only access to the Danbooru catalog."""

import http.client
import json
import socket
from collections import OrderedDict
from threading import Event, Lock, Thread
from time import monotonic
from urllib.parse import urlencode

from moru.cancellation import check_cancelled


class TagLookupError(Exception):
    """The optional catalog could not provide a valid response."""

    def __init__(self, *, status=None):
        super().__init__("Danbooru lookup unavailable")
        self.status = status


class DanbooruHttp:
    def __init__(self, *, connect=http.client.HTTPSConnection, clock=monotonic):
        self._connect, self._clock = connect, clock
        self._lock = Lock()
        self._next_request = 0.0
        self._cache = OrderedDict()

    def get(self, path, params, cancelled):
        key = path + "?" + urlencode(sorted(params.items()))
        with self._lock:
            check_cancelled(cancelled)
            cached = self._cache.get(key)
            if cached is not None and cached[0] > self._clock():
                self._cache.move_to_end(key)
                return cached[1]
            for attempt in range(2):
                delay = 1.0 if attempt else max(0.0, self._next_request - self._clock())
                if delay and cancelled.wait(delay):
                    check_cancelled(cancelled)
                check_cancelled(cancelled)
                self._next_request = self._clock() + 1.0
                try:
                    result = self._read(key, cancelled)
                    break
                except TagLookupError as exc:
                    check_cancelled(cancelled)
                    if exc.status != 429 or attempt:
                        raise
            check_cancelled(cancelled)
            self._cache[key] = (self._clock() + 300.0, result)
            self._cache.move_to_end(key)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return result

    def _read(self, path, cancelled):
        connection = self._connect("safebooru.donmai.us", timeout=10)
        done = Event()
        request_socket = None
        deadline = self._clock() + 10.0

        def interrupt():
            while not done.wait(0.1):
                if cancelled.is_set() or self._clock() >= deadline:
                    sock = request_socket or connection.sock
                    if sock is not None:
                        try:
                            sock.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass  # The socket may already have been closed.
                        return

        watcher = Thread(target=interrupt, name="danbooru-cancel", daemon=True)
        watcher.start()
        try:
            check_cancelled(cancelled)
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Moru/0.1 (https://github.com/neuwcodebox/moru)",
                },
            )
            request_socket = connection.sock
            response = connection.getresponse()
            check_cancelled(cancelled)
            if self._clock() >= deadline:
                raise TagLookupError()
            if response.status != 200:
                raise TagLookupError(status=response.status)
            raw = response.read(500_001)
            check_cancelled(cancelled)
            if self._clock() >= deadline or len(raw) > 500_000:
                raise TagLookupError()
            result = json.loads(raw)
            if not isinstance(result, (list, dict)):
                raise TagLookupError()
            return result
        except (OSError, http.client.HTTPException, ValueError) as exc:
            check_cancelled(cancelled)
            raise TagLookupError() from exc
        finally:
            done.set()
            connection.close()
            watcher.join()
