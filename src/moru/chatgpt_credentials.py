"""User-scoped, atomic Windows DPAPI credential persistence."""

import ctypes
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from moru.application_lock import application_lock
from moru.errors import MoruError


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(content: bytes, *, encrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE")
    buffer = ctypes.create_string_buffer(content)
    source = _Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    # UI_FORBIDDEN; protection is scoped to the current Windows user, never the machine.
    if encrypt:
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
        )
    else:
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
        )
    if not ok:
        raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


class CredentialStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        try:
            encrypted = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE") from exc
        try:
            result = json.loads(_dpapi(encrypted, encrypt=False))
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("host_id"), str)
                or not isinstance(result.get("accounts"), dict)
                or result.get("active") not in (None, *result["accounts"])
                or any(
                    not isinstance(account, dict) or not isinstance(account.get("subject"), str)
                    for account in result["accounts"].values()
                )
            ):
                raise ValueError("invalid credentials")
            return result
        except (ValueError, OSError) as exc:
            raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE") from exc

    def save(self, values):
        encrypted = _dpapi(json.dumps(values).encode("utf-8"), encrypt=True)
        temporary = self.path.with_suffix(".part")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(encrypted)
            os.replace(temporary, self.path)
        except OSError as exc:
            raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE") from exc
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def locked(self):
        # All installations for this Windows user serialize rotating-token updates.
        try:
            with application_lock(self.path.parent):
                yield
        except MoruError as exc:
            if exc.code == "APP_ALREADY_RUNNING":
                raise MoruError("GENERATION_BUSY") from exc
            if exc.code == "DATABASE_FAILED":
                raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE") from exc
            raise


def credential_path() -> Path:
    location = os.environ.get("LOCALAPPDATA")
    if not location:
        raise MoruError("CHATGPT_SECURE_STORAGE_UNAVAILABLE")
    return Path(location) / "Moru" / "chatgpt.dpapi"
