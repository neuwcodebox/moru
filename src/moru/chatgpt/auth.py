"""SIWC PKCE, validated account registrations and rotating credentials."""

import base64
import hashlib
import hmac
import secrets
import time
import uuid
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, RLock, Thread
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt

from moru.chatgpt.http import ChatGPTHttp, ChatGPTHttpError, trusted_auth_url
from moru.errors import MoruError

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"


@dataclass(frozen=True)
class AuthorizationAttempt:
    client_id: str
    redirect_uri: str
    host_id: str
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(64), repr=False)

    def url(self, account=None):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest())
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "ext_agent_host_id": self.host_id,
            "response_type": "code",
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": self.state,
            "nonce": self.nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge.rstrip(b"=").decode(),
        }
        if self.client_id == "dynamic_agent_client":
            params["agent_name_hint"] = "Moru"
        elif account:
            if account.get("id_token"):
                params["id_token_hint"] = account["id_token"]
            if account.get("email"):
                params["login_hint"] = account["email"]
            if PLAN_SCOPE not in account.get("scopes", []):
                params["prompt"] = "consent"
        return ISSUER + "/api/accounts/authorize?" + urlencode(params)

    def exchange_form(self, query):
        if any(len(values) != 1 for values in query.values()):
            raise MoruError("CHATGPT_AUTH_FAILED")
        values = {key: values[0] for key, values in query.items()}
        state = values.get("state", "")
        if not state.isascii() or not hmac.compare_digest(state, self.state):
            raise MoruError("CHATGPT_AUTH_FAILED")
        if values.get("error"):
            raise MoruError("CHATGPT_AUTH_FAILED")
        issued = values.get("client_id", self.client_id)
        if (
            not issued.startswith("oaiapp_")
            or not values.get("code")
            or (self.client_id != "dynamic_agent_client" and issued != self.client_id)
        ):
            raise MoruError("CHATGPT_AUTH_FAILED")
        return {
            "grant_type": "authorization_code",
            "client_id": issued,
            "code": values["code"],
            "code_verifier": self.verifier,
            "redirect_uri": self.redirect_uri,
            "resource": RESOURCE,
        }


class IdTokenValidator:
    def __init__(self, http):
        self.http = http

    def __call__(self, token, client_id, nonce=None):
        try:
            config = self.http.json(ISSUER + "/.well-known/openid-configuration")
            if config["issuer"] != ISSUER:
                raise ValueError("issuer mismatch")
            keys = self.http.json(trusted_auth_url(config["jwks_uri"]))["keys"]
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise ValueError("unsupported signature")
            matching = [key for key in keys if key.get("kid") == header.get("kid")]
            if len(matching) != 1:
                raise ValueError("unknown signing key")
            key = jwt.PyJWK.from_dict(matching[0], algorithm="RS256").key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub"]},
            )
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise ValueError("missing subject")
            if nonce is not None and not hmac.compare_digest(claims.get("nonce", ""), nonce):
                raise ValueError("nonce mismatch")
            return claims
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise MoruError("CHATGPT_AUTH_FAILED") from None


