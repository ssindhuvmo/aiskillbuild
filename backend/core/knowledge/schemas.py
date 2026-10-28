"""Knowledge-base entries and what a Retriever returns. Nothing here depends on how retrieval
works, so a vector retriever can return the same Candidate objects as the tag retriever."""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

Level = Literal["beginner", "intermediate", "advanced"]


class Resource(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    format: Literal["course", "paper", "project", "tutorial", "book"]
    level: Level
    cost: Literal["free", "paid"]
    hours: int = Field(ge=1, le=300)
    skills: list[str] = Field(min_length=1)  # tags from the vocabulary
    domains: list[str] = []  # empty = general, useful in any domain
    description: str = Field(min_length=1, max_length=400)


class KnowledgeBase(BaseModel):
    tags: dict[str, list[str]]  # tag -> aliases, matched against gap text
    broad_tags: list[str] = []  # generic tags ("machine-learning") that count half when matching
    resources: list[Resource]


class SearchProfile(BaseModel):
    """The parts of the user's profile that retrieval and ranking use."""

    ai_level: str  # intake/validation.py ai_level(): None, Beginner, Intermediate or Experienced
    domain: str
    hours_per_week: int


class Candidate(BaseModel):
    """A resource that may help close a gap. match_score (0-1) is the retriever's relevance
    estimate: tag overlap here, cosine similarity for a future vector retriever."""

    resource: Resource
    match_score: float = Field(ge=0, le=1)
    matched_on: list[str] = []  # tags or terms that matched, shown to the user as "why"
    source: Literal["knowledge_base", "web"] = "knowledge_base"
