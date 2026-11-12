"""Uploaded file store. Vault Transit encryption plugs in here (#19)."""
import hashlib
import uuid
from pathlib import Path

from api.settings import get_settings


def save(client_id: uuid.UUID, data: bytes, suffix: str) -> tuple[str, str]:
    """Writes the file, returns (path, sha256 of the plaintext)."""
    folder = Path(get_settings().upload_dir) / str(client_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}{suffix}"
    path.write_bytes(data)
    return str(path), hashlib.sha256(data).hexdigest()
