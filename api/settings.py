"""Env-based settings. Any secret can also come as <VAR>_FILE (Vault Agent Injector)."""
import os
from functools import lru_cache


def env(name: str, default: str | None = None) -> str | None:
    path = os.environ.get(f"{name}_FILE")
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return os.environ.get(name, default)


class Settings:
    def __init__(self):
        self.database_url = env("DATABASE_URL", "sqlite:///./dev.db")
        self.redis_url = env("REDIS_URL")  # unset -> jobs run in-process (dev/tests)
        self.jwt_secret = env("JWT_SECRET")
        self.jwt_minutes = int(env("JWT_MINUTES", "60"))
        self.admin_email = env("ADMIN_EMAIL")
        self.admin_password = env("ADMIN_PASSWORD")
        self.upload_dir = env("UPLOAD_DIR", "./data/uploads")
        self.max_upload_mb = int(env("MAX_UPLOAD_MB", "20"))
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set and at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    return Settings()
