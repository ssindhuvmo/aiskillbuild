"""The scheduler's hour budget: check_budget rules and the agent's retry loop, with a fake LLM (no network)."""
import json
import logging
from types import SimpleNamespace

import pytest

from core.agents.course_search.schemas import ApprovedResource
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.scheduler import agent
from core.agents.scheduler.budget import MONTH_WEEKS, WEEKS, budget, check_budget, finalize, month_weeks
from core.agents.scheduler.schemas import RoadmapDraft, SchedulerInput
from core.knowledge.schemas import Resource
from tests.test_gap_analysis import PROFILE, analysis

TRUNCATED = object()  # scripted reply: the model ran out of output tokens


def approved(rid="ml-course", hours=40):
    resource = Resource(
        id=rid, title=f"Course {rid}", provider="Example U", url=f"https://example.com/{rid}", format="course",
        level="beginner", cost="free", hours=hours, skills=["machine-learning"], description="A course.",
    )
    return ApprovedResource(resource=resource, gaps=["Machine learning basics"], priority="high")


def scheduler_input(hours_per_week=8, resources=None):
    a = GapAnalysis.model_validate(analysis())
    return SchedulerInput(
        **{**PROFILE, "hours_per_week": hours_per_week}, gaps=a.gaps, domain_use_cases=a.domain_use_cases,
        resources=resources or [approved()],
    )


def draft(per_week=8, resource_id="ml-course"):
    """A valid plan using exactly `per_week` hours every week: one hour of the resource in week 1,
    project work in the last week of each phase, practice everywhere else."""
    months = []
    for m in range(1, len(MONTH_WEEKS) + 1):
        weeks = [
            {"number": n, "focus": f"Focus {n}", "tasks": [{"title": f"Practice {n}", "kind": "practice", "hours": per_week}]}
            for n in month_weeks(m)
        ]
        if m % 2 == 0:
            weeks[-1]["tasks"][0].update(title="Build the project", kind="project")
        months.append({"number": m, "theme": f"Theme {m}", "summary": "What this month covers.", "milestone": f"Milestone {m}", "weeks": weeks})
    months[0]["weeks"][0]["tasks"] = [
        {"title": "Start the course", "kind": "learn", "hours": 1, "resource_id": resource_id},
        {"title": "Practice 1", "kind": "practice", "hours": per_week - 1},
    ]
    phases = [
        {"number": p, "name": f"Phase {p}", "project": {
            "title": f"Fraud model {p}", "problem": "Flag fraudulent card payments.",
            "dataset": "Credit Card Fraud Detection (Kaggle)", "deliverables": ["Notebook", "Write-up"],
        }}
        for p in (1, 2, 3)
    ]
    return {"months": months, "phases": phases}


def week(d, number):
    return next(w for m in d["months"] for w in m["weeks"] if w["number"] == number)


def problems(d, data=None):
    return check_budget(RoadmapDraft.model_validate(d), data or scheduler_input())


