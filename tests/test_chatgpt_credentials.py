import sys

import pytest

from moru.chatgpt.credentials import CredentialStore, credential_path
from moru.errors import MoruError


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI contract")
def test_dpapi_roundtrip_does_not_store_plaintext_tokens_in_portable_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "windows-user"))
    path = credential_path()
    store = CredentialStore(path)
    values = {
        "host_id": "host",
        "active": "oaiapp_moru",
        "accounts": {
            "oaiapp_moru": {"subject": "subject", "access_token": "sensitive-access-token"},
        },
    }
    with store.locked():
        store.save(values)
    assert store.load() == values
    assert b"sensitive-access-token" not in path.read_bytes()
    assert path.parent == tmp_path / "windows-user" / "Moru"
    assert not path.with_suffix(".part").exists()


def test_missing_credential_file_is_a_disconnected_state(tmp_path):
    assert CredentialStore(tmp_path / "credentials").load() is None


def test_corrupt_credential_file_reports_a_secure_storage_error(tmp_path):
    path = tmp_path / "credentials"
    path.write_bytes(b"invalid encrypted file")
    with pytest.raises(MoruError) as error:
        CredentialStore(path).load()
    assert error.value.code == "CHATGPT_SECURE_STORAGE_UNAVAILABLE"
