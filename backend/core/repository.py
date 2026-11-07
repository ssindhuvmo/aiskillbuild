"""All database access lives here so routes stay free of business logic."""
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.agents.course_search.schemas import ApprovedList, ApprovedResource, ResourceList
from core.agents.intake.validation import (
    DEFAULT_PREFERENCES, FIELDS, SKIPPABLE, ai_level, check_combination, missing_fields, next_step, steps,
    validate_field,
)
from core.agents.gap_analysis.schemas import Correction, GapAnalysis
from core.agents.resume_parser.rules import years_of_experience
from core.agents.resume_parser.schemas import ResumeData, ResumeDraft
from core.agents.scheduler.schemas import Roadmap
from core.knowledge.schemas import Candidate, Resource, SearchProfile
from core.models import (
    AgentOutput, ApprovedListRecord, Conversation, GapAnalysisRecord, Profile, ResourceListRecord, ResourceProgress,
    Resume, RoadmapRecord, User, WebResourceCandidate, WebSearchCache, _now,
)
from core.schemas import (
    ChatMessage, GapState, IntakeState, ProfileOut, ProfileUpdate, ResourceProgressOut, ResourceState, ResumeState,
    RoadmapState, RoleSuggestion,
)


class ValidationFailed(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__(str(errors))


class NotReady(Exception):
    """An earlier step has to be completed (or redone) first."""


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


def delete_user_data(db: Session, user_id: str) -> None:
    """Start over: delete everything saved for this user. The user row stays, so the sign-in
    keeps working. Any new table with a user_id must be added here."""
    for model in (
        RoadmapRecord, ApprovedListRecord, ResourceListRecord, ResourceProgress, GapAnalysisRecord, AgentOutput,
        Conversation, Resume, Profile,
    ):
        db.query(model).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.commit()


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


def _resume_status(db: Session, user_id: str) -> str | None:
    resume = db.get(Resume, user_id)
    return resume.status if resume else None


def get_profile(db: Session, user_id: str) -> ProfileOut:
    profile = _ensure_profile(db, user_id)
    help_choose = bool(_conversation(db, user_id).state.get("help_choose"))
    data = _profile_dict(profile)
    progress = {**data, "resume_status": _resume_status(db, user_id), "resume_skipped": profile.resume_skipped}
    db.commit()
    return ProfileOut(
        **{**data, "capabilities": data["capabilities"] or {}},
        resume_skipped=profile.resume_skipped,
        resume_status=progress["resume_status"],
        field_sources=profile.field_sources or {},
        ai_level=ai_level(data["capabilities"]),
        confirmed=profile.confirmed,
        missing=missing_fields(data),
        steps=steps(progress, help_choose),
        next_step=next_step(progress, help_choose),
    )


# What skipping an optional step stores (resume is a flag of its own).
SKIP_VALUES = {"preferences": ("learning_preferences", DEFAULT_PREFERENCES), "constraints": ("constraints", {}),
               "context": ("additional_context", "")}


def apply_updates(db: Session, user_id: str, updates: dict, source: str = "user") -> tuple[dict, dict[str, str]]:
    """Validate and save each provided field; `skip` marks optional steps answered. Returns
    (accepted, errors). Any change to the profile un-confirms it so the user re-confirms the edited
    summary, and records where each changed value came from (`source`: "user" or "resume")."""
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
    if "capabilities" in accepted:  # a partial rating update
        accepted["capabilities"] = {**(profile.capabilities or {}), **accepted["capabilities"]}
    skipped = []
    for step in updates.get("skip") or []:
        if step not in SKIPPABLE:
            errors["skip"] = f"Unknown step: {step}."
        elif step == "resume":
            profile.resume_skipped = True
            skipped.append(step)
        else:
            field, value = SKIP_VALUES[step]
            if field not in accepted and getattr(profile, field) is None:
                accepted[field] = value
            skipped.append(step)
    problem = check_combination(
        accepted.get("learning_preferences", profile.learning_preferences),
        accepted.get("constraints", profile.constraints),
    )
    if problem:
        for field in ("learning_preferences", "constraints"):
            if field in accepted:
                errors[field] = problem
                del accepted[field]
    changed = {f: v for f, v in accepted.items() if getattr(profile, f) != v}
    for field, value in changed.items():
        setattr(profile, field, value)
    if changed:
        profile.field_sources = {**(profile.field_sources or {}), **{f: source for f in changed}}
        profile.confirmed = False
        _unconfirm_gaps(db, profile)
    if "target_role" in changed:  # a role was chosen: the suggestions have served their purpose
        set_intake_flags(db, user_id, help_choose=False, suggestions=[])
    db.commit()
    if skipped:
        accepted["skipped"] = skipped
    return accepted, errors


def update_profile(db: Session, user_id: str, body: ProfileUpdate) -> ProfileOut:
    _, errors = apply_updates(db, user_id, body.model_dump(exclude_none=True))
    if errors:
        raise ValidationFailed(errors)
    return get_profile(db, user_id)


def confirm_profile(db: Session, user_id: str) -> ProfileOut:
    profile = _ensure_profile(db, user_id)
    errors = {f: "Required before confirming." for f in missing_fields(_profile_dict(profile))}
    if _resume_status(db, user_id) == "review":
        errors["resume"] = "Finish reviewing your resume (save it or remove it) before confirming."
    if errors:
        raise ValidationFailed(errors)
    if profile.learning_preferences is None:  # BR-05: sensible defaults when not chosen
        profile.learning_preferences = list(DEFAULT_PREFERENCES)
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


def set_intake_flags(db: Session, user_id: str, **flags) -> None:
    """Intake chat state: `help_choose` (the user asked for role suggestions) and `suggestions`."""
    conv = _conversation(db, user_id)
    conv.state = {**conv.state, **flags}
    db.commit()


def intake_flags(db: Session, user_id: str) -> dict:
    conv = _conversation(db, user_id)
    db.commit()
    return dict(conv.state)


def get_suggestions(db: Session, user_id: str) -> list[RoleSuggestion]:
    return [RoleSuggestion.model_validate(s) for s in intake_flags(db, user_id).get("suggestions", [])]


def get_intake_state(db: Session, user_id: str) -> IntakeState:
    return IntakeState(
        messages=get_messages(db, user_id), profile=get_profile(db, user_id), suggestions=get_suggestions(db, user_id)
    )


# --- Resume -------------------------------------------------------------------------


def get_resume_state(db: Session, user_id: str) -> ResumeState:
    profile = get_profile(db, user_id)
    record = db.get(Resume, user_id)
    if record is None:
        return ResumeState(status="none", profile=profile)
    if record.status == "review":
        draft = ResumeDraft.model_validate(record.draft)
        data, dropped = draft.data, draft.dropped
    else:
        data, dropped = ResumeData.model_validate(record.data), []
    return ResumeState(
        status=record.status, profile=profile, filename=record.filename, uploaded_at=record.uploaded_at, data=data,
        dropped=dropped, years_experience=years_of_experience(data.roles),
    )


def _resume_changed(db: Session, profile: Profile) -> None:
    """The resume feeds the profile and the gap analysis: both need confirming again."""
    profile.confirmed = False
    _unconfirm_gaps(db, profile)


def save_resume_draft(
    db: Session, user_id: str, *, filename: str, stored_path: str, content_type: str, size: int, text: str,
    draft: ResumeDraft,
) -> ResumeState:
    """A new upload replaces the old one and waits for review; nothing downstream uses it yet."""
    profile = _ensure_profile(db, user_id)
    record = db.get(Resume, user_id)
    if record is None:
        record = Resume(user_id=user_id)
        db.add(record)
    record.filename, record.stored_path, record.content_type, record.size = filename, stored_path, content_type, size
    record.text = text
    record.draft = draft.model_dump()
    record.data = None
    record.status = "review"
    record.uploaded_at = _now()
    profile.resume_skipped = False
    _resume_changed(db, profile)
    db.add(AgentOutput(user_id=user_id, agent="resume_parser", output={"filename": filename, "draft": record.draft}))
    db.commit()
    return get_resume_state(db, user_id)


def save_reviewed_resume(db: Session, user_id: str, data: ResumeData, prefill: dict) -> ResumeState:
    """Save what the user reviewed. Profile fields that are empty or still came from the resume are
    filled from it (marked "resume"); values the user entered are kept."""
    record = db.get(Resume, user_id)
    if record is None:
        raise NotReady("Upload a resume first.")
    record.data = data.model_dump()
    record.draft = None
    record.status = "reviewed"
    profile = _ensure_profile(db, user_id)
    sources = profile.field_sources or {}
    updates = {f: v for f, v in prefill.items() if getattr(profile, f) in (None, "") or sources.get(f) == "resume"}
    db.commit()
    apply_updates(db, user_id, updates, source="resume")  # a value that fails validation is simply not filled
    _resume_changed(db, profile)
    db.commit()
    return get_resume_state(db, user_id)


def delete_resume(db: Session, user_id: str) -> None:
    """Remove the resume row. Values it filled stay in the profile but are no longer labelled as from it."""
    record = db.get(Resume, user_id)
    if record is None:
        return
    db.delete(record)
    profile = _ensure_profile(db, user_id)
    profile.field_sources = {f: s for f, s in (profile.field_sources or {}).items() if s != "resume"}
    _resume_changed(db, profile)
    db.commit()


# --- Skill-gap analysis -------------------------------------------------------------


def _unconfirm_gaps(db: Session, profile: Profile) -> None:
    """A profile edit means the confirmed skills may no longer apply."""
    record = db.get(GapAnalysisRecord, profile.user_id)
    if record is not None:
        record.confirmed = False
    profile.inferred_skills = None


# The profile fields the gap analysis reads; with the reviewed resume they form its snapshot.
ANALYSIS_FIELDS = [
    "current_role", "target_role", "years_experience", "domain", "hours_per_week", "capabilities", "additional_context",
]


def reviewed_resume(db: Session, user_id: str) -> dict | None:
    """The user's reviewed resume data. A draft awaiting review is never used by later steps."""
    resume = db.get(Resume, user_id)
    return resume.data if resume is not None and resume.status == "reviewed" else None


def gap_inputs(db: Session, user_id: str, profile: ProfileOut) -> dict:
    """What a gap analysis is based on; the analysis is stale when this changes."""
    return {**{f: getattr(profile, f) for f in ANALYSIS_FIELDS}, "resume": reviewed_resume(db, user_id)}


def get_gap_state(db: Session, user_id: str) -> GapState:
    profile = get_profile(db, user_id)
    record = db.get(GapAnalysisRecord, user_id)
    if record is None:
        return GapState(status="none", profile=profile)
    try:
        analysis = GapAnalysis.model_validate(record.analysis)
    except ValidationError:  # saved before the current limits (e.g. more than MAX_GAPS gaps): analyze again
        return GapState(status="none", profile=profile)
    return GapState(
        status="ready",
        profile=profile,
        analysis=analysis,
        corrections=[Correction.model_validate(c) for c in record.corrections],
        confirmed=record.confirmed,
        stale=record.profile_snapshot != gap_inputs(db, user_id, profile),
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


def update_gap_analysis(db: Session, user_id: str, analysis: GapAnalysis, corrections: list[Correction]) -> GapState:
    """Save the user's direct edits (Skill Analysis buttons). The snapshot stays: the edits do not change
    what the analysis is based on, but the skills must be confirmed again."""
    record = db.get(GapAnalysisRecord, user_id)
    record.analysis = analysis.model_dump()
    record.corrections = [c.model_dump() for c in corrections]
    _unconfirm_gaps(db, _ensure_profile(db, user_id))
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
        ai_level=profile.ai_level, domain=profile.domain, hours_per_week=profile.hours_per_week,
        preferences=profile.learning_preferences or [],
        free_only=(profile.constraints or {}).get("budget") == "free_only",
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
    common = {
        "profile": gap_state.profile, "gaps_confirmed": ready, "progress": get_progress(db, user_id),
        "free_only": (gap_state.profile.constraints or {}).get("budget") == "free_only",
    }
    if record is None:
        return ResourceState(status="none", **common)
    snapshot = _resource_snapshot(gap_state)
    approval = db.get(ApprovedListRecord, user_id)
    resources = ResourceList.model_validate(record.items)
    listed = [r.resource.id for g in resources.gaps for r in g.resources]
    approved_ids = [r["resource"]["id"] for r in approval.items["resources"]] if approval else None
    return ResourceState(
        status="ready",
        **common,
        resources=resources,
        stale=not ready or record.snapshot != snapshot,
        approved_ids=approved_ids,
        # Approval covers the whole list, so a refined list no longer matches it.
        approval_stale=approval is not None and (not ready or approval.snapshot != snapshot or approved_ids != listed),
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


# --- Resource progress (Save / Start / Complete) -----------------------------------


def get_progress(db: Session, user_id: str) -> list[ResourceProgressOut]:
    rows = db.query(ResourceProgress).filter_by(user_id=user_id).order_by(ResourceProgress.updated_at.desc()).all()
    return [
        ResourceProgressOut(resource=Resource.model_validate(r.resource), saved=r.saved, status=r.status,
                            started_at=r.started_at, completed_at=r.completed_at)
        for r in rows
    ]


def set_progress(db: Session, user_id: str, resource: Resource, saved: bool | None, status: str | None) -> None:
    """Record one click. The resource comes from the server's own list (or the existing row), never the
    browser. Started and completed times are kept for later progress reviews."""
    row = db.get(ResourceProgress, (user_id, resource.id))
    if row is None:
        row = ResourceProgress(user_id=user_id, resource_id=resource.id, saved=False, status="not_started")
        db.add(row)
    row.resource = resource.model_dump(mode="json")
    if saved is not None:
        row.saved = saved
    if status is not None and status != row.status:
        row.status = status
        if status == "not_started":
            row.started_at = row.completed_at = None
        elif status == "started":
            row.started_at, row.completed_at = _now(), None
        else:
            row.started_at = row.started_at or _now()
            row.completed_at = _now()
    row.updated_at = _now()
    if not row.saved and row.status == "not_started":
        if row in db.new:
            db.expunge(row)
        else:
            db.delete(row)
    db.commit()


# --- Web search cache (shared across users, no user data) ----------------------------


def _utc_naive(value: datetime) -> datetime:
    """SQLite returns naive datetimes; compare everything as naive UTC."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def get_cached_search(db: Session, key: tuple[str, str, str], max_age: timedelta) -> list[Candidate] | None:
    """Cached first-pass web results for (skill, level, domain), or None when missing or older than max_age."""
    skill, level, domain = key
    record = db.query(WebSearchCache).filter_by(skill=skill, level=level, domain=domain).one_or_none()
    if record is None or _utc_naive(record.created_at) < _utc_naive(_now()) - max_age:
        return None
    return [Candidate.model_validate(c) for c in record.results]


def save_cached_search(db: Session, key: tuple[str, str, str], candidates: list[Candidate]) -> None:
    skill, level, domain = key
    record = db.query(WebSearchCache).filter_by(skill=skill, level=level, domain=domain).one_or_none()
    if record is None:
        record = WebSearchCache(skill=skill, level=level, domain=domain)
        db.add(record)
    record.results = [c.model_dump(mode="json") for c in candidates]
    record.created_at = _now()
    db.commit()


# --- Approved list ------------------------------------------------------------------
# The contract between course search and the scheduler: the refinement graph calls
# save_approved_list when the user approves, and the scheduler only ever reads get_approved_list.


def get_approved_list(db: Session, user_id: str) -> ApprovedList | None:
    """The user's approved resources, or None if nothing is approved or the gaps or profile
    changed since the approval."""
    gap_state = get_gap_state(db, user_id)
    record = db.get(ApprovedListRecord, user_id)
    if record is None or not _gaps_ready(gap_state) or record.snapshot != _resource_snapshot(gap_state):
        return None
    return ApprovedList.model_validate(record.items)


def save_approved_list(db: Session, user_id: str, approved: ApprovedList, gap_state: GapState, via: str) -> None:
    items = approved.model_dump(mode="json")
    record = db.get(ApprovedListRecord, user_id)
    previous = {r["resource"]["id"] for r in record.items["resources"]} if record is not None else set()
    if record is None:
        record = ApprovedListRecord(user_id=user_id)
        db.add(record)
    record.items = items
    record.snapshot = _resource_snapshot(gap_state)
    record.approved_via = via
    db.add(AgentOutput(user_id=user_id, agent="resource_approval", output={"via": via, "approved": items}))
    _record_web_candidates(db, approved, previous)
    db.commit()


def _record_web_candidates(db: Session, approved: ApprovedList, previous: set[str]) -> None:
    """Keep approved web and YouTube resources as knowledge-base candidates. Re-approving a list counts a
    resource again only if the user's previous approval did not include it."""
    for item in approved.resources:
        if item.source == "knowledge_base":
            continue
        rid = item.resource.id
        candidate = db.get(WebResourceCandidate, rid)
        if candidate is None:
            candidate = WebResourceCandidate(resource_id=rid, gaps=[], approvals=0, first_approved_at=_now())
            db.add(candidate)
        candidate.resource = item.resource.model_dump(mode="json")
        candidate.gaps = list(dict.fromkeys([*candidate.gaps, *item.gaps]))
        candidate.last_approved_at = _now()
        if rid not in previous:
            candidate.approvals += 1


def build_approved_list(resources: ResourceList) -> ApprovedList:
    """Every resource on the list, in list order. The approved resources (and their links) always
    come from the server's own list, never from the browser or a model."""
    items = [
        ApprovedResource(resource=r.resource, gaps=[g.gap.skill, *r.also_covers], priority=g.gap.priority, source=r.source)
        for g in resources.gaps
        for r in g.resources
    ]
    if not items:
        raise ValidationFailed({"resources": "Your list is empty. Add at least one resource before approving."})
    return ApprovedList(resources=items)


# --- Roadmap (scheduler) ------------------------------------------------------------


# The profile fields the scheduler reads.
SCHEDULER_FIELDS = ["current_role", "target_role", "domain", "hours_per_week", "capabilities", "ai_level"]


def roadmap_snapshot(profile: ProfileOut, approved: ApprovedList) -> dict:
    """The inputs a roadmap depends on; the roadmap is stale when these change."""
    return {"approved": approved.model_dump(mode="json"), "profile": {f: getattr(profile, f) for f in SCHEDULER_FIELDS}}


def get_roadmap_state(db: Session, user_id: str) -> RoadmapState:
    profile = get_profile(db, user_id)
    approved = get_approved_list(db, user_id)
    record = db.get(RoadmapRecord, user_id)
    if record is None:
        return RoadmapState(status="none", profile=profile, list_approved=approved is not None)
    return RoadmapState(
        status="ready",
        profile=profile,
        list_approved=approved is not None,
        roadmap=Roadmap.model_validate(record.roadmap),
        stale=approved is None or record.snapshot != roadmap_snapshot(profile, approved),
    )


def save_roadmap(db: Session, user_id: str, roadmap: Roadmap, snapshot: dict, log: bool = True) -> RoadmapState:
    """Replace the user's roadmap. log=False for a plan whose text is still being written (update_roadmap logs
    the finished one)."""
    data = roadmap.model_dump(mode="json")
    record = db.get(RoadmapRecord, user_id)
    if record is None:
        record = RoadmapRecord(user_id=user_id)
        db.add(record)
    record.roadmap = data
    record.snapshot = snapshot
    if log:
        db.add(AgentOutput(user_id=user_id, agent="scheduler", output={"input": snapshot, "roadmap": data}))
    db.commit()
    return get_roadmap_state(db, user_id)


def update_roadmap(db: Session, user_id: str, roadmap: Roadmap, log_snapshot: dict | None = None) -> RoadmapState | None:
    """Save new text into the existing roadmap (snapshot unchanged); None if it was deleted meanwhile ("Start
    over"). With log_snapshot, the finished roadmap is logged to agent_outputs."""
    record = db.get(RoadmapRecord, user_id)
    if record is None:
        return None
    data = roadmap.model_dump(mode="json")
    record.roadmap = data
    if log_snapshot is not None:
        db.add(AgentOutput(user_id=user_id, agent="scheduler", output={"input": log_snapshot, "roadmap": data}))
    db.commit()
    return get_roadmap_state(db, user_id)
