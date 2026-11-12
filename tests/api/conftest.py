import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

ADMIN = {"email": "ca@example.com", "password": "correct horse battery"}


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    os.environ.update(DATABASE_URL=f"sqlite:///{tmp / 'test.db'}", JWT_SECRET="x" * 32,
                      UPLOAD_DIR=str(tmp / "uploads"), ADMIN_EMAIL=ADMIN["email"],
                      ADMIN_PASSWORD=ADMIN["password"])
    os.environ.pop("REDIS_URL", None)
    command.upgrade(Config("alembic.ini"), "head")  # tests run on the real migrations
    from api.main import app

    return app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/v1/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
