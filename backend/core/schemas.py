from typing import Literal

from pydantic import BaseModel

from core.agents.gap_analysis.schemas import Correction, GapAnalysis


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
