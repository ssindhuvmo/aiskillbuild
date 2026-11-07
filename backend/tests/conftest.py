"""Test setup: fixed auth config, an in-memory DB, and a fake Google verifier (no network)."""
import os

# Set before core.config / core.db are imported; these override backend/.env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["SESSION_COOKIE_SECURE"] = "true"
os.environ["CHECKPOINT_DB"] = ":memory:"  # the course search graph's checkpoints

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
from core.agents.course_search import verify, web, youtube  # noqa: E402
from core.agents.resume_parser import storage  # noqa: E402
from core.models import WebResourceCandidate, WebSearchCache  # noqa: E402


class FakeSearcher:
    """Stands in for live web search: returns the scripted candidates for a gap's skill name
    (none by default) and records every call."""

    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def search(self, gap, profile, hint=None):
        self.calls.append((gap.skill, hint))
        found = self.results.get(gap.skill, [])
        if isinstance(found, Exception):
            raise found
        return list(found)


class FakeYouTube:
    """Stands in for the YouTube Data API: scripted candidates per skill (none by default)."""

    def __init__(self):
        self.results = {}
        self.calls = []

    def search(self, gap, profile):
        self.calls.append(gap.skill)
        found = self.results.get(gap.skill, [])
        if isinstance(found, Exception):
            raise found
        return list(found)


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


@pytest.fixture(autouse=True)
def searcher(monkeypatch):
    """No network: web search finds nothing unless a test fills `searcher.results`, YouTube nothing unless
    a test fills `searcher.youtube.results`, and every link checks out unless a test sets
    `searcher.link_status[url]`."""
    fake = FakeSearcher()
    fake.link_status = {}
    fake.youtube = FakeYouTube()
    monkeypatch.setattr(web, "get_searcher", lambda: fake)
    monkeypatch.setattr(youtube, "get_youtube", lambda: fake.youtube)
    monkeypatch.setattr(verify, "get_checker", lambda: lambda url: (fake.link_status.get(url, "ok"), "fake"))
    return fake


@pytest.fixture(autouse=True)
def uploads(monkeypatch, tmp_path):
    """Uploaded resumes go to a temporary folder."""
    folder = tmp_path / "uploads"
    monkeypatch.setattr(storage, "UPLOAD_DIR", folder)
    return folder


@pytest.fixture()
def anon():
    # https base URL so the Secure session cookie is sent back.
    with TestClient(app, base_url="https://testserver") as c:
        with dbmod.SessionLocal() as db:  # tables shared across users, so also across tests
            db.query(WebSearchCache).delete()
            db.query(WebResourceCandidate).delete()
            db.commit()
        yield c


def login(client: TestClient, sub: str) -> TestClient:
    r = client.post("/api/auth/google", json={"credential": f"good:{sub}"})
    assert r.status_code == 200, r.text
    return client