class ChatGPTAuth:
    def __init__(self, store, *, http=None, validate=None, now=time.time, open_browser=None):
        self.store = store
        self.http = http or ChatGPTHttp()
        self.validate = validate or IdTokenValidator(self.http)
        self.now = now
        self.open_browser = open_browser or webbrowser.open
        self._lock = RLock()
        self._storage_error = None
        try:
            saved = store.load()
        except MoruError as exc:
            saved = None
            self._storage_error = exc.code
        self._values = saved or {
            "host_id": "urn:uuid:" + str(uuid.uuid4()),
            "accounts": {},
            "active": None,
        }
        self._login_cancelled = Event()
        self._thread = None
        self._login_state = "idle"
        self._error = None

    @contextmanager
    def _session(self):
        with self._lock, self.store.locked():
            saved = self.store.load()
            if saved:
                self._values = saved
            self._storage_error = None
            yield

    def status(self):
        with self._lock:
            active = self._values["active"]
            account = self._values["accounts"].get(active, {})
            return {
                "connected": bool(account.get("access_token")),
                "plan_enabled": PLAN_SCOPE in account.get("scopes", []),
                "active_account": active,
                "email": account.get("email"),
                "accounts": [
                    {
                        "id": key,
                        "email": value.get("email"),
                        "connected": bool(value.get("access_token")),
                    }
                    for key, value in self._values["accounts"].items()
                ],
                "login_state": self._login_state,
                "error_code": self._error or self._storage_error,
                "welcome_pending": bool(account.get("welcome_pending")),
            }

    def _commit(self, values):
        # Memory only changes after durable, atomic storage succeeds.
        self.store.save(values)
        self._values = values

    def _save_account(self, client_id, account, *, activate=False):
        values = {**self._values, "accounts": {**self._values["accounts"], client_id: account}}
        if activate:
            values["active"] = client_id
        self._commit(values)

    def accept_callback(self, attempt, query, cancelled=None):
        form = attempt.exchange_form(query)
        result = self.http.json(TOKEN_URL, form=form)
        identity = self.validate(result.get("id_token", ""), form["client_id"], attempt.nonce)
        with self._session():
            if cancelled is not None and cancelled.is_set():
                raise MoruError("GENERATION_CANCELLED")
            old = self._values["accounts"].get(form["client_id"], {})
            if old and old["subject"] != identity["sub"]:
                raise MoruError("CHATGPT_AUTH_FAILED")
            account = self._token_record(result, old)
            account.update(subject=identity["sub"], email=identity.get("email"))
            account["welcome_pending"] = PLAN_SCOPE in account["scopes"] and not old.get(
                "welcome_seen", False
            )
            self._save_account(form["client_id"], account, activate=True)

    def _token_record(self, result, old):
        try:
            if result["token_type"].lower() != "bearer":
                raise ValueError("invalid token type")
            if not isinstance(result["access_token"], str) or not result["access_token"]:
                raise ValueError("missing token")
            scopes = result.get("scope", " ".join(old.get("scopes", []))).split()
            refresh_token = result.get("refresh_token")
            if "offline_access" in scopes and (
                not isinstance(refresh_token, str) or not refresh_token
            ):
                raise ValueError("missing renewable session")
            lifetime = result["expires_in"]
            if type(lifetime) is not int or lifetime <= 0:
                raise ValueError("invalid expiry")
            return {
                **old,
                "access_token": result["access_token"],
                "refresh_token": refresh_token,
                "id_token": result.get("id_token", old.get("id_token")),
                "expires_at": self.now() + lifetime,
                "scopes": scopes,
            }
        except (KeyError, TypeError, AttributeError, ValueError):
            raise MoruError("CHATGPT_AUTH_FAILED") from None

    def login(self, account_id=None):
        with self._session():
            if account_id is not None and not isinstance(account_id, str):
                raise MoruError("INVALID_SETTINGS")
            if self._login_state == "waiting":
                raise MoruError("GENERATION_BUSY")
            if self._thread is not None and self._thread.is_alive():
                raise MoruError("GENERATION_BUSY")
            account = self._values["accounts"].get(account_id) if account_id else None
            if account_id and account is None:
                raise MoruError("INVALID_SETTINGS")
            owner = self
            callback = {}

            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass  # Callback URLs contain authorization codes.

                def do_GET(self):
                    parsed = urlsplit(self.path)
                    if parsed.path != "/auth/callback":
                        self.send_error(404)
                        return
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    try:
                        if query.get("error"):
                            state = query.get("state", [])
                            if (
                                len(state) != 1
                                or not state[0].isascii()
                                or not hmac.compare_digest(state[0], attempt.state)
                            ):
                                raise MoruError("CHATGPT_AUTH_FAILED")
                        else:
                            attempt.exchange_form(query)
                    except MoruError:
                        self.send_error(400, "Invalid authorization callback")
                        return
                    callback.update(query)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(b"Return to Moru to finish signing in.")

            try:
                server = HTTPServer(("127.0.0.1", 0), Callback)
            except OSError as exc:
                raise MoruError("CHATGPT_AUTH_FAILED") from exc
            server.timeout = 0.2
            attempt = AuthorizationAttempt(
                account_id or "dynamic_agent_client",
                f"http://127.0.0.1:{server.server_port}/auth/callback",
                self._values["host_id"],
            )
            try:
                self._commit(self._values)
            except Exception:
                server.server_close()
                raise
            self._login_cancelled = Event()
            cancelled = self._login_cancelled
            self._login_state, self._error = "waiting", None

            def listen():
                try:
                    deadline = owner.now() + 300
                    while not callback and not cancelled.is_set() and owner.now() < deadline:
                        server.handle_request()
                    if cancelled.is_set():
                        return
                    if not callback:
                        raise MoruError("CHATGPT_AUTH_FAILED")
                    owner.accept_callback(attempt, callback, cancelled)
                    with owner._lock:
                        if not cancelled.is_set():
                            owner._login_state = "completed"
                except Exception as exc:
                    with owner._lock:
                        if not cancelled.is_set():
                            owner._login_state = "failed"
                            owner._error = (
                                exc.code if isinstance(exc, MoruError) else "CHATGPT_AUTH_FAILED"
                            )
                finally:
                    server.server_close()

            self._thread = Thread(target=listen, name="chatgpt-login", daemon=True)
            self._thread.start()
            try:
                if not self.open_browser(attempt.url(account)):
                    raise MoruError("CHATGPT_AUTH_FAILED")
            except Exception:
                cancelled.set()
                self._login_state, self._error = "failed", "CHATGPT_AUTH_FAILED"
                raise MoruError("CHATGPT_AUTH_FAILED") from None
            return self.status()

    def cancel_login(self):
        with self._lock:
            self._login_cancelled.set()
            self._login_state, self._error = "idle", None
            return self.status()

    def access_token(self, *, rejected_token=None):
        with self._session():
            client_id = self._values["active"]
            account = self._values["accounts"].get(client_id, {})
            if not account.get("access_token"):
                raise MoruError("CHATGPT_SIGN_IN_REQUIRED")
            if PLAN_SCOPE not in account.get("scopes", []):
                raise MoruError("CHATGPT_NOT_ELIGIBLE")
            if not account.get("refresh_token"):
                if account["expires_at"] > self.now() and rejected_token is None:
                    return account["access_token"]
                self._save_account(client_id, self._without_tokens(account))
                raise MoruError("CHATGPT_SIGN_IN_REQUIRED")
            if (
                account["expires_at"] > self.now() + 60
                and rejected_token != account["access_token"]
            ):
                return account["access_token"]
            try:
                result = self.http.json(
                    TOKEN_URL,
                    form={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "refresh_token": account["refresh_token"],
                        "resource": RESOURCE,
                    },
                )
            except ChatGPTHttpError as exc:
                if exc.remote_code in {
                    "invalid_grant",
                    "invalid_refresh_token",
                    "token_expired",
                    "refresh_token_expired",
                    "refresh_token_invalidated",
                    "refresh_token_reused",
                }:
                    self._save_account(client_id, self._without_tokens(account))
                raise
            if result.get("id_token"):
                identity = self.validate(result["id_token"], client_id)
                if identity["sub"] != account["subject"]:
                    raise MoruError("CHATGPT_AUTH_FAILED")
            updated = self._token_record(result, account)
            self._save_account(client_id, updated)
            if PLAN_SCOPE not in updated["scopes"]:
                raise MoruError("CHATGPT_NOT_ELIGIBLE")
            return updated["access_token"]

    @staticmethod
    def _without_tokens(account):
        return {
            key: value
            for key, value in account.items()
            if key not in {"access_token", "refresh_token", "id_token", "expires_at", "scopes"}
        }

    def logout(self):
        with self._session():
            self._login_cancelled.set()
            client_id = self._values["active"]
            account = self._values["accounts"].get(client_id, {})
            confirmed = True
            if account.get("refresh_token"):
                try:
                    config = self.http.json(ISSUER + "/.well-known/openid-configuration")
                    self.http.json(
                        trusted_auth_url(config["revocation_endpoint"]),
                        form={
                            "client_id": client_id,
                            "token": account["refresh_token"],
                            "token_type_hint": "refresh_token",
                        },
                    )
                except (MoruError, KeyError):
                    confirmed = False
            if account:
                self._save_account(client_id, self._without_tokens(account))
            self._login_state, self._error = "idle", None
            return {**self.status(), "revocation_confirmed": confirmed}

    def select_account(self, account_id):
        with self._session():
            if not isinstance(account_id, str):
                raise MoruError("INVALID_SETTINGS")
            if self._login_state == "waiting":
                raise MoruError("GENERATION_BUSY")
            account = self._values["accounts"].get(account_id)
            if not account:
                raise MoruError("INVALID_SETTINGS")
            self._commit({**self._values, "active": account_id})
            return self.status()

    def dismiss_welcome(self):
        with self._session():
            client_id = self._values["active"]
            account = self._values["accounts"].get(client_id)
            if account:
                self._save_account(
                    client_id,
                    {
                        **account,
                        "welcome_pending": False,
                        "welcome_seen": True,
                    },
                )
            return self.status()

    def close(self):
        self._login_cancelled.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
