"""Deterministic validation for the Career Profile inputs and the intake steps. The LLM never
bypasses this. frontend/src/capabilities.js mirrors the option lists below."""
from core.config import load_domains

# Capability levels (BR-04). Gap targets may go one level higher (gap_analysis/schemas.py).
LEVELS = ["None", "Beginner", "Intermediate", "Experienced"]
TARGET_LEVELS = [*LEVELS, "Expert"]
CAPABILITY_AREAS = {
    "python": "Python",
    "data_sql": "Data and SQL",
    "machine_learning": "Machine Learning",
    "ai_llms": "AI / LLMs",
    "cloud": "Cloud",
}
PREFERENCES = {
    "free_courses": "Free courses",
    "paid_courses": "Paid courses",
    "video": "YouTube / video",
    "articles": "Articles",
    "books": "Books",
    "projects": "Hands-on projects",
    "certifications": "Certifications",
}
DEFAULT_PREFERENCES = ["free_courses", "video", "articles", "projects"]
BUDGETS = ["free_only", "monthly"]
CONSTRAINT_FLAGS = ["weekends_only", "keep_current_job", "remote_only"]
# Labels for the report (mirrored in frontend/src/capabilities.js).
CONSTRAINT_LABELS = {"weekends_only": "Weekends only", "keep_current_job": "Must stay in current job", "remote_only": "Remote only"}
MAX_MONTHLY_BUDGET = 100_000
MAX_CONTEXT = 2000

# Profile fields the user (or the intake model) can set. resume_skipped is set through `skip`.
FIELDS = [
    "current_role", "target_role", "years_experience", "domain", "hours_per_week", "capabilities",
    "learning_preferences", "constraints", "additional_context",
]
# Needed before the profile can be confirmed.
REQUIRED = ["target_role", "current_role", "years_experience", "domain", "hours_per_week", "capabilities"]
# Optional steps the user can skip; skipping preferences applies DEFAULT_PREFERENCES.
SKIPPABLE = ["resume", "preferences", "constraints", "context"]

# The intake steps in the order the chat asks them (SPEC.md section 2).
STEPS = {
    "goal": "Career goal",
    "resume": "Resume",
    "background": "Current role and experience",
    "hours": "Weekly learning hours",
    "capabilities": "Capability assessment",
    "preferences": "Learning preferences",
    "constraints": "Budget and constraints",
    "context": "Additional context",
}

VAGUE_ROLES = {"", "engineer", "developer", "tech", "it", "job", "work", "something", "anything", "ai", "idk", "n/a"}


def _clean(value) -> str:
    return " ".join(str(value).split())


def _whole_number(value) -> int | None:
    try:
        if isinstance(value, bool):
            raise ValueError
        f = float(str(value).strip().split()[0]) if isinstance(value, str) else float(value)
    except (ValueError, TypeError, IndexError):
        return None
    return int(f) if f == int(f) else None


def validate_role(value) -> tuple[str | None, str | None]:
    v = _clean(value) if value is not None else ""
    if v.lower() in VAGUE_ROLES or len(v) < 3:
        return None, "Please give a specific role title (e.g. Backend Engineer, ML Engineer)."
    if len(v) > 100:
        return None, "That role title is too long; please shorten it."
    return v, None


def validate_domain(value) -> tuple[str | None, str | None]:
    v = _clean(value) if value is not None else ""
    if not v:
        return None, "Please tell me the industry you work in today."
    for d in load_domains():
        if v.lower() == d.lower():
            if d == "Other":
                return None, "Please name your industry (for 'Other', free text is needed)."
            return d, None
    # Free text is accepted as "Other: <text>" style custom domain.
    if len(v) > 100:
        return None, "That industry name is too long; please shorten it."
    return v, None


def validate_hours(value) -> tuple[int | None, str | None]:
    h = _whole_number(value)
    if h is None:
        return None, "Hours per week must be a whole number between 1 and 40."
    if not 1 <= h <= 40:
        return None, "Hours per week must be between 1 and 40."
    return h, None


def validate_years(value) -> tuple[int | None, str | None]:
    y = _whole_number(value)
    if y is None or not 0 <= y <= 50:
        return None, "Years of experience must be a whole number between 0 and 50."
    return y, None


def _level(value, options: list[str]) -> str | None:
    v = _clean(value).lower() if value is not None else ""
    return next((o for o in options if o.lower() == v), None)


def validate_capabilities(value) -> tuple[dict | None, str | None]:
    """A partial {area: level} update; it is merged into the saved ratings."""
    if not isinstance(value, dict) or not value:
        return None, f"Rate at least one area: {', '.join(CAPABILITY_AREAS.values())}."
    out = {}
    for area, raw in value.items():
        if area not in CAPABILITY_AREAS:
            return None, f"Unknown capability area: {area}."
        level = _level(raw, LEVELS)
        if level is None:
            return None, f"{CAPABILITY_AREAS[area]} must be one of: {', '.join(LEVELS)}."
        out[area] = level
    return out, None


