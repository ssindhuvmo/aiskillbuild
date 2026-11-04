"""The scheduler: placement in plain Python, check_budget as its safety net, and the per-phase narrative with a
fake LLM (no network)."""
import itertools
import logging
from types import SimpleNamespace

import pytest

from core.agents.course_search.schemas import ApprovedResource
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.scheduler import narrative
from core.agents.scheduler.budget import (
    WEEKS, budget, check_budget, month_weeks, phase_weeks, practice_hours, project_reserve,
)
from core.agents.scheduler.placement import place
from core.agents.scheduler.schemas import PhaseNarrative, SchedulerInput
from core.knowledge.schemas import Resource
from tests.test_gap_analysis import INPUT, analysis


def approved(rid="ml-course", hours=40, gap="Machine learning basics", priority="high", level="beginner"):
    resource = Resource(
        id=rid, title=f"Course {rid}", provider="Example U", url=f"https://example.com/{rid}", format="course",
        level=level, cost="free", hours=hours, skills=["machine-learning"], description="A course.",
    )
    return ApprovedResource(resource=resource, gaps=[gap], priority=priority)


def scheduler_input(hours_per_week=8, resources=None):
    a = GapAnalysis.model_validate(analysis())
    return SchedulerInput(
        **{**INPUT, "hours_per_week": hours_per_week}, gaps=a.gaps, domain_use_cases=a.domain_use_cases,
        resources=resources or [approved()],
    )


def tasks(roadmap, kind=None):
    return [(w.number, t) for m in roadmap.months for w in m.weeks for t in w.tasks if kind in (None, t.kind)]


def learn_hours(roadmap):
    hours = {}
    for _, t in tasks(roadmap, "learn"):
        hours[t.resource.id] = hours.get(t.resource.id, 0) + t.hours
    return hours


# --- calendar and placement ---------------------------------------------------------


def test_calendar():
    assert WEEKS == 26 and budget(8) == 208 and budget(1) == 26
    assert [month_weeks(m)[0] for m in range(1, 7)] == [1, 5, 9, 14, 18, 22] and month_weeks(6)[-1] == 26
    assert [phase_weeks(p)[0] for p in (1, 2, 3)] == [1, 9, 18] and len(phase_weeks(3)) == 9


def test_short_resource_is_never_given_more_learn_hours_than_it_takes():
    # From the log: "dlai-advanced-rag takes 2 hours but has 4 hours of learn tasks".
    data = scheduler_input(resources=[approved("dlai-advanced-rag", hours=2)])
    roadmap = place(data)
    assert learn_hours(roadmap) == {"dlai-advanced-rag": 2}
    practice = [t for _, t in tasks(roadmap, "practice")]
    assert [(t.hours, t.resource.id) for t in practice] == [(1, "dlai-advanced-rag")]
    assert check_budget(roadmap, data) == []


def test_always_three_phases_of_two_months():
    # From the log: the model returned 4 phases. Phases now come from the calendar, not from a reply.
    roadmap = place(scheduler_input())
    assert [(p.number, p.months) for p in roadmap.phases] == [(1, [1, 2]), (2, [3, 4]), (3, [5, 6])]
    assert [len(m.weeks) for m in roadmap.months] == [4, 4, 5, 4, 4, 5]
    assert all(p.narrative == "pending" for p in roadmap.phases)


def test_long_resource_is_split_over_weeks_then_practised():
    data = scheduler_input(resources=[approved(hours=20)])
    roadmap = place(data)
    learn = [(w, t.hours, t.title) for w, t in tasks(roadmap, "learn")]
    assert learn == [(1, 8, "Course ml-course (part 1 of 3)"), (2, 8, "Course ml-course (part 2 of 3)"),
                     (3, 4, "Course ml-course (part 3 of 3)")]
    practice = [(w, t.hours) for w, t in tasks(roadmap, "practice")]
    assert practice == [(3, 4), (4, 3)] and sum(h for _, h in practice) == practice_hours(20) == 7
    assert all(t.resource.url == "https://example.com/ml-course" for _, t in tasks(roadmap, "practice"))
    assert check_budget(roadmap, data) == []


def test_order_is_gap_priority_then_level():
    data = scheduler_input(resources=[
        approved("low-gap", 4, gap="PCI-DSS for ML", priority="low"),
        approved("ml-advanced", 4, level="advanced"),
        approved("ml-intro", 4, level="beginner"),
    ])
    order = list(dict.fromkeys(t.resource.id for _, t in tasks(place(data), "learn")))
    assert order == ["ml-intro", "ml-advanced", "low-gap"]


