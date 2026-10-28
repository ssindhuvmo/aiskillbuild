"""Inputs and outputs of the scheduler agent. RoadmapDraft is the JSON schema the model must
answer in; Pydantic re-validates every reply and budget.check_budget enforces the hour limits.
Roadmap is what gets saved and shown: the draft plus links and hour totals added in Python."""
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


class Task(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["learn", "practice", "project"]
    hours: int = Field(ge=1, le=40)
    resource_id: str | None = None  # the approved resource this task uses, if any


class Week(BaseModel):
    number: int = Field(ge=1, le=26)
    focus: str = Field(min_length=1, max_length=200)
    tasks: list[Task] = Field(min_length=1, max_length=5)


class Month(BaseModel):
    number: int = Field(ge=1, le=6)
    theme: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    milestone: str = Field(min_length=1, max_length=300)  # what the user can do or show by the end of the month
    weeks: list[Week] = Field(min_length=4, max_length=5)


class Project(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    problem: str = Field(min_length=1, max_length=500)  # the industry problem it solves
    dataset: str = Field(min_length=1, max_length=300)  # a public dataset by name; no links
    deliverables: list[str] = Field(min_length=1, max_length=5)


class Phase(BaseModel):
    number: int = Field(ge=1, le=3)
    name: str = Field(min_length=1, max_length=120)
    project: Project


class RoadmapDraft(BaseModel):
    # Phases first: the model settles the projects before the weeks, and the reply ends with month 6.
    phases: list[Phase] = Field(min_length=3, max_length=3)
    months: list[Month] = Field(min_length=6, max_length=6)


# --- Saved roadmap ------------------------------------------------------------------


class ResourceLink(BaseModel):
    """Copied from the approved list, never written by the model."""

    id: str
    title: str
    provider: str
    url: str
    hours: int


class RoadmapTask(BaseModel):
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


class Roadmap(BaseModel):
    hours_per_week: int
    weeks: int
    budget_hours: int  # hours_per_week x weeks
    total_hours: int  # planned; never more than budget_hours
    months: list[RoadmapMonth]
    phases: list[RoadmapPhase]
    unscheduled: list[ResourceLink] = []  # approved resources that did not fit in the plan
