"""Outputs of the course search agent: a ranked resource list per skill gap, what the web search
and refinement models return, and the approved list the scheduler reads."""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Format, Level, Resource, Source

# The page's "Type" filter groups formats; paper and tutorial show as Article.
TypeGroup = Literal["course", "video", "article", "repository", "book", "project"]
TYPE_OF: dict[str, str] = {
    "course": "course", "video": "video", "article": "article", "paper": "article", "tutorial": "article",
    "repository": "repository", "book": "book", "project": "project",
}


class ScoreBreakdown(BaseModel):
    """Each factor is 0-1; the score is their weighted sum (see ranking.WEIGHTS)."""

    relevance: float
    level: float
    domain: float
    time: float
    # Defaults keep lists saved before milestone 9 readable (0.5 = neutral).
    preference: float = 0.5
    quality: float = 0.5


class RankedResource(BaseModel):
    resource: Resource
    score: float
    breakdown: ScoreBreakdown
    matched_on: list[str] = []
    source: Source = "knowledge_base"
    also_covers: list[str] = []  # other gaps (skill names) this resource also helps with


class GapResources(BaseModel):
    gap: Gap
    resources: list[RankedResource]
    note: str | None = None  # shown when there are no resources for the gap


class ResourceList(BaseModel):
    gaps: list[GapResources]  # highest-priority gap first


class WebFinding(BaseModel):
    """One resource the web search model recorded. Validated here; the URL must also appear in
    the search results it came from (web.py)."""

    title: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    format: Format
    level: Level
    cost: Literal["free", "paid"]
    hours: int = Field(ge=1, le=300)
    description: str = Field(min_length=1, max_length=400)
    relevance: float = Field(ge=0, le=1)  # how well it covers the gap
    domain_specific: bool = False  # written for the user's industry


class Preferences(BaseModel):
    """What the user asked for in the refinement chat; applied to every later version of the list."""

    cost: Literal["any", "free", "paid"] = "any"
    formats: list[Format] = []  # formats to favour
    levels: list[Level] = []  # filter; [] = every level
    types: list[TypeGroup] = []  # filter on TYPE_OF groups; [] = every type


class SearchRequest(BaseModel):
    skill: str  # a gap's skill name, exactly as listed
    format: Format | None = None
    hint: str | None = Field(default=None, max_length=200)  # what to look for, in the user's words


class RefinementAction(BaseModel):
    """The refinement model's reading of one user message: operations only. Python applies them,
    so the model never edits the list or writes a URL."""

    remove_ids: list[str] = []
    restore_ids: list[str] = []
    cost: Literal["any", "free", "paid"] | None = None  # None = leave as it is
    favour_formats: list[Format] | None = None  # None = leave as it is; [] = no preference
    levels: list[Level] | None = None  # level filter; None = leave as it is; [] = every level
    types: list[TypeGroup] | None = None  # type filter; None = leave as it is; [] = every type
    known_skills: list[str] = []  # gaps the user already knows: their resources are hidden
    restore_skills: list[str] = []
    add_more: list[SearchRequest] = []  # needs a new web search
    approve: bool = False
    question: str | None = Field(default=None, max_length=600)  # asked instead of changing anything


class ApprovedResource(BaseModel):
    resource: Resource
    gaps: list[str]  # skill names it was chosen for: the gap it is listed under, then also_covers
    priority: Literal["high", "medium", "low"]  # of the gap it is listed under
    source: Source = "knowledge_base"


class ApprovedList(BaseModel):
    """The resources the user approved, highest-priority gap first. This is all the scheduler
    reads. It carries full Resource objects rather than knowledge-base ids, because web results
    exist nowhere else."""

    resources: list[ApprovedResource] = Field(min_length=1)
