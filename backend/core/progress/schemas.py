"""What the Dashboard and Progress Review pages show (milestone 11). Every number here is worked out in Python
(readiness.py, assemble.py) from saved data; the LLM never supplies one."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.scheduler.schemas import NextStep
from core.progress.readiness import GapReadiness

PlanStatus = Literal["not_built", "not_started", "on_track", "behind", "complete"]
CourseStatus = Literal["not_started", "started", "completed"]
MAX_NOTES = 2000


class CareerSummary(BaseModel):
    current_role: str | None
    target_role: str | None
    plan_status: PlanStatus
    weeks_left: int | None  # None without a roadmap
    current_week: int | None
    start_date: date | None
    end_date: date | None
    behind_hours: int  # undone hours of overdue tasks


class RadarPoint(BaseModel):
    skill: str
    today: float  # level index, 0 (None) to 4 (Expert)
    target: int


class TrendPoint(BaseModel):
    day: date
    week: float | None  # plan week the day falls in (0 = the start date); None without a roadmap
    score: int


class PhaseProgress(BaseModel):
    number: int
    name: str
    percent: int
    done_hours: int
    planned_hours: int


class Dashboard(BaseModel):
    readiness: int
    readiness_change: int | None  # against the recorded score at least 7 days earlier (or the first one)
    covered: int
    needed: int
    completion: int  # 0-100, roadmap hours done
    done_hours: int
    planned_hours: int
    jobs_applied: int | None = None  # Job Match (milestone 12)
    summary: CareerSummary
    radar: list[RadarPoint]
    history: list[TrendPoint]
    planned: list[int]  # readiness by week 0-26 if the plan is followed; empty without a roadmap
    phases: list[PhaseProgress]
    next_milestone: str | None
    next_steps: list[NextStep]


class CourseRow(BaseModel):
    resource_id: str
    title: str
    url: str
    skill: str
    hours_done: int  # learn hours checked on the roadmap (all of them once the resource is completed)
    hours: int
    status: CourseStatus
    completed_at: datetime | None = None


class ProgressReview(BaseModel):
    readiness: int
    skills: list[GapReadiness]
    courses: list[CourseRow]
    notes: str
    behind_hours: int
    from_week: int | None  # "Refresh my plan" replans from this week; None without a roadmap
    can_refresh: bool
    refresh_reason: str | None = None  # why it can't refresh


class SkillMarkIn(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    completed: bool = False
    confidence: int | None = Field(default=None, ge=1, le=5)


class ProgressReviewIn(BaseModel):
    skills: list[SkillMarkIn] = Field(default=[], max_length=20)
    notes: str = Field(default="", max_length=MAX_NOTES)
