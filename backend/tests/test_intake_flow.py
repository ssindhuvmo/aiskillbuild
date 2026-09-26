"""Exercises the intake tool loop and profile API with a fake LLM (no network)."""
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory; set before core.db is imported

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core import db as dbmod  # noqa: E402

dbmod.engine.dispose()
dbmod.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
dbmod.SessionLocal.configure(bind=dbmod.engine)

from app.main import app  # noqa: E402
from core.agents.intake import agent  # noqa: E402


class FakeStream:
    def __init__(self, text, tool_input):
        self.text_stream = iter([text])
        blocks = []
        if tool_input is not None:
            blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    id="t1",
                    input=tool_input,
                    model_dump=lambda: {"type": "tool_use", "id": "t1", "name": "record_profile", "input": tool_input},
                )
            )
        self._final = SimpleNamespace(content=blocks)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


class FakeClient:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.messages = SimpleNamespace(stream=lambda **kw: FakeStream(*self.scripted.pop(0)))


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_tool_loop_validates_and_saves(client, monkeypatch):
    fake = FakeClient(
        [
            ("Got it.", {"current_role": "Backend Engineer", "hours_per_week": 50}),  # 50 must be rejected
            ("How many hours (1-40)?", None),
        ]
    )
    monkeypatch.setattr(agent, "get_client", lambda: fake)
    r = client.post("/api/users/t1/intake/chat", json={"message": "I'm a backend engineer, 50 hrs"})
    assert r.status_code == 200 and "event: done" in r.text
    state = client.get("/api/users/t1/intake").json()
    p = state["profile"]
    assert p["current_role"] == "Backend Engineer"
    assert p["hours_per_week"] is None and "hours_per_week" in p["missing"]
    assert len(state["messages"]) == 2


def test_edit_and_confirm(client):
    assert client.put("/api/users/t2/profile", json={"hours_per_week": 99}).status_code == 422
    assert client.post("/api/users/t2/profile/confirm").status_code == 422  # incomplete
    full = dict(
        current_role="Data Analyst", target_role="Data Scientist", ai_level="None",
        ai_knowledge_text="nothing yet", domain="Healthcare", hours_per_week=5,
    )
    assert client.put("/api/users/t2/profile", json=full).status_code == 200
    assert client.post("/api/users/t2/profile/confirm").json()["confirmed"] is True
    # editing after confirming requires re-confirmation
    assert client.put("/api/users/t2/profile", json={"hours_per_week": 6}).json()["confirmed"] is False


def test_missing_api_key_gives_friendly_error(client, monkeypatch):
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    r = client.post("/api/users/t3/intake/chat", json={"message": "hi"})
    assert "event: error" in r.text and "ANTHROPIC_API_KEY" in r.text
