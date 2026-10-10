import copy
from contextlib import nullcontext
from datetime import UTC, datetime
from threading import Event
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from moru.chatgpt_auth import AuthorizationAttempt, ChatGPTAuth, IdTokenValidator
from moru.chatgpt_http import ChatGPTHttpError
from moru.errors import MoruError


class MemoryStore:
    def __init__(self):
        self.values = None

    def load(self):
        return copy.deepcopy(self.values)

    def save(self, values):
        self.values = copy.deepcopy(values)

    def locked(self):
        return nullcontext()


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def tokens(**changes):
    return {
        "access_token": "access",
        "refresh_token": "refresh",
        "id_token": "signed",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid offline_access resource.invoke chatgpt.tokens.use.direct",
        **changes,
    }


def attempt(client_id="dynamic_agent_client"):
    return AuthorizationAttempt(
        client_id,
        "http://127.0.0.1:1455/auth/callback",
        "host",
        state="state",
        nonce="nonce",
        verifier="verifier",
    )


def query(**changes):
    return {"state": ["state"], "code": ["code"], "client_id": ["oaiapp_moru"], **changes}


def connected(http=None, store=None):
    auth = ChatGPTAuth(
        store or MemoryStore(),
        http=http or FakeHttp(tokens()),
        now=lambda: 1000,
        validate=lambda *_: {"sub": "subject", "email": "user@example.com"},
    )
    auth.accept_callback(attempt(), query())
    return auth


def test_dynamic_registration_uses_pkce_and_issued_client_for_exchange():
    pending = attempt()
    params = parse_qs(urlsplit(pending.url()).query)
    assert params["agent_name_hint"] == ["Moru"]
    assert params["resource"] == ["https://api.openai.com/v1"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] != [pending.verifier]
    assert pending.exchange_form(query())["client_id"] == "oaiapp_moru"


@pytest.mark.parametrize(
    "changes",
    [
        {"state": ["other"]},
        {"state": ["state", "state"]},
        {"client_id": []},
        {"client_id": ["dynamic_agent_client"]},
        {"code": [""]},
        {"error": ["access_denied"]},
    ],
)
def test_invalid_oauth_callback_never_exchanges_a_code(changes):
    http = FakeHttp()
    auth = ChatGPTAuth(MemoryStore(), http=http)
    with pytest.raises(MoruError) as error:
        auth.accept_callback(attempt(), query(**changes))
    assert error.value.code == "CHATGPT_AUTH_FAILED"
    assert http.calls == []


def test_returning_registration_cannot_replace_its_client_id():
    with pytest.raises(MoruError):
        attempt("oaiapp_original").exchange_form(query())
    params = parse_qs(urlsplit(attempt("oaiapp_original").url({"email": "x@y"})).query)
    assert "agent_name_hint" not in params
    assert params["login_hint"] == ["x@y"]


def test_validated_identity_and_client_mapping_survive_signout_and_restart():
    store = MemoryStore()
    auth = connected(store=store)
    auth.http = FakeHttp({"revocation_endpoint": "https://auth.openai.com/revoke"}, {})
    result = auth.logout()
    assert result["connected"] is False
    assert result["revocation_confirmed"] is True
    restored = ChatGPTAuth(store)
    assert restored.status()["accounts"] == [
        {"id": "oaiapp_moru", "email": "user@example.com", "connected": False},
    ]
    assert "access_token" not in store.values["accounts"]["oaiapp_moru"]
    assert restored._values["host_id"] == auth._values["host_id"]


def test_status_never_exposes_tokens_or_host_identifiers():
    import json

    result = json.dumps(connected().status())
    for secret in ("access_token", "refresh_token", "id_token", "host_id", "subject"):
        assert secret not in result


def test_signin_without_plan_permission_is_retained_but_cannot_infer():
    auth = connected(FakeHttp(tokens(scope="openid email", refresh_token=None)))
    assert auth.status()["connected"] is True
    assert auth.status()["plan_enabled"] is False
    with pytest.raises(MoruError) as error:
        auth.access_token()
    assert error.value.code == "CHATGPT_NOT_ELIGIBLE"


def test_refresh_rotates_tokens_atomically_and_reuses_latest_token():
    auth = connected()
    auth.now = lambda: 4600
    auth.http = FakeHttp(tokens(access_token="next", refresh_token="rotated"))
    assert auth.access_token() == "next"
    assert auth.access_token() == "next"
    assert len(auth.http.calls) == 1
    form = auth.http.calls[0][1]["form"]
    assert form["client_id"] == "oaiapp_moru"
    assert form["refresh_token"] == "refresh"
    assert "scope" not in form
    assert auth.store.values["accounts"]["oaiapp_moru"]["refresh_token"] == "rotated"


