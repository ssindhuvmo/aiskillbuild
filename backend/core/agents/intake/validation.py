"""Deterministic validation for the five intake inputs. The LLM never bypasses this."""
from core.config import load_domains

AI_EXPERIENCE = ["None", "Beginner", "Intermediate", "Experienced"]
FIELDS = ["current_role", "target_role", "ai_experience", "domain", "hours_per_week"]
VAGUE_ROLES = {"", "engineer", "developer", "tech", "it", "job", "work", "something", "anything", "ai", "idk", "n/a"}


def _clean(value) -> str:
    return " ".join(str(value).split())


def validate_role(value) -> tuple[str | None, str | None]:
    v = _clean(value) if value is not None else ""
    if v.lower() in VAGUE_ROLES or len(v) < 3:
        return None, "Please give a specific role title (e.g. Backend Engineer, ML Engineer)."
    if len(v) > 100:
        return None, "That role title is too long; please shorten it."
    return v, None


def validate_ai_experience(value) -> tuple[str | None, str | None]:
    v = _clean(value) if value is not None else ""
    for option in AI_EXPERIENCE:
        if v.lower() == option.lower():
            return option, None
    return None, f"AI experience must be one of: {', '.join(AI_EXPERIENCE)}."


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
    try:
        if isinstance(value, bool):
            raise ValueError
        f = float(str(value).strip().split()[0]) if isinstance(value, str) else float(value)
    except (ValueError, TypeError, IndexError):
        return None, "Hours per week must be a number between 1 and 40."
    if f != int(f):
        return None, "Please give a whole number of hours per week (1–40)."
    h = int(f)
    if not 1 <= h <= 40:
        return None, "Hours per week must be between 1 and 40."
    return h, None


VALIDATORS = {
    "current_role": validate_role,
    "target_role": validate_role,
    "ai_experience": validate_ai_experience,
    "domain": validate_domain,
    "hours_per_week": validate_hours,
}


def validate_field(field: str, value):
    return VALIDATORS[field](value)


def missing_fields(profile: dict) -> list[str]:
    return [f for f in FIELDS if profile.get(f) in (None, "")]
