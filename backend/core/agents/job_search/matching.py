"""Match Score and everything else about a job that is a number or a fact, in plain Python (no DB, no LLM).

    score = round(100 * covered / required)

A required skill is covered when the assessment mapped it to one of the user's skills ("have"), or to a plan
gap ("in_plan") that the user has since marked completed on Progress Review. The score is worked out on
every read, so it rises as the user reports progress without a new search. The mapping itself comes from
the assessment model, but check() only accepts names that are on the user's own lists; when the model's
reply can't be used, fallback_matches() maps by name alone.
"""
import re

from core.agents.intake.validation import CAPABILITY_AREAS
from core.agents.job_search.schemas import Assessments, Job, JobView, MissingSkill, SkillMatch

LINK = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)
NUMBERS = re.compile(r"\d+\s*%|\bscore\b|\bpercent\b", re.IGNORECASE)
MAX_PROBLEMS = 15


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def _words(text: str) -> str:
    return f" {' '.join(re.findall(r'[a-z0-9+#]+', text.lower()))} "


# --- the user's side ------------------------------------------------------------------

STRONG_LEVELS = {"Intermediate", "Experienced"}


def capability_skills(capabilities: dict[str, str]) -> list[str]:
    """The capability areas the user rated Intermediate or Experienced, by their labels ("Python", "Cloud")."""
    return [label for key, label in CAPABILITY_AREAS.items() if capabilities.get(key) in STRONG_LEVELS]


def user_skills(strengths: list[str], completed_gaps: list[str], capabilities: dict[str, str]) -> list[str]:
    """What the user has today: confirmed strengths, plan gaps marked completed, and capability areas rated
    Intermediate or Experienced. De-duplicated, in that order."""
    found = [*strengths, *completed_gaps, *capability_skills(capabilities)]
    seen, unique = set(), []
    for s in found:
        if norm(s) not in seen:
            seen.add(norm(s))
            unique.append(s)
    return unique


# --- checking the assessment ------------------------------------------------------------


def check(result: Assessments, jobs: list[Job], skills: list[str], plan: list[str]) -> list[str]:
    """Problems with the model's mapping; empty means it can be used as is."""
    problems = []
    by_id = {j.id: j for j in jobs}
    skill_names, plan_names = {norm(s) for s in skills}, {norm(g) for g in plan}
    seen_jobs = set()
    for a in result.jobs:
        job = by_id.get(a.job_id)
        if job is None:
            problems.append(f'"{a.job_id}" is not one of the job ids.')
            continue
        seen_jobs.add(a.job_id)
        required = [norm(r) for r in job.required_skills]
        mapped = [norm(m.required) for m in a.matches]
        if sorted(mapped) != sorted(required):
            problems.append(f'{a.job_id}: map each required skill exactly once, named as in required_skills: '
                            f'{job.required_skills}.')
        for m in a.matches:
            if m.have and m.in_plan:
                problems.append(f'{a.job_id}: "{m.required}" has both have and in_plan; set at most one.')
            if m.have and norm(m.have) not in skill_names:
                problems.append(f'{a.job_id}: "{m.have}" is not one of the person\'s skills; copy one exactly or '
                                'leave have empty.')
            if m.in_plan and norm(m.in_plan) not in plan_names:
                problems.append(f'{a.job_id}: "{m.in_plan}" is not one of the plan gaps; copy one exactly or leave '
                                'in_plan empty.')
        if LINK.search(a.explanation) or NUMBERS.search(a.explanation):
            problems.append(f"{a.job_id}: the explanation must not contain links, percentages or scores.")
    for job in jobs:
        if job.id not in seen_jobs:
            problems.append(f"{job.id} is missing; assess every job.")
    return problems[:MAX_PROBLEMS]


def _canonical(name: str | None, names: list[str]) -> str | None:
    """The user's own spelling of a name the model copied (matching ignores case and spacing)."""
    if not name:
        return None
    return next((n for n in names if norm(n) == norm(name)), None)


def apply(job: Job, matches: list[SkillMatch], explanation: str, skills: list[str], plan: list[str]) -> Job:
    """Copy a checked mapping into the job, in the order of its required skills and the user's spelling."""
    by_required = {norm(m.required): m for m in matches}
    job.matches = [
        SkillMatch(required=r, have=_canonical(by_required[norm(r)].have, skills),
                   in_plan=_canonical(by_required[norm(r)].in_plan, plan))
        for r in job.required_skills
    ]
    job.explanation, job.explained_by = explanation, "ai"
    return job


def _covers(mine: str, required: str) -> bool:
    a, b = _words(mine), _words(required)
    return a.strip() != "" and b.strip() != "" and (a in b or b in a)


def fallback_matches(job: Job, skills: list[str], plan: list[str]) -> Job:
    """Name-only mapping when the AI's can't be used: a required skill matches a skill or plan gap whose words
    contain it (or the other way round)."""
    job.matches = [
        SkillMatch(
            required=r,
            have=next((s for s in skills if _covers(s, r)), None),
            in_plan=None if any(_covers(s, r) for s in skills) else next((g for g in plan if _covers(g, r)), None),
        )
        for r in job.required_skills
    ]
    have = [m.required for m in job.matches if m.have]
    job.explanation = (
        f"Matched by name only: you have {', '.join(have)}." if have
        else "Matched by name only: none of the required skills matches a skill on your profile by name."
    )
    job.explained_by = "default"
    return job


# --- the score, on every read -----------------------------------------------------------


def view(job: Job, completed_gaps: set[str], phase_of_gap: dict[str, int], saved=False, applied=False,
         applied_at=None) -> JobView:
    """Score and have / missing lists with today's progress. `completed_gaps` and `phase_of_gap` use norm()."""
    have, missing = [], []
    for m in job.matches or [SkillMatch(required=r) for r in job.required_skills]:
        if m.have or (m.in_plan and norm(m.in_plan) in completed_gaps):
            have.append(m.required)
        else:
            missing.append(MissingSkill(skill=m.required, in_plan=m.in_plan,
                                        phase=phase_of_gap.get(norm(m.in_plan)) if m.in_plan else None))
    total = len(job.required_skills)
    return JobView(job=job, score=round(100 * len(have) / total) if total else 0, have=have, missing=missing,
                   saved=saved, applied=applied, applied_at=applied_at)


# --- salary -----------------------------------------------------------------------------

AMOUNT = re.compile(r"(\d{1,3}(?:[,.  ]\d{3})+(?!\d)|\d+(?:\.\d+)?)\s*([kK])?")
GROUPED = re.compile(r"^\d{1,3}(?:[,.  ]\d{3})+$")  # 120,000 / 120.000 / 120 000
HOURLY = re.compile(r"/\s*h(ou)?r|per hour|hourly|an hour", re.IGNORECASE)
MIN_ANNUAL = 1000  # smaller numbers without "k" are not annual salaries


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """(min, max) annual amount from the posting's salary text, in its own currency; (None, None) when it states
    none or only an hourly rate."""
    if not text or HOURLY.search(text):
        return None, None
    amounts = []
    for number, k in AMOUNT.findall(text):
        value = float(re.sub(r"[,.  ]", "", number) if GROUPED.match(number) else number)
        if k:
            value *= 1000
        if value >= MIN_ANNUAL:
            amounts.append(int(value))
    if not amounts:
        return None, None
    return min(amounts), max(amounts)
