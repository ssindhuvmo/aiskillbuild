from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.agents.course_search.schemas import ResourceList
from core.agents.gap_analysis.schemas import BudgetSuggestion, Correction, GapAnalysis
from core.agents.resume_parser.schemas import ResumeData
from core.agents.scheduler.schemas import Roadmap


class UserOut(BaseModel):
    email: str | None = None
    name: str | None = None
    picture: str | None = None


class GoogleLoginIn(BaseModel):
    credential: str  # the Google ID token from Google Identity Services


class Step(BaseModel):
    id: str
    label: str
    done: bool


class ProfileOut(BaseModel):
    """The Career Profile as the frontend sees it."""

    current_role: str | None = None
    target_role: str | None = None
    years_experience: int | None = None
    domain: str | None = None
    hours_per_week: int | None = None
    capabilities: dict[str, str] = {}
    learning_preferences: list[str] | None = None  # None = not asked yet
    constraints: dict | None = None  # None = not asked yet, {} = none
    additional_context: str | None = None  # None = not asked yet, "" = skipped
    resume_skipped: bool = False
    resume_status: Literal["review", "reviewed"] | None = None  # None = no resume uploaded
    field_sources: dict[str, str] = {}  # {"current_role": "resume"}: shown as "from resume"
    ai_level: str | None = None  # derived from the Machine Learning and AI / LLMs ratings
    confirmed: bool = False
    missing: list[str] = []  # required fields still missing
    steps: list[Step] = []  # intake steps in asking order
    next_step: str | None = None


class ProfileUpdate(BaseModel):
    """Partial edit from the profile card or an intake widget. Every provided field is validated."""

    current_role: str | None = None
    target_role: str | None = None
    years_experience: int | str | None = None
    domain: str | None = None
    hours_per_week: int | str | None = None
    capabilities: dict[str, str] | None = None  # merged into the saved ratings
    learning_preferences: list[str] | None = None
    constraints: dict | None = None
    additional_context: str | None = None
    skip: list[str] = []  # steps to mark answered without a value: resume, preferences, constraints, context


class RoleSuggestion(BaseModel):
    """One of the 2-3 roles the intake suggests when the user asks for help choosing."""

    role: str = Field(min_length=3, max_length=100)
    reason: str = Field(min_length=1, max_length=300)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str


class IntakeState(BaseModel):
    messages: list[ChatMessage]
    profile: ProfileOut
    suggestions: list[RoleSuggestion] = []  # roles offered after "help me choose", until one is picked


class ResumeState(BaseModel):
    """The uploaded resume: the parser's draft while in review, then the user's reviewed data."""

    status: Literal["none", "review", "reviewed"]
    profile: ProfileOut
    filename: str | None = None
    uploaded_at: datetime | None = None
    data: ResumeData | None = None
    dropped: list[str] = []  # parser items left out because they weren't found in the text (review only)
    years_experience: int | None = None  # calculated from the roles


class GapState(BaseModel):
    status: Literal["none", "ready"]
    profile: ProfileOut
    analysis: GapAnalysis | None = None
    corrections: list[Correction] = []
    confirmed: bool = False
    stale: bool = False  # the profile changed since this analysis was made
    suggestion: BudgetSuggestion | None = None  # only on an adjust reply: adding a gap did not fit


class AnalyzeIn(BaseModel):
    corrections: list[Correction] = []


class AdjustIn(BaseModel):
    """One Skill Analysis button. `make_room`: plan gaps to move to later so a "plan" gap fits."""

    action: Literal["knows", "not_needed", "later", "plan", "restore"]
    skill: str = Field(min_length=1, max_length=120)
    make_room: list[str] = Field(default=[], max_length=8)


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
