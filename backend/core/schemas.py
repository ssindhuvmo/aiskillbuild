from typing import Literal

from pydantic import BaseModel

from core.agents.course_search.schemas import ResourceList
from core.agents.gap_analysis.schemas import Correction, GapAnalysis
from core.agents.scheduler.schemas import Roadmap


class UserOut(BaseModel):
    email: str | None = None
    name: str | None = None
    picture: str | None = None


class GoogleLoginIn(BaseModel):
    credential: str  # the Google ID token from Google Identity Services


class ProfileOut(BaseModel):
    current_role: str | None = None
    target_role: str | None = None
    ai_experience: str | None = None
    domain: str | None = None
    hours_per_week: int | None = None
    confirmed: bool = False
    missing: list[str] = []


class ProfileUpdate(BaseModel):
    """Partial edit from the summary card. Every provided field is validated."""

    current_role: str | None = None
    target_role: str | None = None
    ai_experience: str | None = None
    domain: str | None = None
    hours_per_week: int | str | None = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str


class IntakeState(BaseModel):
    messages: list[ChatMessage]
    profile: ProfileOut


class GapState(BaseModel):
    status: Literal["none", "ready"]
    profile: ProfileOut
    analysis: GapAnalysis | None = None
    corrections: list[Correction] = []
    confirmed: bool = False
    stale: bool = False  # the profile changed since this analysis was made


class AnalyzeIn(BaseModel):
    corrections: list[Correction] = []


class ResourceState(BaseModel):
    status: Literal["none", "ready"]
    profile: ProfileOut
    gaps_confirmed: bool = False  # a search needs a confirmed, up-to-date gap analysis
    resources: ResourceList | None = None
    stale: bool = False  # the gap analysis or profile changed since this list was built
    approved_ids: list[str] | None = None  # resource ids in the approved list; None = nothing approved yet
    approval_stale: bool = False  # the list changed since it was approved
    messages: list[ChatMessage] = []  # the refinement chat
    notice: str | None = None  # e.g. live web search was unavailable for this list


class RemoveIn(BaseModel):
    resource_id: str


class RoadmapState(BaseModel):
    status: Literal["none", "ready"]
    profile: ProfileOut
    list_approved: bool = False  # a roadmap needs an approved, up-to-date resource list
    roadmap: Roadmap | None = None
    stale: bool = False  # the approved list or profile changed since this roadmap was built