def test_no_padding_and_a_proportionate_project_in_every_phase():
    data = scheduler_input(resources=[approved(hours=6)])  # 6 learn + 2 practice, all in phase 1
    roadmap = place(data)
    projects = {p: sum(t.hours for w, t in tasks(roadmap, "project") if w in phase_weeks(p)) for p in (1, 2, 3)}
    assert projects == {1: 4, 2: 4, 3: 4}  # PROJECT_MIN_HOURS each, not the whole reserve
    assert roadmap.total_hours == 6 + 2 + 12 < roadmap.budget_hours
    assert sum(not w.tasks for m in roadmap.months for w in m.weeks) > 15  # free weeks stay free
    assert roadmap.phases[0].gaps == ["Machine learning basics"] and roadmap.phases[1].gaps == []


def test_project_time_is_reserved_at_the_end_of_each_phase():
    data = scheduler_input(resources=[approved(f"c{i}", 3) for i in range(60)])  # fills every study block
    roadmap = place(data)
    for p in (1, 2, 3):
        weeks = phase_weeks(p)
        project = [w for w, t in tasks(roadmap, "project") if w in weeks]
        study = [w for w, t in tasks(roadmap) if w in weeks and t.kind != "project"]
        assert sum(t.hours for w, t in tasks(roadmap, "project") if w in weeks) == project_reserve(8, p)
        assert max(study) <= min(project) and max(project) == weeks[-1]
    assert [r.id for r in roadmap.unscheduled] and check_budget(roadmap, data) == []


def test_resources_that_do_not_fit_are_unscheduled_but_smaller_ones_still_fit():
    data = scheduler_input(hours_per_week=2, resources=[approved("huge", 300), approved("small", 3)])
    roadmap = place(data)
    assert [r.id for r in roadmap.unscheduled] == ["huge"] and learn_hours(roadmap) == {"small": 3}
    assert check_budget(roadmap, data) == []


@pytest.mark.parametrize("hours_per_week,sizes", [
    (1, (1, 5, 13)), (3, (40, 2, 9, 70)), (5, (120, 8)), (8, (2, 2, 2, 90, 15, 33, 4)), (12, (60,) * 6),
    (20, (300, 1, 45)), (40, (100, 100, 100, 100, 100)),
])
def test_budget_rules_hold_by_construction(hours_per_week, sizes):
    priorities = itertools.cycle(["high", "medium", "low"])
    data = scheduler_input(hours_per_week, [approved(f"r{i}", h, priority=next(priorities)) for i, h in enumerate(sizes)])
    roadmap = place(data)
    assert check_budget(roadmap, data) == []
    for rid, hours in learn_hours(roadmap).items():  # every placed resource gets exactly its own hours
        assert hours == next(r.resource.hours for r in data.resources if r.resource.id == rid)
    placed = set(learn_hours(roadmap)) | {r.id for r in roadmap.unscheduled}
    assert placed == {r.resource.id for r in data.resources}
    assert all(t.id for _, t in tasks(roadmap)) and len({t.id for _, t in tasks(roadmap)}) == len(tasks(roadmap))


# --- check_budget (the safety assertion) ---------------------------------------------


def test_check_budget_catches_a_broken_plan():
    data = scheduler_input()
    roadmap = place(data)
    week = roadmap.months[0].weeks[0]
    week.tasks[0].hours += 5  # over the weekly limit, over the resource's length, and the totals disagree
    week.hours += 5
    roadmap.total_hours += 5
    found = check_budget(roadmap, data)
    assert "ml-course takes 40 hours but has 45 hours of learn tasks." in found
    assert "Week 1 plans 13 hours; the limit is 8 hours per week." in found

    roadmap = place(data)
    roadmap.months[0].weeks[0].tasks[0].resource = roadmap.months[0].weeks[0].tasks[0].resource.model_copy(
        update={"url": "https://evil.example.com/"})
    assert check_budget(roadmap, data) == ['Week 1 uses "ml-course", which is not in the approved list.']

    roadmap = place(data)
    roadmap.phases.append(roadmap.phases[0].model_copy())
    assert check_budget(roadmap, data) == ["The roadmap must have exactly 3 phases of 2 months."]


# --- narrative ----------------------------------------------------------------------


