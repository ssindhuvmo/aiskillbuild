"""/api/roadmap endpoints: built from the approved resource list, saved per user, marked stale, exported."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.agents.scheduler import agent
from tests.conftest import login
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps, gaps_confirmed_user  # noqa: F401  (fixture)
from tests.test_scheduler_budget import TRUNCATED, FakeClient, draft


@pytest.fixture()
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return client

    return install


def resource_ids(state):
    return [r["resource"]["id"] for g in state["resources"]["gaps"] for r in g["resources"]]


def approved_user(client, sub, fake_gaps):  # noqa: F811
    """Signed in with confirmed gaps, a resource list and every resource approved. Returns the ids."""
    gaps_confirmed_user(client, sub, fake_gaps)
    ids = resource_ids(client.post("/api/resources/search").json())
    assert client.post("/api/resources/approve").status_code == 200
    return ids


def test_requires_an_approved_list(anon, fake_gaps, fake):  # noqa: F811
    client = gaps_confirmed_user(anon, "m1", fake_gaps)
    client.post("/api/resources/search")  # a list exists but is not approved
    state = client.get("/api/roadmap").json()
    assert state["status"] == "none" and state["list_approved"] is False
    assert client.post("/api/roadmap/generate").status_code == 409
    assert client.get("/api/roadmap/export.md").status_code == 404


def test_generate_saves_roadmap_within_budget(anon, fake_gaps, fake):  # noqa: F811
    ids = approved_user(anon, "m2", fake_gaps)
    assert anon.get("/api/roadmap").json()["list_approved"] is True
    fake(draft(per_week=8, resource_id=ids[0]))
    state = anon.post("/api/roadmap/generate").json()
    roadmap = state["roadmap"]
    assert state["status"] == "ready" and not state["stale"]
    assert roadmap["budget_hours"] == 8 * 26 and roadmap["total_hours"] <= roadmap["budget_hours"]
    assert len(roadmap["months"]) == 6 and sum(len(m["weeks"]) for m in roadmap["months"]) == 26
    assert all(w["hours"] <= 8 for m in roadmap["months"] for w in m["weeks"])
    # The link comes from the approved list, not from the model.
    listed = {r["resource"]["id"]: r["resource"]["url"] for g in anon.get("/api/resources").json()["resources"]["gaps"] for r in g["resources"]}
    assert roadmap["months"][0]["weeks"][0]["tasks"][0]["resource"]["url"] == listed[ids[0]]
    assert sorted(r["id"] for r in roadmap["unscheduled"]) == sorted(ids[1:])

    anon.post("/api/auth/logout")
    login(anon, "m2")
    assert anon.get("/api/roadmap").json()["roadmap"] == roadmap


def test_over_budget_roadmap_is_never_saved(anon, fake_gaps, fake):  # noqa: F811
    ids = approved_user(anon, "m3", fake_gaps)
    fake(*[draft(per_week=9, resource_id=ids[0])] * agent.MAX_ATTEMPTS)
    r = anon.post("/api/roadmap/generate")
    assert r.status_code == 502 and "weekly hours" in r.json()["detail"]
    assert anon.get("/api/roadmap").json()["status"] == "none"


def test_truncated_reply_gives_a_clear_error(anon, fake_gaps, fake):  # noqa: F811
    approved_user(anon, "m4", fake_gaps)
    fake(TRUNCATED)
    r = anon.post("/api/roadmap/generate")
    assert r.status_code == 502 and "cut off" in r.json()["detail"]


def test_llm_failure_gives_friendly_error(anon, fake_gaps, monkeypatch):  # noqa: F811
    approved_user(anon, "m5", fake_gaps)
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    r = anon.post("/api/roadmap/generate")
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_roadmap_goes_stale_when_the_profile_changes(anon, fake_gaps, fake):  # noqa: F811
    # (A changed approval is covered in test_course_graph.py, where the list is refined by chat.)
    ids = approved_user(anon, "m6", fake_gaps)
    fake(draft(resource_id=ids[0]))
    assert anon.post("/api/roadmap/generate").json()["stale"] is False

    # A profile edit un-confirms the gaps, so the approval no longer counts.
    anon.put("/api/profile", json={"hours_per_week": 12})
    state = anon.get("/api/roadmap").json()
    assert state["stale"] is True and state["list_approved"] is False
    assert anon.post("/api/roadmap/generate").status_code == 409


def test_markdown_export(anon, fake_gaps, fake):  # noqa: F811
    ids = approved_user(anon, "m7", fake_gaps)
    fake(draft(resource_id=ids[0]))
    roadmap = anon.post("/api/roadmap/generate").json()["roadmap"]
    r = anon.get("/api/roadmap/export.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"] and ".md" in r.headers["content-disposition"]
    link = roadmap["months"][0]["weeks"][0]["tasks"][0]["resource"]
    for expected in (
        "# AI roadmap: Backend Engineer → AI Engineer",
        "208 of 208 budgeted hours planned",
        "### Month 1: Theme 1",
        "#### Week 26: Focus 26 (8 h)",
        f"- [ ] Start the course (1 h) — [{link['title']}]({link['url']})",
        "**Milestone:** Milestone 6",
        "### Portfolio project (phase 3): Fraud model 3",
        "## Approved but not scheduled",
    ):
        assert expected in r.text, expected


def test_users_only_see_their_own_roadmap(anon, fake_gaps, fake):  # noqa: F811
    ids = approved_user(anon, "m8", fake_gaps)
    fake(draft(resource_id=ids[0]))
    anon.post("/api/roadmap/generate")
    with TestClient(app, base_url="https://testserver") as other:
        confirmed_user(other, "m9")
        assert other.get("/api/roadmap").json()["status"] == "none"
        assert other.get("/api/roadmap/export.md").status_code == 404
        assert other.post("/api/roadmap/generate").status_code == 409
    assert anon.get("/api/roadmap").json()["status"] == "ready"
