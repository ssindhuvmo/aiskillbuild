"""All database access lives here so routes stay free of business logic."""
from sqlalchemy.orm import Session

from core.agents.intake.validation import FIELDS, missing_fields, validate_field
from core.models import Conversation, Profile, User, _now
from core.schemas import ChatMessage, ProfileOut, ProfileUpdate


class ValidationFailed(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__(str(errors))


def upsert_google_user(db: Session, claims: dict) -> User:
    """Create the user on first sign-in; refresh email, name and picture on every sign-in."""
    user = db.get(User, claims["sub"])
    if user is None:
        user = User(user_id=claims["sub"])
        db.add(user)
    user.email = claims.get("email")
    user.name = claims.get("name") or claims.get("email")
    user.picture = claims.get("picture")
    user.last_login_at = _now()
    db.commit()
    return user


def _ensure_profile(db: Session, user_id: str) -> Profile:
    """Return the user's profile, creating an empty one if needed. The user row itself
    is created at sign-in (upsert_google_user)."""
    profile = db.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id, confirmed=False)
        db.add(profile)
        db.flush()
    return profile


def _profile_dict(profile: Profile) -> dict:
    return {f: getattr(profile, f) for f in FIELDS}


def get_profile(db: Session, user_id: str) -> ProfileOut:
    profile = _ensure_profile(db, user_id)
    db.commit()
    data = _profile_dict(profile)
    return ProfileOut(confirmed=profile.confirmed, missing=missing_fields(data), **data)


def apply_updates(db: Session, user_id: str, updates: dict) -> tuple[dict, dict[str, str]]:
    """Validate and save each provided field. Returns (accepted, errors). Any change
    to the profile un-confirms it so the user re-confirms the edited summary."""
    profile = _ensure_profile(db, user_id)
    accepted: dict = {}
    errors: dict[str, str] = {}
    for field, raw in updates.items():
        if field not in FIELDS or raw is None:
            continue
        value, err = validate_field(field, raw)
        if err:
            errors[field] = err
        else:
            accepted[field] = value
    for field, value in accepted.items():
        setattr(profile, field, value)
    if accepted:
        profile.confirmed = False
    db.commit()
    return accepted, errors


def update_profile(db: Session, user_id: str, body: ProfileUpdate) -> ProfileOut:
    _, errors = apply_updates(db, user_id, body.model_dump(exclude_none=True))
    if errors:
        raise ValidationFailed(errors)
    return get_profile(db, user_id)


def confirm_profile(db: Session, user_id: str) -> ProfileOut:
    profile = _ensure_profile(db, user_id)
    missing = missing_fields(_profile_dict(profile))
    if missing:
        raise ValidationFailed({f: "Required before confirming." for f in missing})
    profile.confirmed = True
    db.commit()
    return get_profile(db, user_id)


def _conversation(db: Session, user_id: str) -> Conversation:
    _ensure_profile(db, user_id)
    conv = (
        db.query(Conversation).filter_by(user_id=user_id, kind="intake").one_or_none()
    )
    if conv is None:
        conv = Conversation(user_id=user_id, kind="intake", messages=[], state={})
        db.add(conv)
        db.flush()
    return conv


def get_messages(db: Session, user_id: str) -> list[ChatMessage]:
    conv = _conversation(db, user_id)
    db.commit()
    return [ChatMessage(**m) for m in conv.messages]


def append_message(db: Session, user_id: str, role: str, content: str) -> None:
    conv = _conversation(db, user_id)
    conv.messages = [*conv.messages, {"role": role, "content": content}]  # reassign so JSON change is detected
    db.commit()
