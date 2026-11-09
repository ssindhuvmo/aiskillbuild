"""Inputs and outputs of the scheduler. placement.place builds the Roadmap in plain Python (weeks, tasks,
hours, links); the LLM only writes a PhaseNarrative per phase, which narrative.apply copies into it.
tracking.track adds dates, priority and status (RoadmapTracking) when the roadmap is read."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.course_search.schemas import ApprovedResource
from core.agents.gap_analysis.schemas import DomainUseCase, Gap


class SchedulerInput(BaseModel):
    current_role: str
    target_role: str
    ai_level: str  # overall AI level from the capability assessment
    capabilities: dict[str, str]  # {area: level}, intake/validation.py CAPABILITY_AREAS
    domain: str
    hours_per_week: int
    gaps: list[Gap]
    domain_use_cases: list[DomainUseCase]
    resources: list[ApprovedResource]


class Project(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    problem: str = Field(min_length=1, max_length=500)  # the industry problem it solves
    dataset: str = Field(min_length=1, max_length=300)  # a public dataset by name; no links
    deliverables: list[str] = Field(min_length=1, max_length=5)


# --- Phase narrative (what the LLM writes) ------------------------------------------


class MonthText(BaseModel):
    theme: str = Field(min_length=1, max_length=120)
    milestone: str = Field(min_length=1, max_length=300)  # what the user can do or show by the end of the month


class PracticeText(BaseModel):
    id: str = Field(min_length=1, max_length=20)  # a practice task's id from the placed plan
    title: str = Field(min_length=1, max_length=200)


class PhaseNarrative(BaseModel):
    """The text of one phase. One field per month (a list's length cannot be enforced by the structured-output
    schema). It has no hours, weeks or resources: those come from placement.place and cannot be changed."""

    name: str = Field(min_length=1, max_length=120)
    first_month: MonthText
    second_month: MonthText
    practice: list[PracticeText] = Field(default_factory=list, max_length=40)
    project: Project


# --- Saved roadmap ------------------------------------------------------------------


class ResourceLink(BaseModel):
    """Copied from the approved list, never written by the model."""

    id: str
    title: str
    provider: str
    url: str
    hours: int


class RoadmapTask(BaseModel):
    id: str = ""  # "w<week>-<n>", so the narrative can reword a practice task (empty in roadmaps saved before ids)
    title: str
    kind: Literal["learn", "practice", "project"]
    hours: int
    resource: ResourceLink | None = None


class RoadmapWeek(BaseModel):
    number: int
    focus: str
    hours: int
    tasks: list[RoadmapTask]


class RoadmapMonth(BaseModel):
    number: int
    theme: str
    summary: str
    milestone: str
    hours: int
    weeks: list[RoadmapWeek]


class RoadmapPhase(BaseModel):
    number: int
    name: str
    months: list[int]
    project: Project
    gaps: list[str] = []  # the skill gaps studied in this phase, in plan order
    # pending: the AI is still writing its text; ai: written by the AI; default: plain text after the AI failed
    narrative: Literal["pending", "ai", "default"] = "ai"


class Roadmap(BaseModel):
    hours_per_week: int
    weeks: int
    budget_hours: int  # hours_per_week x weeks
    total_hours: int  # planned; never more than budget_hours
    months: list[RoadmapMonth]
    phases: list[RoadmapPhase]
    unscheduled: list[ResourceLink] = []  # approved resources that did not fit in the plan


# --- Tracking (tracking.track; worked out in Python on every read, never stored) ------

Priority = Literal["high", "medium", "low"]
# A task or month milestone: done (checked), overdue (due date passed), this_week, not_started (later).
ItemStatus = Literal["done", "overdue", "this_week", "not_started"]
# A week or phase: done (every item checked), overdue (a week past its due date with items left),
# in_progress (current, or partly done), not_started, empty (a week with nothing planned).
GroupStatus = Literal["done", "overdue", "in_progress", "not_started", "empty"]


class ItemTracking(BaseModel):
    done: bool
    status: ItemStatus
    due: date
    priority: Priority


class WeekTracking(BaseModel):
    number: int
    due: date
    status: GroupStatus


class PhaseTracking(BaseModel):
    number: int
    status: GroupStatus
    priority: Priority


class NextStep(BaseModel):
    task_id: str
    title: str
    kind: Literal["learn", "practice", "project"]
    hours: int
    week: int
    due: date
    overdue: bool
    resource: ResourceLink | None = None


class RoadmapTracking(BaseModel):
    start_date: date
    today: date
    current_week: int | None  # 1-26 while the plan runs, else None
    items: dict[str, ItemTracking]  # by task id ("w3-1") and month milestone id ("m2")
    weeks: list[WeekTracking]
    phases: list[PhaseTracking]
    next_steps: list[NextStep]  # at most 3: overdue first, then this week, then later
    done_tasks: int
    total_tasks: int
    done_hours: int
    planned_hours: int
