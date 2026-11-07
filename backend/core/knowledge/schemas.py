"""Knowledge-base entries and what a Retriever returns. Nothing here depends on how retrieval
works, so a vector retriever can return the same Candidate objects as the tag retriever."""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

Level = Literal["beginner", "intermediate", "advanced"]
# paper and tutorial are kept for existing entries and saved lists; the page groups them under "Article".
Format = Literal["course", "video", "article", "paper", "tutorial", "repository", "book", "project"]
Source = Literal["knowledge_base", "web", "youtube"]


class Quality(BaseModel):
    """Quality signals a source reports (YouTube: views and likes). Never written by an LLM."""

    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    trusted: bool = False  # from a channel in data/youtube_channels.json


class Resource(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    format: Format
    level: Level
    cost: Literal["free", "paid"]
    hours: int = Field(ge=1, le=300)
    skills: list[str] = Field(min_length=1)  # tags from the vocabulary
    domains: list[str] = []  # empty = general, useful in any domain
    description: str = Field(min_length=1, max_length=400)
    quality: Quality | None = None  # None: the source reports no signals (curated and web resources)


class KnowledgeBase(BaseModel):
    tags: dict[str, list[str]]  # tag -> aliases, matched against gap text
    broad_tags: list[str] = []  # generic tags ("machine-learning") that count half when matching
    resources: list[Resource]


class SearchProfile(BaseModel):
    """The parts of the user's profile that retrieval and ranking use."""

    ai_level: str  # intake/validation.py ai_level(): None, Beginner, Intermediate or Experienced
    domain: str
    hours_per_week: int
    # Intake answers (intake/validation.py PREFERENCES); [] = not given, so preference fit is neutral.
    preferences: list[str] = []
    free_only: bool = False  # constraints.budget == "free_only": paid resources are never listed


class Candidate(BaseModel):
    """A resource that may help close a gap. match_score (0-1) is the retriever's relevance
    estimate: tag overlap here, cosine similarity for a future vector retriever."""

    resource: Resource
    match_score: float = Field(ge=0, le=1)
    matched_on: list[str] = []  # tags or terms that matched, shown to the user as "why"
    source: Source = "knowledge_base"
