"""/api/roadmap endpoints: placed from the approved resource list, phase text streamed, saved per user, marked
stale, exported."""
import json
import logging
import re

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from core import db as dbmod
from core.agents.scheduler import agent, narrative
from core.models import AgentOutput, RoadmapRecord
from tests.conftest import login
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps, gaps_confirmed_user  # noqa: F401  (fixture)
from tests.test_scheduler_budget import FakeClient


def phase_reply(text):
    """A valid narrative for whichever phase the request is about (the calls run in parallel)."""
    n = int(re.search(r"Phase (\d) of 3", text).group(1))
    ids = json.loads(re.search(r"Practice task ids to reword: (\[.*\])", text).group(1))
    return {
        "name": f"AI phase {n}",
        "first_month": {"theme": f"Theme {2 * n - 1}", "milestone": f"Milestone {2 * n - 1}"},
        "second_month": {"theme": f"Theme {2 * n}", "milestone": f"Milestone {2 * n}"},
        "practice": [{"id": i, "title": f"Exercise {i}"} for i in ids],
        "project": {"title": f"Fraud model {n}", "problem": "Flag fraudulent card payments.",
                    "dataset": "Credit Card Fraud Detection (Kaggle)", "deliverables": ["Notebook", "Write-up"]},
    }


def api_error(text):
    return anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=httpx.Request("POST", "https://x")), body=None)


@pytest.fixture()
def fake(monkeypatch):
    """By default every phase gets valid text; pass replies (dicts, exceptions or functions) to script them."""
    def install(*replies):
        client = FakeClient(replies or [phase_reply] * 3)
        monkeypatch.setattr(narrative, "get_client", lambda: client)
        return client

    install()
    return install


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def generate(client):
    """Runs generation; returns the events and the final RoadmapState."""
    r = client.post("/api/roadmap/generate")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    found = events(r)
    return found, [e["state"] for e in found if "state" in e][-1]


def resource_ids(state):
    return [r["resource"]["id"] for g in state["resources"]["gaps"] for r in g["resources"]]


def approved_user(client, sub, fake_gaps):  # noqa: F811
    """Signed in with confirmed gaps, a resource list and every resource approved. Returns the ids."""
    gaps_confirmed_user(client, sub, fake_gaps)
    ids = resource_ids(client.post("/api/resources/search").json())
    assert client.post("/api/resources/approve").status_code == 200
    return ids


def all_tasks(roadmap):
    return [t for m in roadmap["months"] for w in m["weeks"] for t in w["tasks"]]


def test_requires_an_approved_list(anon, fake_gaps, fake):  # noqa: F811
    client = gaps_confirmed_user(anon, "m1", fake_gaps)
    client.post("/api/resources/search")  # a list exists but is not approved
    state = client.get("/api/roadmap").json()
    assert state["status"] == "none" and state["list_approved"] is False
    assert client.post("/api/roadmap/generate").status_code == 409
    assert client.get("/api/roadmap/export.md").status_code == 404


def test_placed_plan_first_then_each_phase_text(anon, fake_gaps, fake):  # noqa: F811
    ids = approved_user(anon, "m2", fake_gaps)
    assert anon.get("/api/roadmap").json()["list_approved"] is True
    found, state = generate(anon)

    assert [e["type"] for e in found] == ["state"] * 4 + ["done"]
    first = found[0]["state"]["roadmap"]
    assert [p["narrative"] for p in first["phases"]] == ["pending"] * 3  # the plan arrives before any text
    assert sorted(e["phase"] for e in found[1:4]) == [1, 2, 3] and not any(e["notice"] for e in found[1:4])

    roadmap = state["roadmap"]
    assert state["status"] == "ready" and not state["stale"]
    assert [(p["name"], p["narrative"]) for p in roadmap["phases"]] == [(f"AI phase {n}", "ai") for n in (1, 2, 3)]
    assert [m["theme"] for m in roadmap["months"]] == [f"Theme {n}" for n in range(1, 7)]
    # The text never changes the plan.
    assert [(t["id"], t["kind"], t["hours"]) for t in all_tasks(roadmap)] == [
        (t["id"], t["kind"], t["hours"]) for t in all_tasks(first)]
    assert roadmap["budget_hours"] == 8 * 26 and roadmap["total_hours"] <= roadmap["budget_hours"]
    assert len(roadmap["months"]) == 6 and sum(len(m["weeks"]) for m in roadmap["months"]) == 26
    assert all(w["hours"] <= 8 for m in roadmap["months"] for w in m["weeks"])
    # Links come from the approved list, not from the model.
    listed = {r["resource"]["id"]: r["resource"]["url"] for g in anon.get("/api/resources").json()["resources"]["gaps"] for r in g["resources"]}
    linked = {t["resource"]["id"]: t["resource"]["url"] for t in all_tasks(roadmap) if t["resource"]}
    assert linked and all(listed[rid] == url for rid, url in linked.items())
    assert set(linked) | {r["id"] for r in roadmap["unscheduled"]} == set(ids)

    anon.post("/api/auth/logout")
    login(anon, "m2")
    assert anon.get("/api/roadmap").json()["roadmap"] == roadmap
    with dbmod.SessionLocal() as db:  # logged once, with the finished text
        logged = db.scalars(select(AgentOutput).where(AgentOutput.user_id == "m2", AgentOutput.agent == "scheduler")).all()
        assert len(logged) == 1 and logged[0].output["roadmap"]["phases"][0]["narrative"] == "ai"