def reply(roadmap, phase=1, **change):
    ids = narrative.practice_ids(roadmap, roadmap.phases[phase - 1])
    data = {
        "name": f"Phase {phase} focus",
        "first_month": {"theme": "Foundations", "milestone": "Train a first model."},
        "second_month": {"theme": "Applied ML", "milestone": "Ship the fraud demo."},
        "practice": [{"id": i, "title": f"Exercise {i}"} for i in ids],
        "project": {"title": f"Fraud model {phase}", "problem": "Flag fraudulent card payments.",
                    "dataset": "Credit Card Fraud Detection (Kaggle)", "deliverables": ["Notebook", "Write-up"]},
    }
    return {**data, **change}


class FakeClient:
    """messages.parse validates each scripted reply like the SDK does. A reply may be a dict, an exception
    to raise, or a function of the request text (for parallel calls, whose order is not fixed)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kw):
        text = kw["messages"][0]["content"]
        self.requests.append(text)
        reply = self.replies.pop(0) if self.replies else None
        reply = reply(text) if callable(reply) else reply
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(parsed_output=PhaseNarrative.model_validate(reply))


@pytest.fixture()
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(narrative, "get_client", lambda: client)
        return client

    return install


def test_narrative_changes_only_text(fake):
    data = scheduler_input(resources=[approved(hours=20)])
    roadmap = place(data)
    before = [(w, t.kind, t.hours, t.resource) for w, t in tasks(roadmap)]
    client = fake(reply(roadmap))
    narrative.apply(roadmap, 1, narrative.write(data, roadmap, roadmap.phases[0]))
    assert [(w, t.kind, t.hours, t.resource) for w, t in tasks(roadmap)] == before
    phase = roadmap.phases[0]
    assert (phase.name, phase.narrative, phase.project.title) == ("Phase 1 focus", "ai", "Fraud model 1")
    assert (roadmap.months[0].theme, roadmap.months[1].milestone) == ("Foundations", "Ship the fraud demo.")
    assert [t.title for _, t in tasks(roadmap, "practice")] == ["Exercise w3-2", "Exercise w4-1"]
    titles = [t.title for w, t in tasks(roadmap, "project") if w in phase_weeks(1)]
    assert titles == ["Portfolio project: Fraud model 1 (part 1 of 2)", "Portfolio project: Fraud model 1 (part 2 of 2)"]
    assert check_budget(roadmap, data) == []
    assert '"id": "w3-2"' in client.requests[0] and "Phase 1 of 3 (months 1-2)" in client.requests[0]
    assert "https://" not in client.requests[0]  # the model never sees links


def test_unknown_practice_id_or_a_link_is_retried_once_with_feedback(fake):
    data = scheduler_input()
    roadmap = place(data)
    bad_id = reply(roadmap, practice=[{"id": "w99-1", "title": "Something"}])
    client = fake(bad_id, reply(roadmap))
    narrative.write(data, roadmap, roadmap.phases[0])
    assert "w99-1" in client.requests[1] and "rejected" in client.requests[1]

    link = reply(roadmap)
    link["project"]["dataset"] = "https://kaggle.com/mlg-ulb/creditcardfraud"
    fake(link, link)
    with pytest.raises(narrative.NarrativeFailed, match="URLs"):
        narrative.write(data, roadmap, roadmap.phases[0])


def test_invalid_reply_gives_up_after_one_retry(fake):
    data = scheduler_input()
    roadmap = place(data)
    client = fake(*[{**reply(roadmap), "name": ""}] * 3)
    with pytest.raises(narrative.NarrativeFailed):
        narrative.write(data, roadmap, roadmap.phases[0])
    assert len(client.requests) == narrative.MAX_ATTEMPTS == 2


def test_default_text_is_a_complete_roadmap():
    data = scheduler_input(resources=[approved(hours=20)])
    roadmap = place(data)
    for n in (1, 2, 3):
        narrative.use_default(roadmap, n)
    assert [p.narrative for p in roadmap.phases] == ["default"] * 3
    assert roadmap.phases[0].name == "Machine learning basics" and roadmap.phases[1].name == "Portfolio project"
    assert roadmap.phases[0].project.dataset and roadmap.months[0].milestone.startswith("Complete Course ml-course")
    assert roadmap.months[2].weeks[0].focus == "Portfolio project"  # phase 2 has no study: just its project
    assert roadmap.months[2].weeks[1].focus == "Free week: catch up or rest"


def test_log_levels(fake, caplog):
    data = scheduler_input()
    roadmap = place(data)
    fake({**reply(roadmap), "name": ""}, reply(roadmap))
    with caplog.at_level(logging.WARNING, logger=narrative.__name__):
        narrative.write(data, roadmap, roadmap.phases[0])
    assert "phase 1, attempt 1 of 2 rejected" in caplog.text
