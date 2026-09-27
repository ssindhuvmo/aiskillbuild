"""Test setup: fixed auth config, an in-memory DB, and a fake Google verifier (no network)."""
import os

# Set before core.config / core.db are imported; these override backend/.env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["SESSION_COOKIE_SECURE"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core import db as dbmod  # noqa: E402

dbmod.engine.dispose()
dbmod.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
dbmod.SessionLocal.configure(bind=dbmod.engine)

from app.main import app  # noqa: E402
from core import auth  # noqa: E402


def fake_verify(credential: str) -> dict:
    """Accepts tokens shaped "good:<sub>"; anything else is rejected like a bad signature."""
    if not credential.startswith("good:"):
        raise auth.InvalidToken("bad token")
    sub = credential.split(":", 1)[1]
    return {
        "sub": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "name": f"User {sub}",
        "picture": f"https://example.com/{sub}.png",
    }


@pytest.fixture(autouse=True)
def _fake_google(monkeypatch):
    monkeypatch.setattr(auth, "verify_google_token", fake_verify)


@pytest.fixture()
def anon():
    # https base URL so the Secure session cookie is sent back.
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def login(client: TestClient, sub: str) -> TestClient:
    r = client.post("/api/auth/google", json={"credential": f"good:{sub}"})
    assert r.status_code == 200, r.text
    return client
