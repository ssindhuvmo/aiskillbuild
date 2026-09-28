"""Gap-analysis agent retries/rules and the /api/gaps endpoints, with a fake LLM (no network)."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.agents.gap_analysis import agent
from core.agents.gap_analysis.schemas import Correction, GapAnalysis, GapInput
from tests.conftest import login

PROFILE = dict(
    current_role="Backend Engineer", target_role="AI Engineer", ai_experience="Beginner",
    domain="FinTech", hours_per_week=8,
)


def analysis(strengths=("Python", "Payments domain"), gaps=(("Machine learning basics", 40), ("PCI-DSS for ML", 10))):
    return {
        "strengths": [
            {"skill": s, "category": "technical", "source": "assumed", "basis": "Typical for the role."}
            for s in strengths
        ],
        "gaps": [
            {"skill": g, "category": "technical", "why_needed": "Core to the role.", "priority": "high",
             "effort_hours": h, "domain_specific": False}
            for g, h in gaps
        ],
        "domain_use_cases": [{"title": "Fraud detection", "description": "Flag bad transactions.", "relevance": "Classic AI Engineer work."}],
        "rationale": "Solid engineering base; focus on ML fundamentals first.",
    }


class FakeClient:
    """messages.parse validates each scripted reply like the SDK does (raising
    ValidationError for bad data) and records the prompts it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kw):
        self.requests.append(kw["messages"][0]["content"])
        return SimpleNamespace(parsed_output=GapAnalysis.model_validate(self.replies.pop(0)))


@pytest.fixture()
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return client

    return install


# --- agent -------------------------------------------------------------------------


def test_invalid_reply_is_retried_with_feedback(fake):
    bad = analysis()
    bad["gaps"][0]["effort_hours"] = 500  # out of range
    client = fake(bad, analysis())
    result = agent.analyze(GapInput(**PROFILE))
    assert len(result.gaps) == 2
    assert "rejected" not in client.requests[0] and "effort_hours" in client.requests[1]


def test_gives_up_after_max_attempts(fake):
    fake(*[{"strengths": []}] * agent.MAX_ATTEMPTS)
    with pytest.raises(agent.GapAnalysisFailed):
        agent.analyze(GapInput(**PROFILE))


def test_ignored_correction_is_retried(fake):
    knows_ml = Correction(kind="knows", skill="Machine learning basics", text="I already know this")
    fixed = analysis(strengths=("Python", "Machine Learning  basics"), gaps=(("PCI-DSS for ML", 10),))
    client = fake(analysis(), fixed)
    result = agent.analyze(GapInput(**PROFILE, corrections=[knows_ml]))
    assert [g.skill for g in result.gaps] == ["PCI-DSS for ML"]
    assert "must not be a gap" in client.requests[1]


def test_rules_catch_duplicates_and_lacks():
    data = GapInput(**PROFILE, corrections=[Correction(kind="lacks", skill="python", text="I don't have this")])
    problems = agent.check_rules(GapAnalysis.model_validate(analysis(gaps=(("Python", 20),))), data)
    assert any("more than once" in p for p in problems)
    assert any("must not be a strength" in p for p in problems)


# --- API ---------------------------------------------------------------------------


def confirmed_user(client, sub):
    login(client, sub)
    assert client.put("/api/profile", json=PROFILE).status_code == 200
    assert client.post("/api/profile/confirm").status_code == 200
    return client


def test_requires_confirmed_profile(anon, fake):
    login(anon, "g1")
    assert anon.get("/api/gaps").json()["status"] == "none"
    assert anon.post("/api/gaps/analyze", json={}).status_code == 409
    assert anon.post("/api/gaps/confirm").status_code == 409


def test_analyze_confirm_and_reload(anon, fake):
    client = confirmed_user(anon, "g2")
    fake(analysis())
    corrections = [{"kind": "note", "text": "I've never used Python"}]
    state = client.post("/api/gaps/analyze", json={"corrections": corrections}).json()
    assert state["status"] == "ready" and not state["confirmed"] and not state["stale"]
    assert state["corrections"][0]["text"] == "I've never used Python"
    assert client.post("/api/gaps/confirm").json()["confirmed"] is True

    client.post("/api/auth/logout")
    login(client, "g2")
    state = client.get("/api/gaps").json()
    assert state["confirmed"] is True and state["analysis"]["gaps"][0]["skill"] == "Machine learning basics"


def test_profile_edit_makes_analysis_stale(anon, fake):
    client = confirmed_user(anon, "g3")
    fake(analysis())
    client.post("/api/gaps/analyze", json={})
    client.post("/api/gaps/confirm")
    client.put("/api/profile", json={"hours_per_week": 12})
    state = client.get("/api/gaps").json()
    assert state["stale"] is True and state["confirmed"] is False
    assert client.post("/api/gaps/confirm").status_code == 409


def test_llm_failure_gives_friendly_error(anon, monkeypatch):
    client = confirmed_user(anon, "g4")
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    r = client.post("/api/gaps/analyze", json={})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_invalid_output_gives_502(anon, fake):
    client = confirmed_user(anon, "g5")
    fake(*[{"strengths": []}] * agent.MAX_ATTEMPTS)
    assert client.post("/api/gaps/analyze", json={}).status_code == 502
    assert client.get("/api/gaps").json()["status"] == "none"


def test_users_only_see_their_own_analysis(anon, fake):
    confirmed_user(anon, "g6")
    fake(analysis())
    anon.post("/api/gaps/analyze", json={})
    with TestClient(app, base_url="https://testserver") as other:
        login(other, "g7")
        assert other.get("/api/gaps").json()["status"] == "none"
