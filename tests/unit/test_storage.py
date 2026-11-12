import base64
import os
import urllib.error

import pytest

from api import storage, vault


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from api.settings import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def fake_transit(path, body):
    if path.startswith("transit/encrypt/"):
        return {"data": {"ciphertext": "vault:v1:" + body["plaintext"][::-1]}}
    return {"data": {"plaintext": body["ciphertext"].removeprefix("vault:v1:")[::-1]}}


def test_plain_when_vault_off(store, monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    path, sha = storage.save("c1", b"hello", ".csv")
    assert path.endswith(".csv") and open(path, "rb").read() == b"hello"
    assert storage.load(path) == b"hello"


def test_encrypted_on_disk_when_vault_on(store, monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setattr(vault, "_post", fake_transit)
    path, sha = storage.save("c1", b"GSTIN,Bill No\n27AAPFU0939F1ZV,INV-1", ".csv")
    on_disk = open(path, "rb").read()
    assert path.endswith(".csv.enc") and on_disk.startswith(b"vault:v1:")
    assert b"27AAPFU0939F1ZV" not in on_disk
    assert storage.load(path) == b"GSTIN,Bill No\n27AAPFU0939F1ZV,INV-1"
    assert sha == __import__("hashlib").sha256(b"GSTIN,Bill No\n27AAPFU0939F1ZV,INV-1").hexdigest()


def test_vault_down_writes_nothing(store, monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:9")

    def down(*a):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(vault, "_post", down)
    with pytest.raises(OSError):
        storage.save("c1", b"secret", ".csv")
    assert not any(store.rglob("*.*"))


@pytest.mark.skipif(not os.environ.get("VAULT_TEST_ADDR"), reason="needs a dev Vault")
def test_real_vault_roundtrip(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", os.environ["VAULT_TEST_ADDR"])
    monkeypatch.setenv("VAULT_TOKEN", os.environ["VAULT_TEST_TOKEN"])
    blob = os.urandom(5000)
    token = vault.encrypt(blob)
    assert token.startswith(b"vault:v1:") and base64.b64encode(blob) not in token
    assert vault.decrypt(token) == blob


def test_purge_removes_only_old_files(store):
    import time

    old, _ = storage.save("c1", b"old", ".csv")
    new, _ = storage.save("c2", b"new", ".csv")
    past = time.time() - 91 * 86400
    os.utime(old, (past, past))
    assert storage.purge(90) == 1
    assert not os.path.exists(old) and os.path.exists(new)
    assert storage.purge(90) == 0