def test_another_runtime_reads_the_rotated_token_before_attempting_refresh():
    store = MemoryStore()
    first = connected(store=store)
    second = ChatGPTAuth(store, http=FakeHttp(), now=lambda: 4600)
    first.now = lambda: 4600
    first.http = FakeHttp(tokens(access_token="latest", refresh_token="rotated"))
    assert first.access_token() == "latest"
    assert second.access_token() == "latest"
    assert second.http.calls == []


def test_signed_out_registration_can_be_selected_for_reauthorization():
    auth = connected()
    auth.http = FakeHttp(tokens())
    auth.accept_callback(attempt(), query(client_id=["oaiapp_second"]))
    auth.http = FakeHttp({"revocation_endpoint": "https://auth.openai.com/revoke"}, {})
    auth.logout()
    assert auth.select_account("oaiapp_moru")["connected"] is True
    assert auth.select_account("oaiapp_second")["connected"] is False


def test_storage_read_failure_is_reported_without_blocking_local_app_startup():
    store = MemoryStore()
    store.load = lambda: (_ for _ in ()).throw(MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE"))
    auth = ChatGPTAuth(store)
    assert auth.status()["connected"] is False
    assert auth.status()["error_code"] == "CHATGPT_SECURE_STORAGE_UNAVAILABLE"


@pytest.mark.parametrize(
    "error,cleared",
    [
        (ChatGPTHttpError(400, "invalid_grant"), True),
        (ChatGPTHttpError(503), False),
    ],
)
def test_terminal_refresh_clears_tokens_but_temporary_failure_preserves_them(error, cleared):
    auth = connected()
    auth.now = lambda: 4600
    auth.http = FakeHttp(error)
    with pytest.raises(MoruError):
        auth.access_token()
    assert auth.status()["connected"] is not cleared


def test_wrong_identity_or_cancelled_login_does_not_replace_active_account():
    auth = connected()
    before = auth.store.load()
    auth.http = FakeHttp(tokens())
    auth.validate = lambda *_: {"sub": "another-subject"}
    with pytest.raises(MoruError):
        auth.accept_callback(attempt("oaiapp_moru"), query())
    assert auth.store.load() == before
    cancelled = Event()
    cancelled.set()
    auth.http = FakeHttp(tokens())
    with pytest.raises(MoruError):
        auth.accept_callback(attempt(), query(), cancelled)
    assert auth.store.load() == before


def test_failed_remote_revocation_still_clears_local_tokens_with_explicit_result():
    auth = connected()
    auth.http = FakeHttp(ChatGPTHttpError(503))
    result = auth.logout()
    assert result["connected"] is False
    assert result["revocation_confirmed"] is False


def test_welcome_is_persisted_and_only_shown_until_acknowledged():
    auth = connected()
    assert auth.status()["welcome_pending"] is True
    auth.dismiss_welcome()
    auth.http = FakeHttp(tokens())
    auth.accept_callback(attempt("oaiapp_moru"), query())
    assert auth.status()["welcome_pending"] is False


def test_failed_storage_does_not_activate_unpersisted_tokens():
    store = MemoryStore()
    auth = ChatGPTAuth(store, http=FakeHttp(tokens()), validate=lambda *_: {"sub": "subject"})
    store.save = lambda _: (_ for _ in ()).throw(MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE"))
    with pytest.raises(MoruError):
        auth.accept_callback(attempt(), query())
    assert auth.status()["connected"] is False


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"iss": "https://attacker.example"},
        {"aud": "oaiapp_other"},
        {"nonce": "other"},
        {"exp": 1},
        {"sub": ""},
    ],
)
def test_id_token_signature_identity_and_authorization_claims_are_verified(
    signing_key, changes, monkeypatch
):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 10, tzinfo=UTC)

    monkeypatch.setattr(jwt.api_jwt, "datetime", FixedDatetime)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    public["kid"] = "key"
    http = FakeHttp(
        {"issuer": "https://auth.openai.com", "jwks_uri": "https://auth.openai.com/jwks"},
        {"keys": [public]},
    )
    token = jwt.encode(
        {
            "iss": "https://auth.openai.com",
            "aud": "oaiapp_moru",
            "sub": "subject",
            "iat": 1,
            "exp": 4_102_444_800,
            "nonce": "nonce",
            **changes,
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "key"},
    )
    validator = IdTokenValidator(http)
    if not changes:
        assert validator(token, "oaiapp_moru", "nonce")["sub"] == "subject"
    else:
        with pytest.raises(MoruError) as error:
            validator(token, "oaiapp_moru", "nonce")
        assert error.value.code == "CHATGPT_AUTH_FAILED"


