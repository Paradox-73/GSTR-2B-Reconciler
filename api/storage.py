"""Uploaded file store. With VAULT_ADDR set, files are Transit-encrypted before they touch disk."""
import hashlib
import uuid
from pathlib import Path

from api import vault
from api.settings import get_settings

ENCRYPTED = ".enc"


def save(client_id: uuid.UUID, data: bytes, suffix: str) -> tuple[str, str]:
    """Writes the file, returns (path, sha256 of the plaintext)."""
    sha = hashlib.sha256(data).hexdigest()
    if vault.enabled():
        data, suffix = vault.encrypt(data), suffix + ENCRYPTED
    folder = Path(get_settings().upload_dir) / str(client_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}{suffix}"
    path.write_bytes(data)
    return str(path), sha


def load(path: str) -> bytes:
    data = Path(path).read_bytes()
    return vault.decrypt(data) if path.endswith(ENCRYPTED) else data
