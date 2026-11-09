from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    # Google account "sub" claim: stable for the account, unlike the email.
    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    picture: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    current_role: Mapped[str | None] = mapped_column(String(200))
    target_role: Mapped[str | None] = mapped_column(String(200))
    domain: Mapped[str | None] = mapped_column(String(200))
    hours_per_week: Mapped[int | None] = mapped_column(Integer)
    years_experience: Mapped[int | None] = mapped_column(Integer)
    # {area: level} for the five capability areas (intake/validation.py CAPABILITY_AREAS).
    capabilities: Mapped[dict | None] = mapped_column(JSON)
    learning_preferences: Mapped[list | None] = mapped_column(JSON)  # None = not asked yet
    constraints: Mapped[dict | None] = mapped_column(JSON)  # None = not asked yet, {} = none
    additional_context: Mapped[str | None] = mapped_column(Text)  # None = not asked yet, "" = skipped
    resume_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    # Where a value came from: {"current_role": "resume" | "user"}; drives the "from resume" labels.
    field_sources: Mapped[dict | None] = mapped_column(JSON)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Confirmed strengths from the gap-analysis agent.
    inferred_skills: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "intake", later "refinement"
    messages: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentOutput(Base):
    __tablename__ = "agent_outputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    output: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GapAnalysisRecord(Base):
    """The user's current skill-gap analysis (every run is also logged in agent_outputs)."""

    __tablename__ = "gap_analyses"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    analysis: Mapped[dict] = mapped_column(JSON)  # GapAnalysis
    corrections: Mapped[list] = mapped_column(JSON, default=list)  # list[Correction]
    profile_snapshot: Mapped[dict] = mapped_column(JSON)  # the five inputs it was based on
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResourceListRecord(Base):
    """The user's current ranked resource list (every run is also logged in agent_outputs)."""

    __tablename__ = "resource_lists"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    items: Mapped[dict] = mapped_column(JSON)  # ResourceList
    snapshot: Mapped[dict] = mapped_column(JSON)  # {"analysis": GapAnalysis, "profile": SearchProfile} it was built from
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApprovedListRecord(Base):
    """The resources the user approved for their roadmap (every approval is also logged in agent_outputs)."""

    __tablename__ = "approved_lists"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    items: Mapped[dict] = mapped_column(JSON)  # ApprovedList
    snapshot: Mapped[dict] = mapped_column(JSON)  # same shape as ResourceListRecord.snapshot
    approved_via: Mapped[str] = mapped_column(String(32))  # "manual", later "refinement"
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RoadmapRecord(Base):
    """The user's current roadmap (every run is also logged in agent_outputs)."""

    __tablename__ = "roadmaps"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    roadmap: Mapped[dict] = mapped_column(JSON)  # Roadmap
    snapshot: Mapped[dict] = mapped_column(JSON)  # {"approved": ApprovedList, "profile": the five inputs} it was built from
    # The day week 1 starts; due dates follow from it. Set to the build day, kept on regenerate, user-editable.
    start_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RoadmapItemProgress(Base):
    """A checked roadmap task or month milestone (self-reported). The row exists only while it is checked.
    The fingerprint (tracking.fingerprints) keeps a check from carrying over to a different task after a
    regenerate."""

    __tablename__ = "roadmap_item_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # "w3-1" or "m2"
    fingerprint: Mapped[str] = mapped_column(String(200))
    done_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SkillProgress(Base):
    """Progress Review: one plan gap marked completed and/or rated for confidence (self-reported, BR-23).
    Keyed by the normalized skill name; rows for skills no longer in the plan are ignored, not deleted."""

    __tablename__ = "skill_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    skill: Mapped[str] = mapped_column(String(120), primary_key=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[int | None] = mapped_column(Integer)  # 1-5, None = not rated
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ProgressNotes(Base):
    """Progress Review: the user's free-text notes."""

    __tablename__ = "progress_notes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ReadinessHistory(Base):
    """The readiness score as recorded on a day (one row per day, the last recording wins): the dashboard's
    progress trend. Recorded by Update Progress, Recalculate, Refresh my plan and roadmap checks."""

    __tablename__ = "readiness_history"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    score: Mapped[int] = mapped_column(Integer)  # 0-100
    covered: Mapped[int] = mapped_column(Integer)  # skills covered ...
    needed: Mapped[int] = mapped_column(Integer)  # ... of the skills the role needs
    completion: Mapped[int] = mapped_column(Integer)  # roadmap completion, 0-100


class ReportRecord(Base):
    """The user's AI Career Transition Report: only the LLM's two sections are stored; the rest is
    assembled from saved data when it is read. Stale when the snapshot differs."""

    __tablename__ = "reports"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    narrative: Mapped[dict] = mapped_column(JSON)  # ReportNarrative
    source: Mapped[str] = mapped_column(String(16))  # ai | default
    snapshot: Mapped[dict] = mapped_column(JSON)  # gap inputs, approved list and roadmap it was written from
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class WebSearchCache(Base):
    """First-pass web search results per (skill, level, domain), shared across users so the same
    gap is not searched (and billed) again within web.CACHE_DAYS. Holds no user data."""

    __tablename__ = "web_search_cache"
    __table_args__ = (UniqueConstraint("skill", "level", "domain"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill: Mapped[str] = mapped_column(String(200))  # normalized gap skill name
    level: Mapped[str] = mapped_column(String(20))  # resource level the learner is ready for
    domain: Mapped[str] = mapped_column(String(200))  # "" unless the gap is domain-specific
    results: Mapped[list] = mapped_column(JSON)  # list[Candidate]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WebResourceCandidate(Base):
    """A web resource that users approved: a candidate for knowledge_base.json
    (scripts/list_web_candidates.py). Counts approvals; holds no user data."""

    __tablename__ = "web_resource_candidates"
    resource_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # web-<sha1 of url>
    resource: Mapped[dict] = mapped_column(JSON)  # Resource as last approved
    gaps: Mapped[list] = mapped_column(JSON, default=list)  # skill names it was approved for
    approvals: Mapped[int] = mapped_column(Integer, default=0)  # approvals that newly included it
    first_approved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_approved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ResourceProgress(Base):
    """Save / Start / Complete on one resource (self-reported, BR-21). Kept when the list is rebuilt, so it
    carries the resource itself; a row with nothing set is deleted."""

    __tablename__ = "resource_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    resource: Mapped[dict] = mapped_column(JSON)  # Resource as it was when last marked
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="not_started")  # not_started | started | completed
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Resume(Base):
    """The user's uploaded resume. `draft` is the parser's output awaiting review; only `data`
    (what the user reviewed and saved) is used by later steps."""

    __tablename__ = "resumes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1000))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)  # extracted text the parser read
    draft: Mapped[dict | None] = mapped_column(JSON)  # {"data": ResumeData, "dropped": [...]}
    data: Mapped[dict | None] = mapped_column(JSON)  # reviewed ResumeData
    status: Mapped[str] = mapped_column(String(16))  # "review" | "reviewed"
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
