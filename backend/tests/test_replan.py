"""Refresh my plan (milestone 11): placement.replan keeps the done work and replans the remaining weeks;
POST /api/roadmap/refresh streams it like a generate."""
from datetime import date, timedelta

from sqlalchemy import select

from core import db as dbmod
from core.agents.scheduler.budget import check_budget, phase_weeks
from core.agents.scheduler.placement import place, replan
from core.agents.scheduler.tracking import tasks
from core.models import AgentOutput
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, events, fake, generate  # noqa: F401  (fixture)
from tests.test_roadmap_tracking import START, today  # noqa: F401  (fixture)
from tests.test_scheduler_budget import approved, learn_hours, scheduler_input

PCI = "PCI-DSS for ML"


def data_and_plan():
    data = scheduler_input(resources=[approved("ml", hours=20), approved("pci", hours=10, gap=PCI, priority="medium")])
    return data, place(data)


def by_id(roadmap):
    return {tid: (week, t) for tid, t, week in tasks(roadmap)}


def test_done_tasks_stay_and_the_rest_moves_to_the_remaining_weeks():
    data, roadmap = data_and_plan()
    week1 = [tid for tid, _, w in tasks(roadmap) if w == 1]
    new = replan(data, roadmap, set(week1), from_week=4)

    old, now = by_id(roadmap), by_id(new)
    for tid in week1:  # same id, week, kind, hours and resource
        assert now[tid][0] == 1 and now[tid][1] == old[tid][1]
    assert not [tid for tid, (w, _) in now.items() if 1 < w < 4]  # closed weeks get nothing new
    assert learn_hours(new) == {"ml": 20, "pci": 10}  # exactly each resource's hours, done + remaining
    assert all(p.narrative == "pending" for p in new.phases)
    assert check_budget(new, data, 4) == []


def test_completed_resources_and_gaps_are_dropped():
    data, roadmap = data_and_plan()
    new = replan(data, roadmap, set(), from_week=1, completed_resources={"pci"})
    assert set(learn_hours(new)) == {"ml"} and check_budget(new, data) == []
    new = replan(data, roadmap, set(), from_week=1, completed_gaps={PCI})
    assert set(learn_hours(new)) == {"ml"}


def test_phases_that_are_over_keep_their_text_and_get_a_catch_up_project():
    data, roadmap = data_and_plan()
    for phase in roadmap.phases:
        phase.name, phase.narrative = f"AI phase {phase.number}", "ai"
    roadmap.months[0].theme = "Kept theme"
    from_week = phase_weeks(3)[0]  # phases 1 and 2 are over, nothing was done
    new = replan(data, roadmap, set(), from_week=from_week)

    assert [(p.name, p.narrative) for p in new.phases[:2]] == [("AI phase 1", "ai"), ("AI phase 2", "ai")]
    assert new.phases[2].narrative == "pending" and new.months[0].theme == "Kept theme"
    assert all(w >= from_week for _, _, w in tasks(new))
    titles = [t.title for _, t, _ in tasks(new) if t.kind == "project"]
    assert any(t.startswith("Phase 1 portfolio project") for t in titles)
    assert any(t.startswith("Phase 2 portfolio project") for t in titles)
    assert check_budget(new, data, from_week) == []
    assert check_budget(new, data) != []  # without from_week, phases 1 and 2 would need project work


def test_new_tasks_are_numbered_after_the_kept_ones():
    data, roadmap = data_and_plan()
    week1 = sorted(tid for tid, _, w in tasks(roadmap) if w == 1)
    new = replan(data, roadmap, {week1[0]}, from_week=1)
    ids = [tid for tid, _, w in tasks(new) if w == 1]
    assert ids[0] == week1[0] and len(ids) == len(set(ids))


# --- endpoint ---------------------------------------------------------------------


def refresh(client):
    r = client.post("/api/roadmap/refresh")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    found = events(r)
    return found, [e["state"] for e in found if "state" in e][-1]


def test_refresh_needs_a_current_roadmap(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rp1", fake_gaps)
    assert anon.post("/api/roadmap/refresh").status_code == 409


def test_refresh_keeps_checks_and_moves_overdue_work(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rp2", fake_gaps)
    state = generate(anon)[1]
    first = state["tracking"]["next_steps"][0]["task_id"]
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})

    today(START + timedelta(weeks=3))  # week 4: weeks 1-3 are overdue
    review = anon.get("/api/progress").json()["review"]
    assert review["behind_hours"] > 0 and review["from_week"] == 4 and review["can_refresh"]

    fake()  # text for the three phases again
    found, state = refresh(anon)
    assert found[0]["from_week"] == 4 and found[-1]["type"] == "done"
    roadmap, tracking = state["roadmap"], state["tracking"]
    assert tracking["items"][first]["done"] and not state["stale"]
    assert state["start_date"] == START.isoformat()
    early = [t for m in roadmap["months"] for w in m["weeks"] if w["number"] < 4 for t in w["tasks"]]
    assert [t["id"] for t in early] == [first]  # only the done task is left in the past weeks
    assert [p["narrative"] for p in roadmap["phases"]] == ["ai"] * 3
    assert anon.get("/api/progress").json()["review"]["behind_hours"] == 0
    with dbmod.SessionLocal() as db:
        logged = db.scalars(select(AgentOutput).where(AgentOutput.user_id == "rp2", AgentOutput.agent == "scheduler")).all()
        assert [o.output.get("mode") for o in logged] == [None, "refresh"]


def test_refresh_drops_a_completed_skill(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rp3", fake_gaps)
    generate(anon)
    skills = [s["skill"] for s in anon.get("/api/progress").json()["review"]["skills"]]
    anon.put("/api/progress", json={"skills": [{"skill": skills[1], "completed": True}]})
    listed = {g["gap"]["skill"]: {r["resource"]["id"] for r in g["resources"]}
              for g in anon.get("/api/resources").json()["resources"]["gaps"]}
    fake()
    roadmap = refresh(anon)[1]["roadmap"]
    planned = {t["resource"]["id"] for m in roadmap["months"] for w in m["weeks"] for t in w["tasks"] if t["resource"]}
    assert planned and listed[skills[1]] and not planned & listed[skills[1]]
    assert date.fromisoformat(anon.get("/api/roadmap").json()["start_date"]) == START
