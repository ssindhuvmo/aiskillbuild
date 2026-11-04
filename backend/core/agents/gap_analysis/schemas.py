"""Inputs and outputs of the gap-analysis agent. GapAnalysis is also the JSON schema the
model must answer in (structured outputs); Pydantic re-validates every reply, including
the length/range limits the API schema cannot express."""
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.intake.validation import LEVELS, TARGET_LEVELS

MAX_GAPS = 8  # gaps in the plan; anything further goes to later_gaps
MAX_LATER = 10
# The capability ratings' level names, so the gap chart and the intake speak the same scale.
# A target may be one step beyond the ratings ("Expert"); a current level never is.
Level = Literal[tuple(LEVELS)]
TargetLevel = Literal[tuple(TARGET_LEVELS)]


class Strength(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    category: Literal["technical", "domain", "soft"]
    # "resume": named in the reviewed resume; "user": the user said so (capability ratings, corrections,
    # additional context); "assumed": inferred from the role and domain.
    source: Literal["resume", "user", "assumed"]
    basis: str = Field(min_length=1, max_length=600)


class Gap(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    category: Literal["technical", "domain", "tooling"]
    why_needed: str = Field(min_length=1, max_length=600)
    priority: Literal["high", "medium", "low"]
    effort_hours: int = Field(ge=1, le=200)
    domain_specific: bool
    current_level: Level  # where the user is today
    target_level: TargetLevel  # where the target role needs them; always above current_level


class Correction(BaseModel):
    """A user's correction to the analysis. "knows"/"lacks" name one skill; "note" is free text such as
    "I've never used Python". The Skill Analysis buttons add "knows", "not_needed" (left out entirely: not a
    strength, not a gap), "later" (kept out of the plan) and "plan" (kept in the plan); a re-analysis must
    respect them all."""

    kind: Literal["knows", "lacks", "note", "not_needed", "later", "plan"]
    skill: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=300)
    # "not_needed" only: the gap as it was and whether it was in the plan, so Restore can put it back.
    gap: Gap | None = None
    in_plan: bool = False


class GapInput(BaseModel):
    current_role: str
    target_role: str
    years_experience: int
    domain: str
    hours_per_week: int
    capabilities: dict[str, str]  # the user's self-ratings, {area: level}
    ai_level: str  # derived from the Machine Learning and AI / LLMs ratings
    additional_context: str | None = None
    resume: dict | None = None  # the reviewed resume data, if any
    corrections: list[Correction] = []


class DomainUseCase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    relevance: str = Field(min_length=1, max_length=600)  # why it matters for the target role


class BudgetSuggestion(BaseModel):
    """Adding a gap to the plan would go over the hour budget or the 8-gap limit: what to move to later."""

    skill: str  # the gap the user wants in the plan
    move: list[str]  # plan gaps to move to later to make room; empty when it cannot fit at all
    fits: bool  # False: the gap alone needs more hours than the whole plan
    message: str


class GapAnalysis(BaseModel):
    strengths: list[Strength] = Field(min_length=1, max_length=15)
    # The gaps the 6-month plan covers: most important first, sized to fit the hour budget.
    gaps: list[Gap] = Field(min_length=1, max_length=MAX_GAPS)
    # "Later / optional": real gaps that do not fit this plan. No resources or roadmap time are planned for them.
    later_gaps: list[Gap] = Field(default=[], max_length=MAX_LATER)
    domain_use_cases: list[DomainUseCase] = Field(min_length=1, max_length=6)
    rationale: str = Field(min_length=1, max_length=1500)
