"""Test setup: fixed auth config, an in-memory DB, and a fake Google verifier (no network)."""
import json
import os
import re

# Set before core.config / core.db are imported; these override backend/.env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["SESSION_COOKIE_SECURE"] = "true"
os.environ["CHECKPOINT_DB"] = ":memory:"  # the course search graph's checkpoints

from types import SimpleNamespace  # noqa: E402

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
from core.agents.job_search import agent as job_agent, source as job_source  # noqa: E402
from core.agents.job_search.schemas import Assessments, JobFinding  # noqa: E402
from core.agents.resume_optimizer import agent as optimizer_agent  # noqa: E402
from core.agents.resume_optimizer.schemas import TailoredText  # noqa: E402
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


class FakeJobSource:
    """Stands in for job search: returns `results` (JobFinding dicts, or an exception) and records each query."""

    def __init__(self):
        self.results = []
        self.calls = []

    def search(self, query, seeker):
        self.calls.append((query, seeker))
        if isinstance(self.results, Exception):
            raise self.results
        return [JobFinding.model_validate(r) for r in self.results]


def assess_nothing(text):
    """A valid assessment that maps no skill: every job's required skills are left uncovered."""
    postings = json.loads(re.search(r"<postings>\n(.*)\n</postings>", text, re.S).group(1))
    return {"jobs": [{"job_id": p["job_id"], "explanation": "A fair fit for your background.",
                      "matches": [{"required": r} for r in p["required_skills"]]} for p in postings]}


class FakeJobLLM:
    """messages.parse for the job assessment: scripted replies (dicts, exceptions or functions of the request
    text); by default every call returns assess_nothing."""

    def __init__(self):
        self.replies = []
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kw):
        text = kw["messages"][0]["content"]
        self.requests.append(text)
        reply = self.replies.pop(0) if self.replies else assess_nothing
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(text)
            if isinstance(reply, Exception):
                raise reply
        return SimpleNamespace(parsed_output=Assessments.model_validate(reply))


def facts_of(text):
    """The <facts> JSON of a resume optimizer request."""
    return json.loads(re.search(r"<facts>\n(.*)\n</facts>", text, re.S).group(1))


def tailor_plainly(text):
    """A valid TailoredText: every role with its own highlights, the first allowed skills, every completed
    project and course, nothing to add."""
    f = facts_of(text)
    return {
        "headline": f["current_role"] or "Professional", "summary": f"Moving into a {f['target_role']} role.",
        "roles": [{"ref": r["ref"], "highlights": r["highlights"]} for r in f["resume"]["roles"]],
        "skills": f["allowed_skills"][:10],
        "projects": [{"ref": p["id"], "bullets": p["deliverables"][:4]} for p in f["completed_projects"][:3]],
        "courses": [c["id"] for c in f["completed_courses"]], "keywords": [], "to_add": [],
    }


class FakeResumeLLM:
    """messages.parse for the resume optimizer: scripted replies (dicts, exceptions or functions of the
    request text); by default tailor_plainly."""

    def __init__(self):
        self.replies = []
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kw):
        text = kw["messages"][0]["content"]
        self.requests.append(text)
        reply = self.replies.pop(0) if self.replies else tailor_plainly
        if callable(reply) and not isinstance(reply, Exception):
            reply = reply(text)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(parsed_output=TailoredText.model_validate(reply))


@pytest.fixture(autouse=True)
def resume_llm(monkeypatch):
    fake = FakeResumeLLM()
    monkeypatch.setattr(optimizer_agent, "get_client", lambda: fake)
    return fake


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
    `searcher.link_status[url]`. Job search returns `searcher.jobs.results`, and the job assessment LLM
    answers with `searcher.job_llm.replies` (by default a mapping that covers nothing)."""
    fake = FakeSearcher()
    fake.link_status = {}
    fake.youtube = FakeYouTube()
    monkeypatch.setattr(web, "get_searcher", lambda: fake)
    monkeypatch.setattr(youtube, "get_youtube", lambda: fake.youtube)
    monkeypatch.setattr(verify, "get_checker", lambda: lambda url: (fake.link_status.get(url, "ok"), "fake"))
    fake.jobs = FakeJobSource()
    fake.job_llm = FakeJobLLM()
    monkeypatch.setattr(job_source, "get_job_source", lambda: fake.jobs)
    monkeypatch.setattr(job_agent, "get_client", lambda: fake.job_llm)
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
