"""Progress Review and Dashboard endpoints (milestone 11): saved marks and notes, readiness history, the
dashboard's numbers, and per-user isolation."""
from datetime import timedelta

from core import db as dbmod
from core.models import ReadinessHistory
from tests.conftest import login
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, fake, generate  # noqa: F401  (fixture)
from tests.test_roadmap_tracking import START, today  # noqa: F401  (fixture)


def history(sub):
    with dbmod.SessionLocal() as db:
        return [(h.day, h.score) for h in db.query(ReadinessHistory).filter_by(user_id=sub).order_by(ReadinessHistory.day)]


def test_nothing_before_a_gap_analysis(anon, today):  # noqa: F811
    confirmed_user(anon, "pr1")
    assert anon.get("/api/progress").json() == {"status": "none", "review": None}
    assert anon.get("/api/dashboard").json() == {"status": "none", "dashboard": None}
    assert anon.put("/api/progress", json={"skills": [], "notes": ""}).status_code == 409
    assert anon.post("/api/dashboard/readiness").status_code == 200 and history("pr1") == []


def test_review_round_trip_and_validation(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "pr2", fake_gaps)
    generate(anon)
    review = anon.get("/api/progress").json()["review"]
    skills = [s["skill"] for s in review["skills"]]
    assert skills == ["Deep learning", "PCI-DSS"] and review["notes"] == ""
    assert review["courses"] and all(c["status"] == "not_started" and c["hours_done"] == 0 for c in review["courses"])
    assert review["from_week"] == 1 and review["can_refresh"] and review["behind_hours"] == 0
    before = review["readiness"]

    body = {"skills": [{"skill": "deep  LEARNING", "confidence": 4}, {"skill": "PCI-DSS", "completed": True}],
            "notes": "  Busy month at work.  "}
    review = anon.put("/api/progress", json=body).json()["review"]
    dl, pci = review["skills"]
    assert dl["confidence"] == 4 and not dl["completed"] and pci["completed"] and pci["credit"] == 1
    assert review["notes"] == "Busy month at work." and review["readiness"] > before

    assert anon.put("/api/progress", json={"skills": [{"skill": "Cooking"}]}).status_code == 422
    assert anon.put("/api/progress", json={"skills": [{"skill": "PCI-DSS", "confidence": 6}]}).status_code == 422
    assert anon.put("/api/progress", json={"notes": "x" * 2001}).status_code == 422
    # Skills left out keep their marks.
    assert anon.put("/api/progress", json={"notes": ""}).json()["review"]["skills"][1]["completed"]


def test_readiness_history_one_point_per_day(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "pr3", fake_gaps)
    first = generate(anon)[1]["tracking"]["next_steps"][0]["task_id"]
    anon.post("/api/dashboard/readiness")
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})  # a check records too
    assert [d for d, _ in history("pr3")] == [START]

    today(START + timedelta(days=8))
    anon.put("/api/progress", json={"skills": [{"skill": "PCI-DSS", "completed": True}]})
    points = history("pr3")
    assert [d for d, _ in points] == [START, START + timedelta(days=8)] and points[1][1] > points[0][1]
    dashboard = anon.get("/api/dashboard").json()["dashboard"]
    assert dashboard["readiness_change"] == points[1][1] - points[0][1]
    assert [p["week"] for p in dashboard["history"]] == [0, round(8 / 7, 2)]


def test_dashboard_numbers(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "pr4", fake_gaps)
    state = generate(anon)[1]
    first = state["tracking"]["next_steps"][0]
    anon.put("/api/roadmap/items", json={"item_id": first["task_id"], "done": True})
    d = anon.get("/api/dashboard").json()["dashboard"]

    assert d["done_hours"] == first["hours"] and d["planned_hours"] == state["tracking"]["planned_hours"]
    assert d["completion"] == round(100 * d["done_hours"] / d["planned_hours"])
    assert d["jobs_applied"] is None and (d["covered"], d["needed"]) == (2, 4)
    assert [p["skill"] for p in d["radar"]] == ["Deep learning", "PCI-DSS"]
    assert all(p["target"] == 3 and 1 <= p["today"] < 3 for p in d["radar"])
    assert len(d["planned"]) == 27 and d["planned"][0] <= d["readiness"] <= d["planned"][-1]
    assert [p["number"] for p in d["phases"]] == [1, 2, 3] and d["phases"][0]["done_hours"] == first["hours"]
    assert d["next_milestone"] == state["roadmap"]["months"][0]["milestone"]
    assert len(d["next_steps"]) == 2 and first["task_id"] not in [s["task_id"] for s in d["next_steps"]]
    s = d["summary"]
    assert s["plan_status"] == "on_track" and s["weeks_left"] == 26 and s["current_week"] == 1
    assert s["start_date"] == START.isoformat() and s["end_date"] == (START + timedelta(days=181)).isoformat()

    today(START + timedelta(weeks=2))
    assert anon.get("/api/dashboard").json()["dashboard"]["summary"]["plan_status"] == "behind"
    today(START - timedelta(days=1))
    assert anon.get("/api/dashboard").json()["dashboard"]["summary"]["plan_status"] == "not_started"


def test_progress_is_per_user(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "pr5", fake_gaps)
    generate(anon)
    anon.put("/api/progress", json={"skills": [{"skill": "PCI-DSS", "completed": True}], "notes": "mine"})
    anon.post("/api/auth/logout")

    approved_user(anon, "pr6", fake_gaps)
    generate(anon)
    review = anon.get("/api/progress").json()["review"]
    assert review["notes"] == "" and not any(s["completed"] for s in review["skills"])
    anon.post("/api/auth/logout")

    login(anon, "pr5")
    assert anon.get("/api/progress").json()["review"]["notes"] == "mine"
