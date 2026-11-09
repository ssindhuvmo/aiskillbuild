"""The AI Career Transition Report (milestone 10): two LLM sections (faked), the rest assembled from saved
data; plain default text when the AI fails; stale tracking; Markdown and PDF exports; per-user data."""
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from core import db as dbmod
from core.agents.report import agent
from core.agents.report.export import SECTIONS
from core.agents.report.schemas import ReportNarrative
from core.models import AgentOutput
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, fake, generate  # noqa: F401  (fixture)

FIT = "Your backend experience carries over well: you already build and run production services. " * 2
STRATEGY = "Start with the foundations, then build a portfolio project in each phase for your domain. " * 2


def good():
    return {"career_fit": FIT, "strategy": STRATEGY}


class FakeClient:
    """messages.parse validates each scripted reply like the SDK does (a dict, an exception or a function)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kw):
        text = kw["messages"][0]["content"]
        self.requests.append(text)
        reply = self.replies.pop(0) if self.replies else good()
        reply = reply(text) if callable(reply) else reply
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(parsed_output=ReportNarrative.model_validate(reply))


@pytest.fixture()
def report_llm(monkeypatch):
    """Valid text by default; call it with replies to script them."""
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return client

    install()
    return install


def ready_user(client, sub, fake_gaps):  # noqa: F811
    """Signed in with an approved list and a generated roadmap."""
    approved_user(client, sub, fake_gaps)
    generate(client)
    return client


def test_needs_a_current_roadmap(anon, fake_gaps, fake, report_llm):  # noqa: F811
    confirmed_user(anon, "rp1")
    assert anon.get("/api/report").json() == {
        "status": "none", "can_generate": False, "stale": False, "report": None, "notice": None}
    assert anon.post("/api/report/generate").status_code == 409
    assert anon.get("/api/report/export.md").status_code == 404
    assert anon.get("/api/report/export.pdf").status_code == 404


def test_report_assembled_from_saved_data(anon, fake_gaps, fake, report_llm):  # noqa: F811
    ready_user(anon, "rp2", fake_gaps)
    assert anon.get("/api/report").json()["can_generate"] is True
    client = report_llm(good())
    r = anon.post("/api/report/generate")
    assert r.status_code == 200
    state = r.json()
    report = state["report"]
    assert state["status"] == "ready" and not state["stale"] and state["notice"] is None
    assert report["narrative_source"] == "ai"
    assert report["career_fit"] == FIT and report["strategy"] == STRATEGY
    assert "<facts>" in client.requests[0] and "AI Engineer" in client.requests[0]

    roadmap = anon.get("/api/roadmap").json()
    gaps = anon.get("/api/gaps").json()["analysis"]
    assert report["career_goal"]["target_role"] == "AI Engineer"
    assert report["transferable_skills"] == gaps["strengths"] and report["gaps"] == gaps["gaps"]
    assert {i["skill"] for i in report["learning_plan"]} == {g["skill"] for g in gaps["gaps"]}
    # Links come from the approved list.
    listed = {r["resource"]["url"] for g in anon.get("/api/resources").json()["resources"]["gaps"] for r in g["resources"]}
    assert report["resources"] and {x["url"] for x in report["resources"]} == listed
    assert [p["name"] for p in report["roadmap"]] == [p["name"] for p in roadmap["roadmap"]["phases"]]
    assert [m["due"] for p in report["roadmap"] for m in p["milestones"]] == [
        roadmap["tracking"]["items"][f"m{n}"]["due"] for n in range(1, 7)]
    assert [p["title"] for p in report["projects"]] == [p["project"]["title"] for p in roadmap["roadmap"]["phases"]]
    assert report["next_steps"] == roadmap["tracking"]["next_steps"]
    assert report["start_date"] == roadmap["start_date"]

    with dbmod.SessionLocal() as db:
        logged = db.scalars(select(AgentOutput).where(AgentOutput.user_id == "rp2", AgentOutput.agent == "report")).all()
        assert len(logged) == 1 and logged[0].output["source"] == "ai"

    # Ticking a task updates the next steps but doesn't make the text stale.
    first = report["next_steps"][0]["task_id"]
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})
    state = anon.get("/api/report").json()
    assert not state["stale"] and first not in [s["task_id"] for s in state["report"]["next_steps"]]


def test_links_and_percentages_are_retried(anon, fake_gaps, fake, report_llm):  # noqa: F811
    ready_user(anon, "rp3", fake_gaps)
    client = report_llm({"career_fit": FIT + " See https://example.com.", "strategy": STRATEGY + " You are 80% ready."}, good())
    state = anon.post("/api/report/generate").json()
    assert state["report"]["narrative_source"] == "ai" and len(client.requests) == 2
    assert "rejected" in client.requests[1] and "URLs" in client.requests[1] and "percentages" in client.requests[1]


@pytest.mark.parametrize("replies, says", [
    ((anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=httpx.Request("POST", "https://x")),
                               body=None),), "plain text: The AI service returned an error (529)"),
    (({"career_fit": FIT + " www.x.com", "strategy": STRATEGY},) * 2, "didn't pass the checks"),
])
def test_default_text_when_the_ai_fails(anon, fake_gaps, fake, report_llm, replies, says):  # noqa: F811
    sub = "rp4" if "529" in says else "rp5"
    ready_user(anon, sub, fake_gaps)
    report_llm(*replies)
    state = anon.post("/api/report/generate").json()
    assert says in state["notice"]
    report = state["report"]
    assert report["narrative_source"] == "default"
    gaps = anon.get("/api/gaps").json()["analysis"]
    assert gaps["rationale"] in report["career_fit"] and "Phase 1" in report["strategy"]
    assert anon.get("/api/report").json()["notice"] is None  # the notice belongs to that reply only


def test_stale_after_the_profile_changes(anon, fake_gaps, fake, report_llm):  # noqa: F811
    ready_user(anon, "rp6", fake_gaps)
    anon.post("/api/report/generate")
    assert anon.put("/api/profile", json={"hours_per_week": 10}).status_code == 200
    state = anon.get("/api/report").json()
    assert state["status"] == "ready" and state["stale"] and state["can_generate"] is False
    assert anon.post("/api/report/generate").status_code == 409


def test_exports(anon, fake_gaps, fake, report_llm):  # noqa: F811
    ready_user(anon, "rp7", fake_gaps)
    report = anon.post("/api/report/generate").json()["report"]
    md = anon.get("/api/report/export.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    text = md.text
    positions = [text.index(f"## {n}. {name}") for n, name in enumerate(SECTIONS, start=1)]
    assert positions == sorted(positions) and len(SECTIONS) == 11
    first = report["resources"][0]
    assert f"[{first['title']}]({first['url']})" in text
    assert "# AI Career Transition Report: Backend Engineer → AI Engineer" in text
    pdf = anon.get("/api/report/export.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-") and "attachment" in pdf.headers["content-disposition"]


def test_users_only_see_their_own_report(anon, fake_gaps, fake, report_llm):  # noqa: F811
    ready_user(anon, "rp8", fake_gaps)
    anon.post("/api/report/generate")
    with TestClient(app, base_url="https://testserver") as other:
        confirmed_user(other, "rp9")
        assert other.get("/api/report").json()["status"] == "none"
        assert other.get("/api/report/export.md").status_code == 404
        assert other.get("/api/report/export.pdf").status_code == 404
    assert anon.get("/api/report").json()["status"] == "ready"
