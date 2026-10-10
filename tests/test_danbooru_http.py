import json
from threading import Event

import pytest

from moru.danbooru.http import DanbooruHttp, TagLookupError
from moru.errors import MoruError


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ControlledCancellation(Event):
    def __init__(self, clock, *, cancel_on_wait=False):
        super().__init__()
        self.clock, self.cancel_on_wait = clock, cancel_on_wait
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self.clock.now += timeout
        if self.cancel_on_wait:
            self.set()
        return self.is_set()


class Response:
    def __init__(self, body, status=200, *, on_read=None):
        self.body, self.status, self.on_read = body, status, on_read

    def read(self, size):
        if self.on_read is not None:
            self.on_read()
        return self.body[:size]


class Connection:
    sock = None

    def __init__(self, response):
        self.response, self.requests, self.closed = response, [], False

    def request(self, method, path, *, headers):
        self.requests.append((method, path, headers))

    def getresponse(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def close(self):
        self.closed = True


class Server:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.connections = []

    def connect(self, host, *, timeout):
        assert host == "safebooru.donmai.us" and timeout == 10
        connection = Connection(next(self.responses))
        self.connections.append(connection)
        return connection


def test_reads_use_a_fixed_host_get_identifiable_agent_and_no_chatgpt_credentials():
    server = Server(Response(b'[{"name":"grey_hair"}]'))
    http = DanbooruHttp(connect=server.connect)
    assert http.get("/tags.json", {"search[name]": "grey_hair"}, Event()) == [{"name": "grey_hair"}]
    connection = server.connections[0]
    method, path, headers = connection.requests[0]
    assert method == "GET" and path.startswith("/tags.json?")
    assert headers["User-Agent"].startswith("Moru/")
    assert "Authorization" not in headers
    assert connection.closed


def test_successful_results_are_cached_until_expiry_without_additional_network_or_waiting():
    clock, cancelled = Clock(), Event()
    server = Server(Response(b"[]"), Response(b'[{"name":"grey_hair"}]'))
    http = DanbooruHttp(connect=server.connect, clock=clock)
    assert http.get("/tags.json", {}, cancelled) == []
    assert http.get("/tags.json", {}, cancelled) == []
    assert len(server.connections) == 1
    clock.now = 301
    assert http.get("/tags.json", {}, cancelled) == [{"name": "grey_hair"}]
    assert len(server.connections) == 2


def test_uncached_reads_are_spaced_by_one_second_with_a_cancellable_wait():
    clock = Clock()
    cancelled = ControlledCancellation(clock)
    server = Server(Response(b"[]"), Response(b"[]"))
    http = DanbooruHttp(connect=server.connect, clock=clock)
    http.get("/tags.json", {"name": "a"}, cancelled)
    http.get("/tags.json", {"name": "b"}, cancelled)
    assert cancelled.waits == [1.0]


def test_cancellation_during_throttling_does_not_start_another_network_request():
    clock = Clock()
    cancelled = ControlledCancellation(clock, cancel_on_wait=True)
    server = Server(Response(b"[]"))
    http = DanbooruHttp(connect=server.connect, clock=clock)
    http.get("/tags.json", {"name": "a"}, cancelled)
    with pytest.raises(MoruError) as error:
        http.get("/tags.json", {"name": "b"}, cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert len(server.connections) == 1


@pytest.mark.parametrize(
    "response",
    [
        Response(b"{}", status=403),
        Response(b"{}", status=503),
        Response(b"not json"),
        Response(b"null"),
        Response(b"a" * 500001),
        TimeoutError(),
    ],
)
def test_unavailable_or_invalid_responses_are_optional_lookup_errors_and_connections_close(
    response,
):
    server = Server(response)
    with pytest.raises(TagLookupError):
        DanbooruHttp(connect=server.connect).get("/tags.json", {}, Event())
    assert server.connections[0].closed


def test_cancellation_during_response_read_propagates_and_closes_the_connection():
    cancelled = Event()
    server = Server(Response(b"[]", on_read=cancelled.set))
    with pytest.raises(MoruError) as error:
        DanbooruHttp(connect=server.connect).get("/tags.json", {}, cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert server.connections[0].closed


def test_cancelled_cached_lookup_never_returns_a_result():
    cancelled, server = Event(), Server(Response(b"[]"))
    http = DanbooruHttp(connect=server.connect)
    http.get("/tags.json", {}, cancelled)
    cancelled.set()
    with pytest.raises(MoruError) as error:
        http.get("/tags.json", {}, cancelled)
    assert error.value.code == "GENERATION_CANCELLED"


def test_cache_has_a_fixed_size_and_does_not_grow_for_every_new_query():
    clock = Clock()
    server = Server(*[Response(json.dumps([]).encode()) for _ in range(130)])
    http = DanbooruHttp(connect=server.connect, clock=clock)
    for index in range(129):
        clock.now += 2
        http.get("/tags.json", {"name": str(index)}, Event())
    clock.now += 2
    http.get("/tags.json", {"name": "0"}, Event())
    assert len(server.connections) == 130


def test_rate_limit_retries_once_after_exactly_one_second_and_returns_the_result():
    clock = Clock()
    cancelled = ControlledCancellation(clock)
    server = Server(Response(b"{}", status=429), Response(b"[]"))
    http = DanbooruHttp(connect=server.connect, clock=clock)
    assert http.get("/tags.json", {}, cancelled) == []
    assert cancelled.waits == [1.0]
    assert len(server.connections) == 2
    assert all(connection.closed for connection in server.connections)


def test_a_second_rate_limit_is_an_optional_failure_without_a_third_request():
    clock = Clock()
    cancelled = ControlledCancellation(clock)
    server = Server(Response(b"{}", status=429), Response(b"{}", status=429))
    http = DanbooruHttp(connect=server.connect, clock=clock)
    with pytest.raises(TagLookupError) as error:
        http.get("/tags.json", {}, cancelled)
    assert error.value.status == 429
    assert cancelled.waits == [1.0]
    assert len(server.connections) == 2
    assert all(connection.closed for connection in server.connections)


def test_cancellation_during_rate_limit_retry_wait_prevents_the_second_request():
    clock = Clock()
    cancelled = ControlledCancellation(clock, cancel_on_wait=True)
    server = Server(Response(b"{}", status=429))
    with pytest.raises(MoruError) as error:
        DanbooruHttp(connect=server.connect, clock=clock).get("/tags.json", {}, cancelled)
    assert error.value.code == "GENERATION_CANCELLED"
    assert len(server.connections) == 1


def test_each_read_has_a_ten_second_deadline_even_if_the_socket_returns_late():
    clock = Clock()
    server = Server(Response(b"[]", on_read=lambda: setattr(clock, "now", 10.1)))
    with pytest.raises(TagLookupError):
        DanbooruHttp(connect=server.connect, clock=clock).get("/tags.json", {}, Event())
    assert len(server.connections) == 1 and server.connections[0].closed


def test_deadline_interrupts_the_body_socket_even_when_http_detaches_it(monkeypatch):
    import moru.danbooru.http as transport

    class Done:
        def __init__(self):
            self.finished = False

        def wait(self, timeout):
            return self.finished

        def set(self):
            self.finished = True

    class Watcher:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            watchers.append(self)

        def join(self):
            pass

    class Socket:
        interrupted = False

        def shutdown(self, how):
            self.interrupted = True

    class DetachedConnection(Connection):
        def getresponse(self):
            self.sock = None  # HTTP Connection: close detaches the socket before body reads.
            return super().getresponse()

    clock, sock, watchers = Clock(), Socket(), []

    def read_body():
        clock.now = 10.1
        watchers[0].target()
        assert sock.interrupted
        raise TimeoutError()

    connection = DetachedConnection(Response(b"[]", on_read=read_body))
    connection.sock = sock
    monkeypatch.setattr(transport, "Event", Done)
    monkeypatch.setattr(transport, "Thread", Watcher)
    with pytest.raises(TagLookupError):
        DanbooruHttp(connect=lambda *a, **kw: connection, clock=clock).get(
            "/tags.json",
            {},
            Event(),
        )
    assert sock.interrupted and connection.closed