def test_without_the_llm_a_roadmap_is_still_produced(anon, fake_gaps, monkeypatch):  # noqa: F811
    approved_user(anon, "m5", fake_gaps)
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    found, state = generate(anon)
    assert found[-1]["type"] == "done"
    assert all("ANTHROPIC_API_KEY" in e["notice"] for e in found[1:4])
    assert [p["narrative"] for p in state["roadmap"]["phases"]] == ["default"] * 3
    assert all(p["project"]["dataset"] for p in state["roadmap"]["phases"])


def test_one_failed_phase_keeps_default_text(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m3", fake_gaps)
    fake(*[lambda text: api_error(text) if "Phase 2 of 3" in text else phase_reply(text)] * 4)
    found, state = generate(anon)
    assert [p["narrative"] for p in state["roadmap"]["phases"]] == ["ai", "default", "ai"]
    notices = {e["phase"]: e["notice"] for e in found if "phase" in e}
    assert notices[1] is None and notices[3] is None and "529" in notices[2]


def test_invalid_text_falls_back_after_one_retry(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m4", fake_gaps)
    bad = lambda text: {**phase_reply(text), "name": ""} if "Phase 1 of 3" in text else phase_reply(text)  # noqa: E731
    client = fake(*[bad] * 4)
    found, state = generate(anon)
    assert [p["narrative"] for p in state["roadmap"]["phases"]] == ["default", "ai", "ai"]
    assert len(client.requests) == 4  # phase 1 tried twice, the others once
    assert "didn't pass the checks" in next(e["notice"] for e in found if e.get("phase") == 1)


def test_one_run_at_a_time_and_interrupted_text_shows_as_default(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m10", fake_gaps)
    generate(anon)
    lock = agent._lock("m10")
    with lock:
        assert anon.post("/api/roadmap/generate").status_code == 409
    with dbmod.SessionLocal() as db:  # as if the server stopped while phase 3 was being written
        record = db.get(RoadmapRecord, "m10")
        record.roadmap = {**record.roadmap, "phases": [*record.roadmap["phases"][:2], {**record.roadmap["phases"][2], "narrative": "pending"}]}
        db.commit()
    assert [p["narrative"] for p in anon.get("/api/roadmap").json()["roadmap"]["phases"]] == ["ai", "ai", "default"]


def test_roadmap_goes_stale_when_the_profile_changes(anon, fake_gaps, fake):  # noqa: F811
    # (A changed approval is covered in test_course_graph.py, where the list is refined by chat.)
    approved_user(anon, "m6", fake_gaps)
    assert generate(anon)[1]["stale"] is False

    # A profile edit un-confirms the gaps, so the approval no longer counts.
    anon.put("/api/profile", json={"hours_per_week": 12})
    state = anon.get("/api/roadmap").json()
    assert state["stale"] is True and state["list_approved"] is False
    assert anon.post("/api/roadmap/generate").status_code == 409


def test_markdown_export(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m7", fake_gaps)
    state = generate(anon)[1]
    roadmap, tracking = state["roadmap"], state["tracking"]
    r = anon.get("/api/roadmap/export.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"] and ".md" in r.headers["content-disposition"]
    task = roadmap["months"][0]["weeks"][0]["tasks"][0]
    link = task["resource"]
    for expected in (
        "# AI roadmap: Backend Engineer → AI Engineer",
        f"{roadmap['total_hours']} of 208 budgeted hours planned",
        "## Phase 1: AI phase 1 (months 1–2)",
        "### Month 1: Theme 1",
        f"- [ ] {task['title']} ({task['hours']} h, {tracking['items'][task['id']]['priority']} priority)"
        f" — [{link['title']}]({link['url']})",
        "- [ ] **Milestone (due ",
        ":** Milestone 6",
        "## Immediate next steps",
        "### Portfolio project (phase 3): Fraud model 3",
        "_Nothing planned: catch up or rest._",
    ):
        assert expected in r.text, expected


def test_users_only_see_their_own_roadmap(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m8", fake_gaps)
    generate(anon)
    with TestClient(app, base_url="https://testserver") as other:
        confirmed_user(other, "m9")
        assert other.get("/api/roadmap").json()["status"] == "none"
        assert other.get("/api/roadmap/export.md").status_code == 404
        assert other.post("/api/roadmap/generate").status_code == 409
    assert anon.get("/api/roadmap").json()["status"] == "ready"


def test_generation_time_is_logged(anon, fake_gaps, fake, caplog):  # noqa: F811
    approved_user(anon, "m-timing", fake_gaps)
    with caplog.at_level(logging.INFO, logger="core.agents.scheduler.agent"):
        generate(anon)
    assert "Roadmap generated: plan placed in" in caplog.text and "total" in caplog.text
