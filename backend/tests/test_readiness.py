"""Readiness Score, Skill Coverage and the planned trend (core/progress/readiness.py): pure, no DB."""
import pytest

from core.agents.course_search.schemas import ApprovedList
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.scheduler.placement import place
from core.agents.scheduler.tracking import tasks
from core.progress.readiness import SkillMark, completion, compute, norm, planned_series
from tests.test_gap_analysis import analysis
from tests.test_scheduler_budget import approved, scheduler_input

ML, PCI = "Machine learning basics", "PCI-DSS for ML"


def setup(*resources):
    """Two strengths; two high-priority gaps, Beginner -> Experienced (base credit 1/3 each)."""
    a = GapAnalysis.model_validate(analysis())
    data = scheduler_input(resources=list(resources) or [approved("ml", hours=20, gap=ML)])
    return a, ApprovedList(resources=data.resources), place(data)


def ids_of(roadmap, rid, kind=None):
    return {tid for tid, t, _ in tasks(roadmap) if t.resource and t.resource.id == rid and kind in (None, t.kind)}


def test_without_progress_only_the_starting_levels_count():
    a, approved_list, roadmap = setup()
    r = compute(a, approved_list, roadmap, set(), set(), {})
    # (2 strengths + 3 x 1/3 + 3 x 1/3) / (2 + 3 + 3) = 4 / 8
    assert r.score == 50 and (r.covered, r.needed) == (2, 4)
    ml = r.gaps[0]
    assert ml.base == pytest.approx(1 / 3) and ml.hours_planned == 20 + 7 and ml.hours_done == 0
    assert ml.level_today == 1 and ml.level_target == 3


def test_completed_skill_gives_full_credit_and_coverage():
    a, approved_list, roadmap = setup()
    r = compute(a, approved_list, roadmap, set(), set(), {norm(ML): SkillMark(completed=True)})
    assert r.score == 75 and r.covered == 3  # (2 + 3 + 1) / 8
    assert r.gaps[0].credit == 1 and r.gaps[0].level_today == 3


def test_confidence_is_averaged_with_the_hours():
    a, approved_list, roadmap = setup()
    r = compute(a, approved_list, roadmap, set(), set(), {norm(ML): SkillMark(confidence=3)})
    ml = r.gaps[0]
    assert ml.progress == pytest.approx(0.25)  # (0 hours + (3 - 1) / 4) / 2
    assert ml.credit == pytest.approx(0.5) and r.score == 56  # (2 + 1.5 + 1) / 8 = 56.25


def test_checked_tasks_and_completed_resources_count_as_hours():
    a, approved_list, roadmap = setup()
    learn = ids_of(roadmap, "ml", "learn")
    r = compute(a, approved_list, roadmap, learn, set(), {})
    assert r.gaps[0].hours_done == 20 and r.gaps[0].progress == pytest.approx(20 / 27)
    r = compute(a, approved_list, roadmap, set(), {"ml"}, {})  # marked Complete on the Resources page
    assert r.gaps[0].hours_done == 27 and r.gaps[0].credit == 1


def test_priority_weights():
    a, approved_list, roadmap = setup()
    a.gaps[1].priority = "low"
    r = compute(a, approved_list, roadmap, set(), set(), {norm(PCI): SkillMark(completed=True)})
    assert r.score == round(100 * (2 + 3 / 3 + 1) / (2 + 3 + 1))  # 67
    assert [g.weight for g in r.gaps] == [3, 1]


def test_planned_series_rises_to_the_plan_followed_through():
    a, approved_list, roadmap = setup()
    series = planned_series(a, approved_list, roadmap)
    assert len(series) == 27 and series[0] == 50
    assert all(x <= y for x, y in zip(series, series[1:]))
    # Every scheduled hour done: ML is covered, PCI-DSS (no resources) stays at its starting level.
    assert series[-1] == compute(a, approved_list, roadmap, {tid for tid, _, _ in tasks(roadmap)}, set(), {}).score == 75


def test_completion():
    assert completion(0, 0) == 0 and completion(19, 162) == 12 and completion(5, 5) == 100