class FakeClient:
    """messages.create returns each scripted reply as JSON text and records the prompts it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.max_tokens = None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw["messages"][0]["content"])
        self.max_tokens = kw["max_tokens"]
        reply = self.replies.pop(0)
        if reply is TRUNCATED:
            return SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(type="text", text='{"months": [{"number": 1,')])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))])


@pytest.fixture()
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return client

    return install


# --- check_budget ------------------------------------------------------------------


def test_budget_is_weekly_hours_times_weeks():
    assert WEEKS == 26 and budget(8) == 208 and budget(1) == 26
    assert [month_weeks(m)[0] for m in range(1, 7)] == [1, 5, 9, 14, 18, 22] and month_weeks(6)[-1] == 26


def test_plan_using_the_full_budget_is_accepted():
    assert problems(draft(per_week=8)) == []
    roadmap = finalize(RoadmapDraft.model_validate(draft(per_week=8)), scheduler_input())
    assert roadmap.total_hours == roadmap.budget_hours == 208
    assert all(w.hours <= 8 for m in roadmap.months for w in m.weeks)


def test_week_over_the_weekly_limit_is_rejected():
    d = draft(per_week=7)  # 182 hours: under the 208-hour total, so only the weekly rule can catch it
    week(d, 10)["tasks"].append({"title": "Extra exercises", "kind": "practice", "hours": 2})
    assert problems(d) == ["Week 10 plans 9 hours; the limit is 8 hours per week."]


def test_total_over_budget_is_rejected():
    found = problems(draft(per_week=9))  # 234 hours against a 208-hour budget
    assert "The plan totals 234 hours; the budget is 208 hours (8 per week x 26 weeks)." in found
    assert sum("hours per week" in p for p in found) == 14  # capped at MAX_PROBLEMS, total included


def test_budget_follows_the_users_weekly_hours():
    assert problems(draft(per_week=5), scheduler_input(hours_per_week=5)) == []
    assert problems(draft(per_week=6), scheduler_input(hours_per_week=5)) != []


def test_wrong_calendar_is_rejected():
    d = draft()
    d["months"][2]["weeks"].pop()  # month 3 loses week 13
    assert problems(d) == ["Month 3 must contain exactly weeks 9 to 13, in order."]
    d = draft()
    d["months"][0]["number"], d["months"][1]["number"] = 2, 1
    assert "Months must be numbered 1 to 6, in order." in problems(d)


def test_unknown_resource_id_is_rejected():
    assert problems(draft(resource_id="made-up-course")) == [
        'Week 1 uses resource_id "made-up-course", which is not in the approved list.'
    ]


def test_learn_task_without_a_resource_is_rejected():
    d = draft()
    del week(d, 1)["tasks"][0]["resource_id"]  # a learn task with nothing to link to
    assert len(found := problems(d)) == 1 and 'the learn task "Start the course" has no resource_id' in found[0]
    roadmap = finalize(RoadmapDraft.model_validate(draft()), scheduler_input())
    tasks = [t for m in roadmap.months for w in m.weeks for t in w.tasks]
    assert all(t.resource and t.resource.url.startswith("https://") for t in tasks if t.kind == "learn")


def test_resource_scheduled_for_more_than_its_hours_is_rejected():
    data = scheduler_input(resources=[approved(hours=3)])
    d = draft()
    week(d, 1)["tasks"] = [{"title": "Whole course", "kind": "learn", "hours": 4, "resource_id": "ml-course"}]
    assert problems(d, data) == ['Resource "ml-course" takes 3 hours but has 4 hours of "learn" tasks.']
    week(d, 1)["tasks"][0]["kind"] = "practice"  # building on a resource may take longer than studying it
    assert problems(d, data) == []


def test_phase_without_project_work_is_rejected():
    d = draft()
    week(d, 17)["tasks"][0]["kind"] = "practice"  # the only project task of phase 2
    assert len(found := problems(d)) == 1 and found[0].startswith("Phase 2 (months 3-4)")


def test_finalize_adds_links_and_lists_unscheduled_resources():
    data = scheduler_input(resources=[approved(), approved("llm-course", 12)])
    roadmap = finalize(RoadmapDraft.model_validate(draft()), data)
    first = roadmap.months[0].weeks[0].tasks[0]
    assert first.resource.url == "https://example.com/ml-course" and first.resource.title == "Course ml-course"
    assert [r.id for r in roadmap.unscheduled] == ["llm-course"]
    assert [p.months for p in roadmap.phases] == [[1, 2], [3, 4], [5, 6]]


# --- agent -------------------------------------------------------------------------


def test_over_budget_reply_is_retried_with_feedback(fake):
    client = fake(draft(per_week=9), draft(per_week=8))
    roadmap = agent.build(scheduler_input())
    assert roadmap.total_hours == 208
    assert "Weekly limit: 8 hours. Total budget: 208 hours." in client.requests[0]
    assert "rejected" not in client.requests[0]
    assert "rejected" in client.requests[1] and "The plan totals 234 hours" in client.requests[1]


def test_invalid_reply_is_retried_with_feedback(fake):
    bad = draft()
    week(bad, 3)["tasks"][0]["hours"] = 0  # tasks need at least 1 hour
    client = fake(bad, draft())
    assert agent.build(scheduler_input()).total_hours == 208
    assert "hours" in client.requests[1]


def test_never_returns_an_over_budget_roadmap(fake):
    client = fake(*[draft(per_week=9)] * agent.MAX_ATTEMPTS)
    with pytest.raises(agent.SchedulerFailed):
        agent.build(scheduler_input())
    assert len(client.requests) == agent.MAX_ATTEMPTS


def test_truncated_reply_is_reported_not_retried(fake, caplog):
    client = fake(TRUNCATED, draft())
    with caplog.at_level(logging.ERROR, logger=agent.__name__), pytest.raises(agent.SchedulerTruncated):
        agent.build(scheduler_input())
    assert len(client.requests) == 1  # not treated as invalid JSON and retried
    assert "stop_reason=max_tokens" in caplog.text
    assert client.max_tokens == agent.MAX_TOKENS >= 16000
