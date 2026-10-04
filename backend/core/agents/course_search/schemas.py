"""Outputs of the course search agent: a ranked resource list per skill gap."""
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Resource


class ScoreBreakdown(BaseModel):
    """Each factor is 0-1; the score is their weighted sum (see ranking.WEIGHTS)."""

    relevance: float
    level: float
    domain: float
    time: float


class RankedResource(BaseModel):
    resource: Resource
    score: float
    breakdown: ScoreBreakdown
    matched_on: list[str] = []
    source: Literal["knowledge_base", "web"] = "knowledge_base"
    also_covers: list[str] = []  # other gaps (skill names) this resource also helps with


class GapResources(BaseModel):
    gap: Gap
    resources: list[RankedResource]
    note: str | None = None  # shown when there are no resources for the gap


class ResourceList(BaseModel):
    gaps: list[GapResources]  # highest-priority gap first


class ApprovedResource(BaseModel):
    resource: Resource
    gaps: list[str]  # skill names it was chosen for: the gap it is listed under, then also_covers
    priority: Literal["high", "medium", "low"]  # of the gap it is listed under
    source: Literal["knowledge_base", "web"] = "knowledge_base"


class ApprovedList(BaseModel):
    """The resources the user approved, highest-priority gap first. This is all the scheduler
    reads: the Resources page writes it now and the refinement graph (milestone 6) will write
    the same shape, so it carries full Resource objects rather than knowledge-base ids."""

    resources: list[ApprovedResource] = Field(min_length=1)
