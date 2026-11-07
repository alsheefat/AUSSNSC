import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "UPLOAD_DIR": f"{_tmp}/uploads",
    "SECRET_KEY": "test-secret-key-test-secret-key-1234",
    "ADMIN_PHONE": "01711111111",
    "ADMIN_PASSWORD": "AdminPass123",
    "SEED_DEMO": "1",
})

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:   # runs lifespan: creates tables + seeds
        yield c


def login(client, ident, password):
    r = client.post("/api/v1/auth/login", json={"identifier": ident, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "01711111111", "AdminPass123")


@pytest.fixture(scope="session")
def student(client):
    return login(client, "01700000001", "Demo12345")


@pytest.fixture(scope="session")
def teacher(client):
    return login(client, "01700000002", "Demo12345")


@pytest.fixture(scope="session")
def parent(client):
    return login(client, "01700000003", "Demo12345")
