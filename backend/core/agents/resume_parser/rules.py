"""Plain-Python checks and numbers for resume data (no DB, no LLM). Everything the parser returns
must be found in the resume text, and the years of experience are calculated here, never by the LLM."""
import re
import unicodedata
from datetime import date

from core.agents.resume_parser.schemas import ResumeData, Role

EARLIEST_YEAR = 1950


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip(" .,;:")


def _month(value: str, end: bool = False) -> int:
    """Months since year 0. A bare year is its first month, or its last when it ends a role."""
    year = int(value[:4])
    month = int(value[5:7]) if len(value) > 4 else (12 if end else 1)
    return year * 12 + month - 1


def _now(today: date) -> int:
    return today.year * 12 + today.month - 1


def _role_dates(role: Role, today: date) -> str | None:
    """A problem with the role's dates, or None."""
    now = _now(today)
    if int(role.start[:4]) < EARLIEST_YEAR:
        return f"starts before {EARLIEST_YEAR}"
    if _month(role.start) > now:
        return "starts in the future"
    if role.end is not None:
        if _month(role.end) > now:
            return "ends in the future (use null for a current role)"
        if _month(role.start) > _month(role.end, end=True):
            return "ends before it starts"
    return None


def _year_problem(year: int | None, latest: int) -> str | None:
    if year is not None and not EARLIEST_YEAR <= year <= latest:
        return f"has an invalid year ({year})"
    return None


def issues(data: ResumeData, text: str | None, today: date | None = None) -> list[tuple[str, int, str, str]]:
    """(section, index, problem, label) for every item that fails a check. With `text`, names must
    appear in it (the parser's output); without it only the dates are checked (the user's edits)."""
    today = today or date.today()
    found = _norm(text) if text is not None else None
    missing = lambda value: found is not None and _norm(value) not in found  # noqa: E731
    out = []
    for i, skill in enumerate(data.skills):
        if missing(skill):
            out.append(("skills", i, f'Skill "{skill}" does not appear in the resume text.', f'Skill "{skill}"'))
    for i, role in enumerate(data.roles):
        label = f'Role "{role.title} at {role.employer}"'
        for field in ("title", "employer"):
            if missing(getattr(role, field)):
                out.append(("roles", i, f'{label}: the {field} "{getattr(role, field)}" does not appear in the resume text.', label))
        if problem := _role_dates(role, today):
            out.append(("roles", i, f"{label} {problem}.", label))
    for i, cert in enumerate(data.certifications):
        label = f'Certification "{cert.name}"'
        if missing(cert.name):
            out.append(("certifications", i, f"{label} does not appear in the resume text.", label))
        if problem := _year_problem(cert.year, today.year):
            out.append(("certifications", i, f"{label} {problem}.", label))
    for i, edu in enumerate(data.education):
        label = f'Education "{edu.qualification}"'
        if problem := _year_problem(edu.year, today.year + 6):  # expected graduation may be ahead
            out.append(("education", i, f"{label} {problem}.", label))
    return out


def check_rules(data: ResumeData, text: str | None = None, today: date | None = None) -> list[str]:
    """Problems as messages; empty means OK."""
    return [problem for _, _, problem, _ in issues(data, text, today)]


def filter_unverified(data: ResumeData, text: str, today: date | None = None) -> tuple[ResumeData, list[str]]:
    """Keep only the items that pass the checks. Returns (kept data, labels of what was dropped)."""
    found = issues(data, text, today)
    bad = {(section, i) for section, i, _, _ in found}
    kept = data.model_copy(update={
        section: [item for i, item in enumerate(getattr(data, section)) if (section, i) not in bad]
        for section in ("skills", "roles", "certifications", "education")
    })
    return kept, list(dict.fromkeys(label for *_, label in found))


def years_of_experience(roles: list[Role], today: date | None = None) -> int | None:
    """Whole years covered by the roles, counting overlapping roles once. None without roles."""
    today = today or date.today()
    now = _now(today)
    spans = sorted(
        (_month(r.start), min(_month(r.end, end=True), now) if r.end else now)
        for r in roles
        if _role_dates(r, today) is None
    )
    if not spans:
        return None if not roles else 0
    months, (start, end) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= end + 1:
            end = max(end, e)
        else:
            months += end - start + 1
            start, end = s, e
    months += end - start + 1
    return months // 12


def latest_role(roles: list[Role]) -> Role | None:
    """The current role (no end date) or else the one that ended last; the latest start breaks ties."""
    if not roles:
        return None
    return max(roles, key=lambda r: (r.end is None, _month(r.end, end=True) if r.end else 0, _month(r.start)))


def prefill(data: ResumeData, today: date | None = None) -> dict:
    """Profile values read from the reviewed resume: current role, years of experience, industry."""
    out = {}
    if role := latest_role(data.roles):
        out["current_role"] = role.title
    years = years_of_experience(data.roles, today)
    if years is not None:
        out["years_experience"] = years
    if data.industry:
        out["domain"] = data.industry
    return out
