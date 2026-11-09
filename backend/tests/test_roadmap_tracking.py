"""Roadmap tracking (milestone 10): due dates, priority, status, next steps, checks that survive a regenerate,
the start date and the PDF export."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core import db as dbmod
from core import repository
from core.agents.course_search.schemas import ApprovedList
from core.agents.scheduler.placement import place
from core.agents.scheduler.tracking import due_date, fingerprints, milestone_id, tasks, track, week_of
from core.models import RoadmapItemProgress
from tests.conftest import login
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, fake, generate  # noqa: F401  (fixture)
from tests.test_scheduler_budget import approved, scheduler_input

START = date(2026, 11, 2)


def plan(*resources):
    data = scheduler_input(resources=list(resources) or [approved("a", hours=20, priority="high")])
    return place(data), ApprovedList(resources=data.resources)


def ids(roadmap, week):
    return [tid for tid, _, w in tasks(roadmap) if w == week]


# --- pure tracking ------------------------------------------------------------------


def test_due_dates_and_weeks():
    assert due_date(START, 1) == date(2026, 11, 8) and due_date(START, 26) == START + timedelta(days=181)
    assert week_of(START, START) == 1 and week_of(START, date(2026, 11, 9)) == 2 and week_of(START, START - timedelta(1)) == 0


def test_first_day_statuses_and_next_steps():
    roadmap, approved_list = plan()
    t = track(roadmap, approved_list, START, set(), START)
    assert t.current_week == 1 and t.start_date == START and t.today == START
    assert {t.items[i].status for i in ids(roadmap, 1)} == {"this_week"}
    assert {t.items[i].status for i in ids(roadmap, 2)} == {"not_started"}
    assert t.items[milestone_id(1)].due == due_date(START, 4) and t.items[milestone_id(1)].status == "not_started"
    assert [w.status for w in t.weeks[:2]] == ["in_progress", "not_started"]
    assert t.phases[0].status == "in_progress" and t.phases[1].status == "not_started"
    first = [tid for tid, _, _ in tasks(roadmap)][:3]
    assert [s.task_id for s in t.next_steps] == first and not any(s.overdue for s in t.next_steps)
    assert t.done_tasks == 0 and t.total_tasks == len(list(tasks(roadmap)))
    assert t.planned_hours == roadmap.total_hours


def test_priority_comes_from_the_approved_list():
    roadmap, approved_list = plan(approved("a", hours=10, priority="low"), approved("b", hours=10, gap="Other", priority="high"))
    t = track(roadmap, approved_list, START, set(), START)
    by_resource = {task.resource.id: t.items[tid].priority for tid, task, _ in tasks(roadmap) if task.resource}
    assert by_resource == {"a": "low", "b": "high"}
    for tid, task, _ in tasks(roadmap):
        if task.kind == "project":  # the phase's highest gap priority
            phase = next(p for p in roadmap.phases if any(tid in ids(roadmap, w.number) for m in roadmap.months
                                                          if m.number in p.months for w in m.weeks))
            assert t.items[tid].priority == next(x.priority for x in t.phases if x.number == phase.number)


def test_overdue_work_comes_first_in_next_steps():
    roadmap, approved_list = plan()
    week1 = ids(roadmap, 1)
    today = START + timedelta(days=15)  # week 3
    t = track(roadmap, approved_list, START, {week1[0]}, today)
    assert t.current_week == 3
    assert t.items[week1[0]].status == "done" and t.items[week1[0]].done
    overdue = [i for w in (1, 2) for i in ids(roadmap, w) if i != week1[0]]
    assert overdue and {t.items[i].status for i in overdue} == {"overdue"}
    assert {t.items[i].status for i in ids(roadmap, 3)} == {"this_week"}
    assert t.weeks[1].status == "overdue" and t.weeks[2].status == "in_progress"
    assert [s.task_id for s in t.next_steps] == (overdue + ids(roadmap, 3))[:3]
    assert all(s.overdue for s in t.next_steps if s.task_id in overdue)
    assert t.done_tasks == 1 and t.done_hours == next(task.hours for tid, task, _ in tasks(roadmap) if tid == week1[0])


def test_done_week_and_before_the_start():
    roadmap, approved_list = plan()
    t = track(roadmap, approved_list, START, set(ids(roadmap, 1)), START)
    assert t.weeks[0].status == "done"
    early = track(roadmap, approved_list, START, set(), START - timedelta(days=3))
    assert early.current_week is None and early.weeks[0].status == "not_started"
    assert not any(i.status in ("overdue", "this_week") for i in early.items.values())
    late = track(roadmap, approved_list, START, set(), START + timedelta(days=400))
    assert late.current_week is None and all(i.status == "overdue" for i in late.items.values())


def test_fingerprints_follow_the_task():
    roadmap, _ = plan(approved("a", hours=10))
    other, _ = plan(approved("z", hours=10))
    same = fingerprints(roadmap)
    assert same == fingerprints(plan(approved("a", hours=10))[0])
    assert set(same) == set(fingerprints(other))  # same ids...
    learn = next(tid for tid, task, _ in tasks(roadmap) if task.kind == "learn")
    assert same[learn] != fingerprints(other)[learn]  # ...but a different resource
    assert all(milestone_id(m) in same for m in range(1, 7))


# --- endpoints ----------------------------------------------------------------------


@pytest.fixture()
def today(monkeypatch):
    def set_today(d):
        monkeypatch.setattr(repository, "today", lambda: d)

    set_today(START)
    return set_today


def test_new_roadmap_starts_today_and_checks_are_saved(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rt1", fake_gaps)
    state = generate(anon)[1]
    assert state["start_date"] == START.isoformat() and state["tracking"]["current_week"] == 1
    first = state["tracking"]["next_steps"][0]["task_id"]

    r = anon.put("/api/roadmap/items", json={"item_id": first, "done": True})
    assert r.status_code == 200
    tracking = r.json()["tracking"]
    assert tracking["items"][first]["done"] and tracking["done_tasks"] == 1
    assert first not in [s["task_id"] for s in tracking["next_steps"]]
    assert anon.put("/api/roadmap/items", json={"item_id": "m1", "done": True}).json()["tracking"]["items"]["m1"]["done"]

    anon.post("/api/auth/logout")
    login(anon, "rt1")
    assert anon.get("/api/roadmap").json()["tracking"]["items"][first]["done"]

    r = anon.put("/api/roadmap/items", json={"item_id": first, "done": False})
    assert not r.json()["tracking"]["items"][first]["done"]
    with dbmod.SessionLocal() as db:
        assert {x.item_id for x in db.query(RoadmapItemProgress).filter_by(user_id="rt1")} == {"m1"}


def test_unknown_item_and_missing_roadmap(anon, fake_gaps, fake, today):  # noqa: F811
    confirmed_user(anon, "rt2")
    assert anon.put("/api/roadmap/items", json={"item_id": "w1-1", "done": True}).status_code == 404
    assert anon.put("/api/roadmap/start-date", json={"start_date": "2026-11-02"}).status_code == 404
    assert anon.get("/api/roadmap/export.pdf").status_code == 404

    approved_user(anon, "rt3", fake_gaps)
    generate(anon)
    assert anon.put("/api/roadmap/items", json={"item_id": "w99-1", "done": True}).status_code == 422
    assert anon.put("/api/roadmap/items", json={"item_id": "", "done": True}).status_code == 422
    assert anon.put("/api/roadmap/start-date", json={"start_date": "soon"}).status_code == 422


def test_start_date_moves_the_due_dates_and_survives_a_regenerate(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rt4", fake_gaps)
    first = generate(anon)[1]["tracking"]["next_steps"][0]["task_id"]
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})

    state = anon.put("/api/roadmap/start-date", json={"start_date": "2026-12-07"}).json()
    assert state["start_date"] == "2026-12-07" and state["tracking"]["weeks"][0]["due"] == "2026-12-13"
    assert state["tracking"]["current_week"] is None  # it hasn't started yet

    today(date(2026, 12, 1))  # a later day: a regenerate keeps the user's start date and unchanged checks
    state = generate(anon)[1]
    assert state["start_date"] == "2026-12-07" and state["tracking"]["items"][first]["done"]


def test_a_check_does_not_carry_over_to_a_different_task(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rt5", fake_gaps)
    first = generate(anon)[1]["tracking"]["next_steps"][0]["task_id"]
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})
    with dbmod.SessionLocal() as db:  # as if a regenerate had put another task under the same id
        db.get(RoadmapItemProgress, ("rt5", first)).fingerprint = "learn|something-else|1"
        db.commit()
    assert not anon.get("/api/roadmap").json()["tracking"]["items"][first]["done"]


def test_checks_are_per_user(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rt6", fake_gaps)
    first = generate(anon)[1]["tracking"]["next_steps"][0]["task_id"]
    anon.put("/api/roadmap/items", json={"item_id": first, "done": True})
    with TestClient(app, base_url="https://testserver") as other:
        approved_user(other, "rt7", fake_gaps)
        state = generate(other)[1]
        assert state["tracking"]["done_tasks"] == 0
        other.put("/api/roadmap/items", json={"item_id": first, "done": True})
        other.put("/api/roadmap/start-date", json={"start_date": "2027-01-04"})
    state = anon.get("/api/roadmap").json()
    assert state["tracking"]["done_tasks"] == 1 and state["start_date"] == START.isoformat()


def test_pdf_and_markdown_exports_carry_the_tracking(anon, fake_gaps, fake, today):  # noqa: F811
    approved_user(anon, "rt8", fake_gaps)
    state = generate(anon)[1]
    first = state["tracking"]["next_steps"][0]
    anon.put("/api/roadmap/items", json={"item_id": "m1", "done": True})
    r = anon.get("/api/roadmap/export.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and "attachment" in r.headers["content-disposition"]
    md = anon.get("/api/roadmap/export.md").text
    assert "started 2 Nov 2026" in md and "## Immediate next steps" in md
    assert f"1. {first['title']} ({first['hours']} h, week 1, due 8 Nov 2026)" in md
    assert "- [x] **Milestone (due 29 Nov 2026):**" in md
