"""Builds the Dashboard and the Progress Review from saved data (milestone 11). Pure Python: the repository
gathers ProgressData, everything else is worked out here and in readiness.py on every read."""
from dataclasses import dataclass, field
from datetime import date, datetime

from core.agents.course_search.schemas import ApprovedList
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.scheduler.budget import WEEKS, phase_weeks
from core.agents.scheduler.schemas import Roadmap, RoadmapTracking
from core.agents.scheduler.tracking import due_date, milestone_id, tasks
from core.progress import readiness
from core.progress.readiness import Readiness, SkillMark
from core.progress.schemas import (
    CareerSummary, CourseRow, Dashboard, PhaseProgress, ProgressReview, RadarPoint, TrendPoint,
)

CHANGE_DAYS = 7
NEXT_STEPS = 2


@dataclass
class ProgressData:
    current_role: str | None
    target_role: str | None
    analysis: GapAnalysis
    approved: ApprovedList | None  # the list the roadmap was built from (or the current approved list)
    roadmap: Roadmap | None
    roadmap_stale: bool
    tracking: RoadmapTracking | None
    done: set[str]  # checked roadmap items
    completed_resources: set[str]
    resource_status: dict[str, tuple[str, datetime | None]]  # resource id -> (status, completed_at)
    marks: dict[str, SkillMark]  # by readiness.norm(skill)
    notes: str
    history: list[tuple[date, int]] = field(default_factory=list)  # recorded scores, oldest first
    today: date = field(default_factory=date.today)
    jobs_applied: int = 0  # Job Match marks
    jobs_saved: int = 0


def current(data: ProgressData) -> Readiness:
    return readiness.compute(data.analysis, data.approved, data.roadmap, data.done, data.completed_resources,
                             data.marks)


def behind_hours(roadmap: Roadmap | None, tracking: RoadmapTracking | None) -> int:
    if roadmap is None or tracking is None:
        return 0
    return sum(t.hours for tid, t, _ in tasks(roadmap)
               if tid in tracking.items and tracking.items[tid].status == "overdue")


def from_week(tracking: RoadmapTracking | None) -> int | None:
    """The first week a refresh replans: this week, or week 1 before the start, or week 26 after the end."""
    if tracking is None:
        return None
    week = (tracking.today - tracking.start_date).days // 7 + 1
    return min(max(week, 1), WEEKS)


def _summary(data: ProgressData) -> CareerSummary:
    t, roadmap = data.tracking, data.roadmap
    behind = behind_hours(roadmap, t)
    if roadmap is None or t is None:
        status, weeks_left, end = "not_built", None, None
    else:
        end = due_date(t.start_date, WEEKS)
        week = (t.today - t.start_date).days // 7 + 1
        weeks_left = WEEKS if week < 1 else max(0, WEEKS - week + 1)
        if t.total_tasks and t.done_tasks == t.total_tasks:
            status = "complete"
        elif week < 1:
            status = "not_started"
        elif behind:
            status = "behind"
        else:
            status = "on_track"
    return CareerSummary(
        current_role=data.current_role, target_role=data.target_role, plan_status=status, weeks_left=weeks_left,
        current_week=t.current_week if t else None, start_date=t.start_date if t else None, end_date=end,
        behind_hours=behind,
    )


def _change(history: list[tuple[date, int]], today: date) -> int | None:
    """Today's recorded score against the last one at least CHANGE_DAYS earlier, else the first one."""
    if len(history) < 2:
        return None
    latest_day, latest = history[-1]
    earlier = [s for d, s in history if (latest_day - d).days >= CHANGE_DAYS]
    return latest - (earlier[-1] if earlier else history[0][1])


def _phases(roadmap: Roadmap | None, done: set[str]) -> list[PhaseProgress]:
    if roadmap is None:
        return []
    found = []
    for phase in roadmap.phases:
        weeks = set(phase_weeks(phase.number))
        own = [(tid, t) for tid, t, w in tasks(roadmap) if w in weeks]
        planned = sum(t.hours for _, t in own)
        done_hours = sum(t.hours for tid, t in own if tid in done)
        found.append(PhaseProgress(
            number=phase.number, name=phase.name, done_hours=done_hours, planned_hours=planned,
            percent=readiness.completion(done_hours, planned),
        ))
    return found


def _next_milestone(roadmap: Roadmap | None, done: set[str]) -> str | None:
    for month in (roadmap.months if roadmap else []):
        if milestone_id(month.number) not in done:
            return month.milestone
    return None


def dashboard(data: ProgressData) -> Dashboard:
    now = current(data)
    t = data.tracking
    start = t.start_date if t else None
    history = [
        TrendPoint(day=d, score=s, week=round((d - start).days / 7, 2) if start else None)
        for d, s in data.history
    ]
    return Dashboard(
        readiness=now.score,
        readiness_change=_change(data.history, data.today),
        covered=now.covered,
        needed=now.needed,
        completion=readiness.completion(t.done_hours, t.planned_hours) if t else 0,
        done_hours=t.done_hours if t else 0,
        planned_hours=t.planned_hours if t else 0,
        jobs_applied=data.jobs_applied,
        jobs_saved=data.jobs_saved,
        summary=_summary(data),
        radar=[RadarPoint(skill=g.skill, today=round(g.level_today, 2), target=g.level_target) for g in now.gaps],
        history=history,
        planned=readiness.planned_series(data.analysis, data.approved, data.roadmap) if data.roadmap else [],
        phases=_phases(data.roadmap, data.done),
        next_milestone=_next_milestone(data.roadmap, data.done),
        next_steps=t.next_steps[:NEXT_STEPS] if t else [],
    )


def _courses(data: ProgressData) -> list[CourseRow]:
    learned: dict[str, int] = {}
    for tid, task, _ in (tasks(data.roadmap) if data.roadmap else []):
        if task.kind == "learn" and task.resource and tid in data.done:
            learned[task.resource.id] = learned.get(task.resource.id, 0) + task.hours
    rows = []
    for item in (data.approved.resources if data.approved else []):
        r = item.resource
        status, completed_at = data.resource_status.get(r.id, ("not_started", None))
        done = r.hours if status == "completed" else min(r.hours, learned.get(r.id, 0))
        if status == "not_started" and done:
            status = "completed" if done >= r.hours else "started"
        rows.append(CourseRow(
            resource_id=r.id, title=r.title, url=str(r.url), skill=item.gaps[0] if item.gaps else "",
            hours_done=done, hours=r.hours, status=status, completed_at=completed_at,
        ))
    return rows


def review(data: ProgressData) -> ProgressReview:
    now = current(data)
    if data.roadmap is None:
        reason = "Build your roadmap first."
    elif data.roadmap_stale:
        reason = "Your roadmap is out of date. Regenerate it on the Learning Roadmap page first."
    else:
        reason = None
    return ProgressReview(
        readiness=now.score,
        skills=now.gaps,
        courses=_courses(data),
        notes=data.notes,
        behind_hours=behind_hours(data.roadmap, data.tracking),
        from_week=from_week(data.tracking) if data.roadmap else None,
        can_refresh=reason is None,
        refresh_reason=reason,
    )
