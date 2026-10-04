from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
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
    ai_experience: Mapped[str | None] = mapped_column(String(20))
    domain: Mapped[str | None] = mapped_column(String(200))
    hours_per_week: Mapped[int | None] = mapped_column(Integer)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Confirmed strengths from the gap-analysis agent; resume data can extend this in V2.
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
