from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    current_role: Mapped[str | None] = mapped_column(String(200))
    target_role: Mapped[str | None] = mapped_column(String(200))
    ai_level: Mapped[str | None] = mapped_column(String(20))
    ai_knowledge_text: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(200))
    hours_per_week: Mapped[int | None] = mapped_column(Integer)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Filled by the gap-analysis agent in a later milestone; resume data can extend this.
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
