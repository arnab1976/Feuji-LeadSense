import os
import tempfile

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("EMAIL_PROVIDER", "console")
os.environ.setdefault("DEMO_CONNECTORS", "true")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.seed import seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded():
    seed()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    resp = client.post("/api/v1/auth/dev-token", json={
        "email": "arnab.das@feuji.com", "name": "Arnab Das",
        "role": "tenant_admin", "tenant_slug": "feuji-revops",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}
