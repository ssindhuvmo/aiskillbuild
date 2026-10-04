"""Inputs and outputs of the gap-analysis agent. GapAnalysis is also the JSON schema the
model must answer in (structured outputs); Pydantic re-validates every reply, including
the length/range limits the API schema cannot express."""
from typing import Literal

from pydantic import BaseModel, Field


MAX_GAPS = 8  # gaps in the plan; anything further goes to later_gaps


class Correction(BaseModel):
    """A user's correction to the inferred skills. "knows"/"lacks" name one skill (from the
    buttons on the page); "note" is free text such as "I've never used Python"."""

    kind: Literal["knows", "lacks", "note"]
    skill: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=300)


class GapInput(BaseModel):
    current_role: str
    target_role: str
    ai_experience: str
    domain: str
    hours_per_week: int
    corrections: list[Correction] = []
    # V2: resume-derived skills will be added here.


class Strength(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    category: Literal["technical", "domain", "soft"]
    source: Literal["assumed", "user"]  # "user" only when the user stated it in a correction
    basis: str = Field(min_length=1, max_length=600)


class Gap(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    category: Literal["technical", "domain", "tooling"]
    why_needed: str = Field(min_length=1, max_length=600)
    priority: Literal["high", "medium", "low"]
    effort_hours: int = Field(ge=1, le=200)
    domain_specific: bool


class DomainUseCase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    relevance: str = Field(min_length=1, max_length=600)  # why it matters for the target role


class GapAnalysis(BaseModel):
    strengths: list[Strength] = Field(min_length=1, max_length=15)
    # The gaps the 6-month plan covers: most important first, sized to fit the hour budget.
    gaps: list[Gap] = Field(min_length=1, max_length=MAX_GAPS)
    # "Later / optional": real gaps that do not fit this plan. No resources or roadmap time are planned for them.
    later_gaps: list[Gap] = Field(default=[], max_length=10)
    domain_use_cases: list[DomainUseCase] = Field(min_length=1, max_length=6)
    rationale: str = Field(min_length=1, max_length=1500)
