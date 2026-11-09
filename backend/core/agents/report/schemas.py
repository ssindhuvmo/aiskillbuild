"""The AI Career Transition Report (SPEC.md section 8, BRD 8.4).

ReportNarrative is all the LLM writes: the Career Fit Assessment and the Recommended Career Strategy. Every
other section of TransitionReport is assembled in Python (assemble.build) from saved data, so its facts,
numbers, dates and links are the app's own.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.gap_analysis.schemas import Gap, Strength
from core.agents.scheduler.schemas import NextStep, Priority, Project


class ReportNarrative(BaseModel):
    career_fit: str = Field(min_length=50, max_length=2000)  # how the background fits the target role
    strategy: str = Field(min_length=50, max_length=2000)  # how to make the move over the six months


class CareerGoal(BaseModel):
    current_role: str
    target_role: str
    domain: str
    hours_per_week: int
    weeks: int


class ResumeSummary(BaseModel):
    roles: list[str]  # "Title, Employer (2019–present)"
    skills: list[str]
    certifications: list[str]
    education: list[str]


class CurrentProfile(BaseModel):
    years_experience: int | None
    ai_level: str | None
    capabilities: dict[str, str]
    learning_preferences: list[str]
    constraints: list[str]  # readable lines, e.g. "Budget: free resources only"
    additional_context: str | None
    resume: ResumeSummary | None


class PlanItem(BaseModel):
    """One plan gap in study order, with where it is studied and the hours its resources take."""

    skill: str
    priority: Priority
    current_level: str
    target_level: str
    phase: int | None  # None: none of its resources fit in the plan
    resource_hours: int


class ReportResource(BaseModel):
    title: str
    provider: str
    url: str
    format: str
    cost: Literal["free", "paid"]
    hours: int
    gap: str
    scheduled: bool


class ReportMilestone(BaseModel):
    month: int
    theme: str
    milestone: str
    due: date
    done: bool


class ReportPhase(BaseModel):
    number: int
    name: str
    months: list[int]
    gaps: list[str]
    hours: int
    status: str
    milestones: list[ReportMilestone]


class ReportProject(Project):
    phase: int


class TransitionReport(BaseModel):
    """The 11 sections in SPEC.md order."""

    written_at: datetime
    narrative_source: Literal["ai", "default"]
    career_goal: CareerGoal
    current_profile: CurrentProfile
    career_fit: str
    transferable_skills: list[Strength]
    gaps: list[Gap]
    later_gaps: list[Gap]
    strategy: str
    learning_plan: list[PlanItem]
    resources: list[ReportResource]
    start_date: date
    planned_hours: int
    budget_hours: int
    roadmap: list[ReportPhase]
    projects: list[ReportProject]
    next_steps: list[NextStep]


class ReportState(BaseModel):
    status: Literal["none", "ready"]
    can_generate: bool = False  # a current roadmap exists
    stale: bool = False  # the profile, gaps, resources or roadmap changed since the report was written
    report: TransitionReport | None = None
    notice: str | None = None  # set on a generate reply when the plain default text was used
