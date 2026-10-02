"""All database access lives here so routes stay free of business logic."""
from sqlalchemy.orm import Session

from core.agents.course_search.schemas import ResourceList
from core.agents.intake.validation import FIELDS, missing_fields, validate_field
from core.agents.gap_analysis.schemas import Correction, GapAnalysis
from core.knowledge.schemas import SearchProfile
from core.models import AgentOutput, Conversation, GapAnalysisRecord, Profile, ResourceListRecord, User, _now
from core.schemas import ChatMessage, GapState, ProfileOut, ProfileUpdate, ResourceState


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
        _unconfirm_gaps(db, profile)
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


# --- Skill-gap analysis -------------------------------------------------------------


def _unconfirm_gaps(db: Session, profile: Profile) -> None:
    """A profile edit means the confirmed skills may no longer apply."""
    record = db.get(GapAnalysisRecord, profile.user_id)
    if record is not None:
        record.confirmed = False
    profile.inferred_skills = None


def get_gap_state(db: Session, user_id: str) -> GapState:
    profile = get_profile(db, user_id)
    record = db.get(GapAnalysisRecord, user_id)
    if record is None:
        return GapState(status="none", profile=profile)
    current = {f: getattr(profile, f) for f in FIELDS}
    return GapState(
        status="ready",
        profile=profile,
        analysis=GapAnalysis.model_validate(record.analysis),
        corrections=[Correction.model_validate(c) for c in record.corrections],
        confirmed=record.confirmed,
        stale=record.profile_snapshot != current,
    )


def save_gap_analysis(
    db: Session, user_id: str, analysis: GapAnalysis, corrections: list[Correction], snapshot: dict
) -> GapState:
    data = analysis.model_dump()
    record = db.get(GapAnalysisRecord, user_id)
    if record is None:
        record = GapAnalysisRecord(user_id=user_id)
        db.add(record)
    record.analysis = data
    record.corrections = [c.model_dump() for c in corrections]
    record.profile_snapshot = snapshot
    record.confirmed = False
    db.add(
        AgentOutput(
            user_id=user_id,
            agent="gap_analysis",
            output={"input": snapshot, "corrections": record.corrections, "analysis": data},
        )
    )
    db.commit()
    return get_gap_state(db, user_id)


def confirm_gaps(db: Session, user_id: str) -> GapState:
    """Mark the analysis confirmed and store the confirmed strengths on the profile."""
    state = get_gap_state(db, user_id)
    if state.status != "ready" or state.stale:
        raise ValidationFailed({"analysis": "Run the skill-gap analysis for your current profile first."})
    db.get(GapAnalysisRecord, user_id).confirmed = True
    _ensure_profile(db, user_id).inferred_skills = {"strengths": [s.model_dump() for s in state.analysis.strengths]}
    db.commit()
    return get_gap_state(db, user_id)


# --- Resources (course search) ------------------------------------------------------


def search_profile(profile: ProfileOut) -> SearchProfile:
    return SearchProfile(
        ai_experience=profile.ai_experience, domain=profile.domain, hours_per_week=profile.hours_per_week
    )


def _gaps_ready(gap_state: GapState) -> bool:
    return gap_state.status == "ready" and gap_state.confirmed and not gap_state.stale


def _resource_snapshot(gap_state: GapState) -> dict:
    """The inputs a resource list depends on; the list is stale when these change."""
    return {
        "analysis": gap_state.analysis.model_dump(mode="json") if gap_state.analysis else None,
        "profile": search_profile(gap_state.profile).model_dump() if gap_state.profile.confirmed else None,
    }


def get_resource_state(db: Session, user_id: str) -> ResourceState:
    gap_state = get_gap_state(db, user_id)
    ready = _gaps_ready(gap_state)
    record = db.get(ResourceListRecord, user_id)
    if record is None:
        return ResourceState(status="none", profile=gap_state.profile, gaps_confirmed=ready)
    return ResourceState(
        status="ready",
        profile=gap_state.profile,
        gaps_confirmed=ready,
        resources=ResourceList.model_validate(record.items),
        stale=not ready or record.snapshot != _resource_snapshot(gap_state),
    )


def save_resource_list(db: Session, user_id: str, resources: ResourceList, gap_state: GapState) -> ResourceState:
    items = resources.model_dump(mode="json")
    snapshot = _resource_snapshot(gap_state)
    record = db.get(ResourceListRecord, user_id)
    if record is None:
        record = ResourceListRecord(user_id=user_id)
        db.add(record)
    record.items = items
    record.snapshot = snapshot
    db.add(AgentOutput(user_id=user_id, agent="course_search", output={"input": snapshot, "resources": items}))
    db.commit()
    return get_resource_state(db, user_id)
