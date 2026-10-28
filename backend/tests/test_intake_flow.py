"""Exercises the intake tool loop and profile API with a fake LLM (no network)."""
from types import SimpleNamespace

import pytest

from core.agents.intake import agent
from tests.conftest import login
from tests.test_gap_analysis import CAPABILITIES


class FakeStream:
    def __init__(self, text, tool_input):
        self.text_stream = iter([text])
        blocks = []
        if tool_input is not None:
            blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    id="t1",
                    name="record_profile",
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
def client(anon):
    return login(anon, "t1")


def test_tool_loop_validates_and_saves(client, monkeypatch):
    fake = FakeClient(
        [
            ("Got it.", {"current_role": "Backend Engineer", "hours_per_week": 50}),  # 50 must be rejected
            ("How many hours (1-40)?", None),
        ]
    )
    monkeypatch.setattr(agent, "get_client", lambda: fake)
    r = client.post("/api/intake/chat", json={"message": "I'm a backend engineer, 50 hrs"})
    assert r.status_code == 200 and "event: done" in r.text
    state = client.get("/api/intake").json()
    p = state["profile"]
    assert p["current_role"] == "Backend Engineer"
    assert p["hours_per_week"] is None and "hours_per_week" in p["missing"]
    assert len(state["messages"]) == 2


def test_edit_and_confirm(client):
    assert client.put("/api/profile", json={"hours_per_week": 99}).status_code == 422
    assert client.post("/api/profile/confirm").status_code == 422  # incomplete
    full = dict(
        current_role="Data Analyst", target_role="Data Scientist", years_experience=3,
        domain="Healthcare", hours_per_week=5, capabilities=CAPABILITIES,
    )
    assert client.put("/api/profile", json=full).status_code == 200
    assert client.post("/api/profile/confirm").json()["confirmed"] is True
    # editing after confirming requires re-confirmation
    assert client.put("/api/profile", json={"hours_per_week": 6}).json()["confirmed"] is False


def test_missing_api_key_gives_friendly_error(client, monkeypatch):
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    r = client.post("/api/intake/chat", json={"message": "hi"})
    assert "event: error" in r.text and "ANTHROPIC_API_KEY" in r.text
