"""/api/resources endpoints: built from the confirmed gap analysis, saved per user, marked stale."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.agents.gap_analysis import agent as gap_agent
from tests.conftest import login
from tests.test_gap_analysis import FakeClient, analysis, confirmed_user


# Gaps the knowledge base covers above the relevance gate (deep learning: several; PCI-DSS: the FinTech guide).
COVERED = (("Deep learning", 40), ("PCI-DSS", 10))


@pytest.fixture()
def fake_gaps(monkeypatch):
    def install(*replies):
        monkeypatch.setattr(gap_agent, "get_client", lambda: FakeClient(replies or [analysis(gaps=COVERED)]))

    return install


def gaps_confirmed_user(client, sub, fake_gaps):
    confirmed_user(client, sub)
    fake_gaps()
    assert client.post("/api/gaps/analyze", json={}).status_code == 200
    assert client.post("/api/gaps/confirm").status_code == 200
    return client


def test_requires_confirmed_gaps(anon, fake_gaps):
    client = confirmed_user(anon, "r1")
    state = client.get("/api/resources").json()
    assert state["status"] == "none" and state["gaps_confirmed"] is False
    assert client.post("/api/resources/search").status_code == 409
    fake_gaps()
    client.post("/api/gaps/analyze", json={})  # analyzed but not confirmed yet
    assert client.post("/api/resources/search").status_code == 409


def test_search_saves_ranked_list_per_gap(anon, fake_gaps):
    client = gaps_confirmed_user(anon, "r2", fake_gaps)
    assert client.get("/api/resources").json()["gaps_confirmed"] is True
    state = client.post("/api/resources/search").json()
    assert state["status"] == "ready" and not state["stale"]
    gaps = state["resources"]["gaps"]
    assert [g["gap"]["skill"] for g in gaps] == ["Deep learning", "PCI-DSS"]
    ml, pci = gaps
    assert 1 <= len(ml["resources"]) <= 4
    assert pci["resources"][0]["resource"]["id"] == "pci-dss-library"  # the FinTech compliance resource
    first = ml["resources"][0]
    assert first["resource"]["url"].startswith("https://")
    assert set(first["breakdown"]) == {"relevance", "level", "domain", "time"}

    client.post("/api/auth/logout")
    login(client, "r2")
    assert client.get("/api/resources").json()["resources"] == state["resources"]


def test_list_goes_stale_when_gaps_or_profile_change(anon, fake_gaps):
    client = gaps_confirmed_user(anon, "r3", fake_gaps)
    client.post("/api/resources/search")

    # Re-running the gap analysis with different gaps (and re-confirming) makes the list stale.
    fake_gaps(analysis(gaps=(("Deep learning with PyTorch", 30),)))
    client.post("/api/gaps/analyze", json={})
    client.post("/api/gaps/confirm")
    state = client.get("/api/resources").json()
    assert state["stale"] is True and state["gaps_confirmed"] is True
    state = client.post("/api/resources/search").json()
    assert not state["stale"] and state["resources"]["gaps"][0]["gap"]["skill"] == "Deep learning with PyTorch"

    # A profile edit un-confirms the gaps: stale, and no new search until they are re-confirmed.
    client.put("/api/profile", json={"hours_per_week": 12})
    state = client.get("/api/resources").json()
    assert state["stale"] is True and state["gaps_confirmed"] is False
    assert client.post("/api/resources/search").status_code == 409


def ids_of(state):
    return [r["resource"]["id"] for g in state["resources"]["gaps"] for r in g["resources"]]


def test_approve_saves_the_whole_list(anon, fake_gaps):
    client = gaps_confirmed_user(anon, "r6", fake_gaps)
    assert client.post("/api/resources/approve").status_code == 409  # no list yet
    state = client.post("/api/resources/search").json()
    assert state["approved_ids"] is None
    ids = ids_of(state)

    state = client.post("/api/resources/approve").json()
    assert state["approved_ids"] == ids and state["approval_stale"] is False

    client.post("/api/auth/logout")
    login(client, "r6")
    assert client.get("/api/resources").json()["approved_ids"] == ids


def test_approval_goes_stale_when_the_list_changes(anon, fake_gaps):
    client = gaps_confirmed_user(anon, "r7", fake_gaps)
    client.post("/api/resources/search")
    client.post("/api/resources/approve")

    fake_gaps(analysis(gaps=(("Deep learning with PyTorch", 30),)))
    client.post("/api/gaps/analyze", json={})
    client.post("/api/gaps/confirm")
    assert client.get("/api/resources").json()["approval_stale"] is True
    assert client.post("/api/resources/approve").status_code == 409  # stale list
    state = client.post("/api/resources/search").json()
    assert state["approval_stale"] is True  # rebuilt, but not approved again yet
    state = client.post("/api/resources/approve").json()
    assert state["approval_stale"] is False


def test_users_only_see_their_own_resources(anon, fake_gaps):
    gaps_confirmed_user(anon, "r4", fake_gaps)
    anon.post("/api/resources/search")
    with TestClient(app, base_url="https://testserver") as other:
        login(other, "r5")
        assert other.get("/api/resources").json()["status"] == "none"
        assert other.post("/api/resources/search").status_code == 409
    assert anon.get("/api/resources").json()["status"] == "ready"