def validate_preferences(value) -> tuple[list | None, str | None]:
    if not isinstance(value, list) or not value:
        return None, "Pick at least one learning preference, or skip to use the defaults."
    unknown = [p for p in value if p not in PREFERENCES]
    if unknown:
        return None, f"Unknown learning preference: {', '.join(map(str, unknown))}."
    return [p for p in PREFERENCES if p in value], None  # fixed order, no duplicates


def validate_constraints(value) -> tuple[dict | None, str | None]:
    """{} means the user has no constraints."""
    if not isinstance(value, dict):
        return None, "Constraints must be a set of options."
    unknown = set(value) - {"budget", "monthly_budget", "other", *CONSTRAINT_FLAGS}
    if unknown:
        return None, f"Unknown constraint: {', '.join(sorted(unknown))}."
    out: dict = {}
    budget = value.get("budget")
    if budget not in (None, *BUDGETS):
        return None, "Budget must be 'free only' or a monthly amount."
    if budget == "monthly":
        amount = _whole_number(value.get("monthly_budget"))
        if amount is None or not 1 <= amount <= MAX_MONTHLY_BUDGET:
            return None, f"Give the monthly budget as a whole number between 1 and {MAX_MONTHLY_BUDGET}."
        out["monthly_budget"] = amount
    if budget:
        out["budget"] = budget
    for flag in CONSTRAINT_FLAGS:
        if value.get(flag):
            out[flag] = True
    other = _clean(value.get("other") or "")
    if len(other) > 300:
        return None, "Please keep other constraints under 300 characters."
    if other:
        out["other"] = other
    return out, None


def validate_context(value) -> tuple[str | None, str | None]:
    v = str(value).strip() if value is not None else ""
    if len(v) > MAX_CONTEXT:
        return None, f"Please keep additional context under {MAX_CONTEXT} characters."
    return v, None


VALIDATORS = {
    "current_role": validate_role,
    "target_role": validate_role,
    "years_experience": validate_years,
    "domain": validate_domain,
    "hours_per_week": validate_hours,
    "capabilities": validate_capabilities,
    "learning_preferences": validate_preferences,
    "constraints": validate_constraints,
    "additional_context": validate_context,
}


def validate_field(field: str, value):
    return VALIDATORS[field](value)


def check_combination(preferences: list | None, constraints: dict | None) -> str | None:
    """Rules across fields; returns a problem or None."""
    if (constraints or {}).get("budget") == "free_only" and "paid_courses" in (preferences or []):
        return "Your budget is free only, so paid courses can't be a preference. Remove one of them."
    return None


def capabilities_complete(capabilities: dict | None) -> bool:
    return all((capabilities or {}).get(a) for a in CAPABILITY_AREAS)


def ai_level(capabilities: dict | None) -> str | None:
    """The overall AI level that ranking and the scheduler use: the mean of the Machine Learning and
    AI / LLMs ratings, rounded down. None until both are rated."""
    caps = capabilities or {}
    ml, llm = caps.get("machine_learning"), caps.get("ai_llms")
    if ml not in LEVELS or llm not in LEVELS:
        return None
    return LEVELS[(LEVELS.index(ml) + LEVELS.index(llm)) // 2]


def missing_fields(profile: dict) -> list[str]:
    """Required fields still missing; empty means the profile can be confirmed."""
    return [
        f for f in REQUIRED
        if (not capabilities_complete(profile.get(f)) if f == "capabilities" else profile.get(f) in (None, ""))
    ]


def _step_done(step: str, p: dict) -> bool:
    if step == "goal":
        return bool(p.get("target_role"))
    if step == "resume":
        return p.get("resume_status") == "reviewed" or bool(p.get("resume_skipped"))
    if step == "background":
        return all(p.get(f) not in (None, "") for f in ("current_role", "years_experience", "domain"))
    if step == "hours":
        return p.get("hours_per_week") is not None
    if step == "capabilities":
        return capabilities_complete(p.get("capabilities"))
    if step == "preferences":
        return p.get("learning_preferences") is not None
    if step == "constraints":
        return p.get("constraints") is not None
    return p.get("additional_context") is not None  # context


def steps(profile: dict, help_choose: bool = False) -> list[dict]:
    """The steps in asking order, each with whether it is done. "Help me choose" moves the goal
    after the background, so the suggested roles can draw on it."""
    order = list(STEPS)
    if help_choose and not _step_done("goal", profile):
        order.remove("goal")
        order.insert(order.index("background") + 1, "goal")
    return [{"id": s, "label": STEPS[s], "done": _step_done(s, profile)} for s in order]


def next_step(profile: dict, help_choose: bool = False) -> str | None:
    return next((s["id"] for s in steps(profile, help_choose) if not s["done"]), None)
