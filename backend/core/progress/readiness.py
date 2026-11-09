"""Readiness Score, Skill Coverage and Roadmap Completion (milestone 11). Plain Python, no DB, no LLM.

The formula, for each gap g in the plan (GapAnalysis.gaps):

    base_g     = index(current_level) / index(target_level)        on TARGET_LEVELS (None=0 ... Expert=4)
    hours_g    = done / planned learn + practice hours of g's approved resources (a resource's planned hours
                 are its hours plus its practice hours; a resource marked Complete counts as fully done,
                 otherwise its checked roadmap tasks count, capped at its planned hours)
    conf_g     = (confidence - 1) / 4, when the user rated it on Progress Review (1-5)
    progress_g = 1 when the user marked the skill completed;
                 else the mean of hours_g and conf_g when rated; else hours_g
    credit_g   = base_g + (1 - base_g) * progress_g

    Readiness  = round(100 * (S + sum(w_g * credit_g)) / (S + sum(w_g)))
                 S = number of strengths (each counts 1); w_g = 3 / 2 / 1 for high / medium / low priority
    Coverage   = (S + gaps with credit_g = 1) of (S + gaps in the plan)
    Completion = round(100 * done hours / planned hours) of the roadmap's tasks

The planned trend uses the same formula for each week w, with hours_g = the hours the roadmap schedules for g
up to week w, no confidence and nothing marked completed: where the score goes if the plan is followed.
A gap's resources are those listed under it in the approved list (ApprovedResource.gaps[0]), as in placement.
"""
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel

from core.agents.course_search.schemas import ApprovedList
from core.agents.gap_analysis.schemas import Gap, GapAnalysis
from core.agents.intake.validation import TARGET_LEVELS
from core.agents.scheduler.budget import WEEKS, practice_hours
from core.agents.scheduler.schemas import Roadmap
from core.agents.scheduler.tracking import tasks

WEIGHTS = {"high": 3, "medium": 2, "low": 1}
CONFIDENCE_MIN, CONFIDENCE_MAX = 1, 5
EPSILON = 1e-9


def norm(skill: str) -> str:
    """How a skill is matched between the gap analysis and saved progress (same as the gap analysis agent)."""
    return " ".join(skill.lower().split())


@dataclass(frozen=True)
class SkillMark:
    """The user's Progress Review entry for one skill."""

    completed: bool = False
    confidence: int | None = None  # 1-5


class GapReadiness(BaseModel):
    skill: str
    priority: str
    current_level: str
    target_level: str
    weight: int
    base: float  # 0-1, credit before any progress
    hours_done: int
    hours_planned: int
    completed: bool
    confidence: int | None
    progress: float  # 0-1
    credit: float  # 0-1
    level_today: float  # current_level index moved toward the target by the progress
    level_target: int  # target_level index


class Readiness(BaseModel):
    score: int  # 0-100
    covered: int
    needed: int
    strengths: int
    gaps: list[GapReadiness]


def level_index(level: str) -> int:
    return TARGET_LEVELS.index(level)


def base_credit(gap: Gap) -> float:
    target = level_index(gap.target_level)
    return level_index(gap.current_level) / target if target else 0.0


def planned_hours(approved: ApprovedList | None) -> dict[str, dict[str, int]]:
    """{gap skill: {resource id: learn + practice hours}} from the approved list."""
    found: dict[str, dict[str, int]] = {}
    for item in (approved.resources if approved else []):
        if item.gaps:
            hours = item.resource.hours + practice_hours(item.resource.hours)
            found.setdefault(item.gaps[0], {}).setdefault(item.resource.id, hours)
    return found


def task_hours(roadmap: Roadmap | None, include) -> dict[str, int]:
    """Learn + practice hours per resource over the roadmap tasks for which include(task id, week) is true."""
    hours: dict[str, int] = {}
    for tid, task, week in (tasks(roadmap) if roadmap else []):
        if task.resource and task.kind in ("learn", "practice") and include(tid, week):
            hours[task.resource.id] = hours.get(task.resource.id, 0) + task.hours
    return hours


def _credit(base: float, progress: float) -> float:
    return base + (1 - base) * min(max(progress, 0.0), 1.0)


def score(strengths: int, weighted: Iterable[tuple[int, float]]) -> int:
    weighted = list(weighted)
    total = strengths + sum(w for w, _ in weighted)
    if not total:
        return 0
    return round(100 * (strengths + sum(w * c for w, c in weighted)) / total)


def compute(
    analysis: GapAnalysis,
    approved: ApprovedList | None,
    roadmap: Roadmap | None,
    done: set[str],
    completed_resources: set[str],
    marks: dict[str, SkillMark],
) -> Readiness:
    """Today's readiness. `marks` is keyed by norm(skill)."""
    planned = planned_hours(approved)
    done_by_resource = task_hours(roadmap, lambda tid, _: tid in done)
    gaps = []
    for gap in analysis.gaps:
        resources = planned.get(gap.skill, {})
        hours_planned = sum(resources.values())
        hours_done = sum(
            hours if rid in completed_resources else min(hours, done_by_resource.get(rid, 0))
            for rid, hours in resources.items()
        )
        mark = marks.get(norm(gap.skill), SkillMark())
        hours_share = hours_done / hours_planned if hours_planned else 0.0
        if mark.completed:
            progress = 1.0
        elif mark.confidence is not None:
            progress = (hours_share + (mark.confidence - CONFIDENCE_MIN) / (CONFIDENCE_MAX - CONFIDENCE_MIN)) / 2
        else:
            progress = hours_share
        base = base_credit(gap)
        current, target = level_index(gap.current_level), level_index(gap.target_level)
        gaps.append(GapReadiness(
            skill=gap.skill, priority=gap.priority, current_level=gap.current_level, target_level=gap.target_level,
            weight=WEIGHTS[gap.priority], base=base, hours_done=hours_done, hours_planned=hours_planned,
            completed=mark.completed, confidence=mark.confidence, progress=progress, credit=_credit(base, progress),
            level_today=current + (target - current) * progress, level_target=target,
        ))
    strengths = len(analysis.strengths)
    return Readiness(
        score=score(strengths, ((g.weight, g.credit) for g in gaps)),
        covered=strengths + sum(1 for g in gaps if g.credit >= 1 - EPSILON),
        needed=strengths + len(gaps),
        strengths=strengths,
        gaps=gaps,
    )


def planned_series(analysis: GapAnalysis, approved: ApprovedList | None, roadmap: Roadmap | None) -> list[int]:
    """Readiness at the end of weeks 0 (the start) to 26 if every task is done in its week."""
    planned = planned_hours(approved)
    strengths = len(analysis.strengths)
    series = []
    for week in range(WEEKS + 1):
        scheduled = task_hours(roadmap, lambda _, w, upto=week: w <= upto)
        weighted = []
        for gap in analysis.gaps:
            resources = planned.get(gap.skill, {})
            total = sum(resources.values())
            hours = sum(min(h, scheduled.get(rid, 0)) for rid, h in resources.items())
            weighted.append((WEIGHTS[gap.priority], _credit(base_credit(gap), hours / total if total else 0.0)))
        series.append(score(strengths, weighted))
    return series


def completion(done_hours: int, planned: int) -> int:
    return round(100 * done_hours / planned) if planned else 0