def test_forged_signature_is_rejected(signing_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(other.public_key(), as_dict=True)
    public["kid"] = "key"
    http = FakeHttp(
        {"issuer": "https://auth.openai.com", "jwks_uri": "https://auth.openai.com/jwks"},
        {"keys": [public]},
    )
    token = jwt.encode({"sub": "x"}, signing_key, algorithm="RS256", headers={"kid": "key"})
    with pytest.raises(MoruError):
        IdTokenValidator(http)(token, "oaiapp_moru", "nonce")


@pytest.fixture
def login_runtime(monkeypatch):
    from io import BytesIO
    from types import SimpleNamespace
    from urllib.parse import urlencode

    runtime = SimpleNamespace(server=None, thread=None, parameters=None, denied=False)

    class Server:
        def __init__(self, address, callback):
            assert address == ("127.0.0.1", 0)
            self.callback, self.server_port, self.closed = callback, 1455, False
            runtime.server = self

        def handle_request(self):
            params = {"state": runtime.parameters["state"][0]}
            if runtime.denied:
                params["error"] = "access_denied"
            else:
                params.update(code="code", client_id="oaiapp_moru")
            request = object.__new__(self.callback)
            request.path = "/auth/callback?" + urlencode(params)
            request.wfile = BytesIO()
            request.send_response = lambda *_: None
            request.send_header = lambda *_: None
            request.end_headers = lambda: None
            self.callback.do_GET(request)

        def server_close(self):
            self.closed = True

    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            self.target, self.alive = target, False
            runtime.thread = self

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, **_kwargs):
            if self.alive:
                self.target()
                self.alive = False

    def browser(url):
        assert runtime.server is not None and runtime.thread.alive
        runtime.parameters = parse_qs(urlsplit(url).query)
        return True

    monkeypatch.setattr("moru.chatgpt_auth.HTTPServer", Server)
    monkeypatch.setattr("moru.chatgpt_auth.Thread", DeferredThread)
    runtime.auth = ChatGPTAuth(
        MemoryStore(),
        http=FakeHttp(tokens()),
        now=lambda: 1000,
        open_browser=browser,
        validate=lambda *_: {"sub": "subject", "email": "user@example.com"},
    )
    return runtime


def test_login_starts_listener_before_browser_and_closes_it_after_callback(login_runtime):
    runtime = login_runtime
    assert runtime.auth.login()["login_state"] == "waiting"
    runtime.thread.join()
    assert runtime.auth.status()["connected"] is True
    assert runtime.auth.status()["login_state"] == "completed"
    assert runtime.server.closed is True
    form = runtime.auth.http.calls[0][1]["form"]
    assert form["redirect_uri"] == runtime.parameters["redirect_uri"][0]


def test_declined_consent_ends_login_and_closes_listener_without_code_exchange(login_runtime):
    runtime = login_runtime
    runtime.denied = True
    runtime.auth.login()
    runtime.thread.join()
    assert runtime.auth.status()["error_code"] == "CHATGPT_AUTH_FAILED"
    assert runtime.auth.status()["login_state"] == "failed"
    assert runtime.server.closed
    assert runtime.auth.http.calls == []


def test_cancelled_login_closes_listener_without_activating_account(login_runtime):
    runtime = login_runtime
    runtime.auth.login()
    runtime.auth.cancel_login()
    runtime.thread.join()
    assert runtime.auth.status()["login_state"] == "idle"
    assert runtime.auth.status()["connected"] is False
    assert runtime.server.closed
    assert runtime.auth.http.calls == []


def test_browser_launch_failure_preserves_explicit_error_and_closes_listener(login_runtime):
    runtime = login_runtime
    runtime.auth.open_browser = lambda _: False
    with pytest.raises(MoruError) as error:
        runtime.auth.login()
    runtime.thread.join()
    assert error.value.code == "CHATGPT_AUTH_FAILED"
    assert runtime.server.closed
    assert runtime.auth.status()["connected"] is False
