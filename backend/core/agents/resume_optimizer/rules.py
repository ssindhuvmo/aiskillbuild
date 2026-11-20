"""Checks on the model's TailoredText (pure). An empty list means it can be used.

The model never writes an employer, title, date, degree or certification: those are copied from the resume by
reference. These checks cover the rest: every reference must point at Evidence, every skill must be one the
user can claim, every number in the text must already be in the user's own data (no invented metrics or
years; "[...]" placeholders are for the user to fill in), and "To add" may only name what is still pending.
"""
import json
import re

from core.agents.job_search.matching import norm
from core.agents.job_search.schemas import Job
from core.agents.resume_optimizer.schemas import Evidence, TailoredText

LINK = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\[[^\[\]]{1,80}\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MAX_PROBLEMS = 15


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def source_numbers(e: Evidence) -> set[str]:
    """Every number in the user's own data: the resume, the completed projects and courses, years of
    experience."""
    data = [e.resume.model_dump(), [p.project.model_dump() for p in e.projects],
            [c.model_dump() for c in e.courses], e.years_experience, e.current_role, e.target_role]
    return numbers(json.dumps(data, ensure_ascii=False))


def free_text(t: TailoredText) -> list[tuple[str, str]]:
    """(where, text) for everything the model wrote in its own words."""
    found = [("headline", t.headline), ("summary", t.summary)]
    for r in t.roles:
        found += [(f"role {r.ref}", h) for h in r.highlights]
    for p in t.projects:
        found += [(f"project {p.ref}", b) for b in p.bullets]
    return found


def _words(text: str) -> str:
    return f" {' '.join(re.findall(r'[a-z0-9+#]+', text.lower()))} "


def contains(text: str, phrase: str) -> bool:
    w = _words(phrase)
    return w.strip() != "" and w in _words(text)


def job_text(job: Job) -> str:
    return " ".join([job.title, job.summary, *job.required_skills])


def check(t: TailoredText, e: Evidence, job: Job) -> list[str]:
    problems: list[str] = []
    roles = e.resume.roles

    refs = [r.ref for r in t.roles]
    if sorted(refs) != list(range(len(roles))):
        problems.append(f"Include every role exactly once, by its ref (0 to {len(roles) - 1})." if roles
                        else "There are no roles in the resume: leave roles empty.")

    allowed = {norm(s) for s in e.skills}
    for s in t.skills:
        if norm(s) not in allowed:
            problems.append(f'Skill "{s}" is not one the person can claim; use only names from allowed_skills.')
    if len({norm(s) for s in t.skills}) != len(t.skills):
        problems.append("List each skill once.")

    project_ids = {p.id for p in e.projects}
    if len({p.ref for p in t.projects}) != len(t.projects):
        problems.append("List each project once.")
    for p in t.projects:
        if p.ref not in project_ids:
            problems.append(f'Project "{p.ref}" is not a completed project; use only ids from completed_projects.')
    course_ids = {c.id for c in e.courses}
    for c in t.courses:
        if c not in course_ids:
            problems.append(f'Course "{c}" is not a completed course; use only ids from completed_courses.')

    allowed_numbers = source_numbers(e)
    for where, text in free_text(t):
        if LINK.search(text):
            problems.append(f"{where}: do not write URLs or links.")
        invented = numbers(PLACEHOLDER.sub("", text)) - allowed_numbers
        if invented:
            problems.append(f"{where}: {', '.join(sorted(invented))} is not in the person's data. Do not invent "
                            'numbers, years or metrics; write a placeholder like "[add your scale]" instead.')
    employers = [r.employer for r in roles]
    if not any(norm(job.company) == norm(x) for x in employers):
        for where, text in free_text(t):
            if contains(text, job.company):
                problems.append(f"{where}: do not name {job.company}; the person has not worked there.")

    tailored = " ".join([text for _, text in free_text(t)] + t.skills)
    for k in t.keywords:
        if not contains(job_text(job), k):
            problems.append(f'Keyword "{k}" is not in the posting; copy keywords from the posting.')
        elif not contains(tailored, k):
            problems.append(f'Keyword "{k}" does not appear in the tailored resume; list only keywords you used.')

    pending_skills = {norm(s) for s in [*e.pending_gaps, *job.required_skills]}
    claimed = allowed
    pending_projects = {norm(p.title) for p in e.pending_projects}
    for a in t.to_add:
        if a.kind == "skill" and (norm(a.name) not in pending_skills or norm(a.name) in claimed):
            problems.append(f'To add "{a.name}": name a plan gap or required skill the person does not have yet.')
        if a.kind == "project" and norm(a.name) not in pending_projects:
            problems.append(f'To add "{a.name}": name an unfinished roadmap project by its title.')
        if LINK.search(a.note):
            problems.append(f'To add "{a.name}": do not write URLs or links.')
    return problems[:MAX_PROBLEMS]
