"""Vault Transit encryption for uploaded files. The key never leaves Vault (DESIGN.md 12)."""
import base64
import json
import urllib.request

from api.settings import env

KEY = "uploads"


def enabled() -> bool:
    return bool(env("VAULT_ADDR"))


def _post(path: str, body: dict) -> dict:
    # VAULT_TOKEN_FILE is where Vault Agent Injector writes the pod's token
    req = urllib.request.Request(
        f"{env('VAULT_ADDR').rstrip('/')}/v1/{path}", data=json.dumps(body).encode(),
        headers={"X-Vault-Token": env("VAULT_TOKEN") or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def encrypt(data: bytes) -> bytes:
    out = _post(f"transit/encrypt/{KEY}", {"plaintext": base64.b64encode(data).decode()})
    return out["data"]["ciphertext"].encode()  # "vault:v1:..."


def decrypt(token: bytes) -> bytes:
    out = _post(f"transit/decrypt/{KEY}", {"ciphertext": token.decode()})
    return base64.b64decode(out["data"]["plaintext"])
