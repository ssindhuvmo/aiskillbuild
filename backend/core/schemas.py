from pydantic import BaseModel


class ProfileOut(BaseModel):
    user_id: str
    current_role: str | None = None
    target_role: str | None = None
    ai_level: str | None = None
    ai_knowledge_text: str | None = None
    domain: str | None = None
    hours_per_week: int | None = None
    confirmed: bool = False
    missing: list[str] = []


class ProfileUpdate(BaseModel):
    """Partial edit from the summary card. Every provided field is validated."""

    current_role: str | None = None
    target_role: str | None = None
    ai_level: str | None = None
    ai_knowledge_text: str | None = None
    domain: str | None = None
    hours_per_week: int | str | None = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str


class IntakeState(BaseModel):
    user_id: str
    messages: list[ChatMessage]
    profile: ProfileOut
