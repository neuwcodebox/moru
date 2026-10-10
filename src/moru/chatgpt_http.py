"""Small HTTPS boundary for OAuth JSON and cancellable Responses SSE."""

import http.client
import json
import socket
from contextlib import contextmanager
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from moru.errors import MoruError

ERROR_CODES = {
    "subscription_sharing_user_not_eligible": "CHATGPT_NOT_ELIGIBLE",
    "subscription_sharing_usage_limit_exceeded": "CHATGPT_USAGE_LIMIT",
    "subscription_sharing_unsupported_capability": "CHATGPT_UNSUPPORTED",
    "subscription_sharing_route_not_supported": "CHATGPT_UNSUPPORTED",
    "subscription_sharing_usage_unavailable": "CHATGPT_UNAVAILABLE",
    "subscription_sharing_user_unavailable": "CHATGPT_UNAVAILABLE",
    "invalid_grant": "CHATGPT_SIGN_IN_REQUIRED",
    "invalid_refresh_token": "CHATGPT_SIGN_IN_REQUIRED",
    "token_expired": "CHATGPT_SIGN_IN_REQUIRED",
    "refresh_token_expired": "CHATGPT_SIGN_IN_REQUIRED",
    "refresh_token_invalidated": "CHATGPT_SIGN_IN_REQUIRED",
    "refresh_token_reused": "CHATGPT_SIGN_IN_REQUIRED",
}


class ChatGPTHttpError(MoruError):
    def __init__(self, status, code=""):
        self.status = status
        self.remote_code = code
        super().__init__(
            ERROR_CODES.get(
                code,
                {
                    401: "CHATGPT_SIGN_IN_REQUIRED",
                    403: "CHATGPT_NOT_ELIGIBLE",
                    429: "CHATGPT_USAGE_LIMIT",
                }.get(status, "CHATGPT_UNAVAILABLE"),
            )
        )


def response_error(status, body):
    error = body.get("error", {}) if isinstance(body, dict) else {}
    code = error.get("code", "") if isinstance(error, dict) else error
    return ChatGPTHttpError(status, code if isinstance(code, str) else "")


class ChatGPTHttp:
    def json(self, url, *, form=None, token=None):
        headers = {"Accept": "application/json"}
        body = None
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(form).encode("ascii")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urlopen(Request(url, data=body, headers=headers), timeout=30) as response:
                raw = response.read(2_000_000)
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            try:
                body = json.loads(exc.read(16384))
            except (ValueError, OSError):
                body = {}
            raise response_error(exc.code, body) from None
        except (URLError, OSError, ValueError) as exc:
            raise MoruError("CHATGPT_UNAVAILABLE") from exc

    @contextmanager
    def stream(self, token, payload, cancelled):
        connection = http.client.HTTPSConnection("api.openai.com", timeout=30)
        done = Event()
        request_socket = None

        def interrupt():
            while not done.wait(0.1):
                if cancelled.is_set():
                    sock = request_socket or connection.sock
                    if sock is not None:
                        try:
                            sock.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass  # A closed socket already interrupted the request.
                    return

        watcher = Thread(target=interrupt, name="chatgpt-cancel", daemon=True)
        watcher.start()
        try:
            if cancelled.is_set():
                raise MoruError("GENERATION_CANCELLED")
            connection.request(
                "POST",
                "/v1/responses",
                json.dumps(payload),
                {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            )
            request_socket = connection.sock
            response = connection.getresponse()
            if response.status != 200:
                try:
                    body = json.loads(response.read(16384))
                except ValueError:
                    body = {}
                raise response_error(response.status, body)
            yield sse_events(response, cancelled)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            code = "GENERATION_CANCELLED" if cancelled.is_set() else "CHATGPT_UNAVAILABLE"
            raise MoruError(code) from exc
        finally:
            done.set()
            connection.close()
            watcher.join()


def sse_events(response, cancelled):
    data = []
    size = 0
    while True:
        if cancelled.is_set():
            raise MoruError("GENERATION_CANCELLED")
        line = response.readline(1_000_001)
        if not line:
            break
        size += len(line)
        if size > 1_000_000:
            raise MoruError("PROMPT_INVALID_RESPONSE")
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                raw = "\n".join(data)
                if raw != "[DONE]":
                    event = json.loads(raw)
                    if not isinstance(event, dict):
                        raise MoruError("PROMPT_INVALID_RESPONSE")
                    yield event
            data, size = [], 0
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


def trusted_auth_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "auth.openai.com":
        raise MoruError("CHATGPT_AUTH_FAILED")
    return url
