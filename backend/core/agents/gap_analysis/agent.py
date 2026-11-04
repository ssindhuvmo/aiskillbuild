"""Skill-gap analysis agent.

One structured-output call returns a GapAnalysis. Pydantic validates it and rule checks
enforce the user's corrections; a rejected attempt is retried with the problems fed back.
Transport errors (429/5xx/connection) are retried separately by the SDK client.
"""
import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.gap_analysis.schemas import MAX_LATER, Correction, GapAnalysis, GapInput
from core.agents.intake.validation import TARGET_LEVELS
from core.agents.scheduler.budget import WEEKS, budget
from core.llm import MODEL, get_client
from core.schemas import GapState

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 3
log = logging.getLogger(__name__)
EFFORT_TOLERANCE = 1.1  # the gaps' total effort only has to fit the hour budget roughly


class GapAnalysisFailed(Exception):
    pass


class ProfileNotConfirmed(Exception):
    pass


def _norm(skill: str) -> str:
    return " ".join(skill.lower().split())


def _words(text: str) -> str:
    """Lowercase words padded with spaces, so containment is whole-word ("go" is not in "governance")."""
    return f" {' '.join(re.findall(r'[a-z0-9+#]+', text.lower()))} "


def _resume_names(resume: dict) -> list[str]:
    """Skills, job titles, qualifications and certification names in the reviewed resume."""
    names = [*resume.get("skills", []), *(r["title"] for r in resume.get("roles", [])),
             *(e["qualification"] for e in resume.get("education", [])),
             *(c["name"] for c in resume.get("certifications", []))]
    return [w for w in map(_words, names) if w.strip()]


def _in_resume(skill: str, names: list[str]) -> bool:
    """The strength names a resume item, or is part of one ("SQL" in "SQL Server", "Python" in "Python 3")."""
    skill = _words(skill)
    return skill.strip() != "" and any(skill in n or n in skill for n in names)


def repair(result: GapAnalysis, data: GapInput) -> GapAnalysis:
    """Fix what Python can fix the way the prompt asks, instead of spending a retry on it:
    - a "resume" strength that names nothing in the resume (the model paraphrased it) becomes "assumed";
    - a target level not above the current level becomes the next level up;
    - while the gaps go over the hour budget, the least important (last) gap moves to the front of
      later_gaps, keeping at least one gap and within the later_gaps limit. Gaps the user put in the plan
      ("plan" corrections) are never moved."""
    names = _resume_names(data.resume) if data.resume else []
    for s in result.strengths:
        if s.source == "resume" and not _in_resume(s.skill, names):
            s.source = "assumed"
    for g in result.gaps + result.later_gaps:
        current = TARGET_LEVELS.index(g.current_level)
        if TARGET_LEVELS.index(g.target_level) <= current:
            g.target_level = TARGET_LEVELS[current + 1]
    limit = budget(data.hours_per_week) * EFFORT_TOLERANCE
    pinned = _skills(data, "plan")
    while sum(g.effort_hours for g in result.gaps) > limit and len(result.gaps) > 1 and len(result.later_gaps) < MAX_LATER:
        movable = [i for i, g in enumerate(result.gaps) if _norm(g.skill) not in pinned]
        if not movable:
            break
        result.later_gaps.insert(0, result.gaps.pop(movable[-1]))
    return result


def _skills(data: GapInput, kind: str) -> set[str]:
    """Normalized skills named by the user's corrections of one kind."""
    return {_norm(c.skill) for c in data.corrections if c.kind == kind and c.skill}


def check_rules(result: GapAnalysis, data: GapInput) -> list[str]:
    """Checks the schema cannot express. Returns problems; empty means OK."""
    problems = []
    names = _resume_names(data.resume) if data.resume else []
    for s in result.strengths:
        if s.source == "resume" and not data.resume:
            problems.append(f'"{s.skill}" has source "resume", but the user has no resume. Use "user" or "assumed".')
        elif s.source == "resume" and not _in_resume(s.skill, names):
            problems.append(
                f'"{s.skill}" has source "resume", but it does not match a skill, job title or certification in the '
                'resume. Name it as the resume does, or use "assumed".'
            )
    for g in result.gaps + result.later_gaps:
        if TARGET_LEVELS.index(g.target_level) <= TARGET_LEVELS.index(g.current_level):
            problems.append(f'"{g.skill}": target_level must be above current_level ({g.current_level}).')
    strengths = [_norm(s.skill) for s in result.strengths]
    planned = [_norm(g.skill) for g in result.gaps]
    gaps = planned + [_norm(g.skill) for g in result.later_gaps]  # a later gap is still a gap
    seen: set[str] = set()
    for name in strengths + gaps:
        if name in seen:
            problems.append(f'"{name}" is listed more than once; each skill must appear exactly once.')
        seen.add(name)
    for c in data.corrections:
        if not c.skill:
            continue
        skill = _norm(c.skill)
        if c.kind == "knows" and skill in gaps:
            problems.append(f'The user said they know "{c.skill}", so it must not be a gap.')
        if c.kind == "knows" and skill not in strengths:
            problems.append(f'The user said they know "{c.skill}"; list it as a strength with source "user".')
        if c.kind == "lacks" and skill in strengths:
            problems.append(f'The user said they do not have "{c.skill}", so it must not be a strength.')
        if c.kind == "not_needed" and (skill in strengths or skill in gaps):
            problems.append(
                f'The user said "{c.skill}" is not needed: leave it out of strengths, gaps and later_gaps entirely.'
            )
        if c.kind == "later" and skill in planned:
            problems.append(f'The user moved "{c.skill}" to later: put it in later_gaps, not gaps.')
        if c.kind == "plan" and skill not in planned:
            problems.append(
                f'The user put "{c.skill}" in their plan: it must be in gaps. Move less important gaps to later_gaps.'
            )
    effort, limit = sum(g.effort_hours for g in result.gaps), budget(data.hours_per_week)
    if effort > limit * EFFORT_TOLERANCE:
        problems.append(
            f"The gaps total {effort} hours of effort, but the user has {limit} hours ({data.hours_per_week} per week "
            f"x {WEEKS} weeks). Move the least important gaps to later_gaps until the rest fits; do not shrink "
            "realistic estimates."
        )
    return problems


def _request(data: GapInput, problems: list[str]) -> str:
    profile = data.model_dump(exclude={"corrections", "resume"})
    corrections = [c.model_dump(exclude_none=True, exclude={"gap", "in_plan"}) for c in data.corrections]
    # The resume is untrusted data: it stays inside its tags and its instructions are ignored.
    resume = json.dumps(data.resume, indent=2).replace("</resume>", "") if data.resume else "none (no resume uploaded)"
    text = (
        f"Profile:\n{json.dumps(profile, indent=2)}\n\n"
        f"<resume>\n{resume}\n</resume>\n\n"
        f"Hour budget for the plan: {budget(data.hours_per_week)} hours "
        f"({data.hours_per_week} per week x {WEEKS} weeks).\n\n"
        f"User corrections:\n{json.dumps(corrections, indent=2) if corrections else 'none'}"
    )
    if problems:
        text += "\n\nYour previous analysis was rejected:\n- " + "\n- ".join(problems)
        text += "\nReturn a complete, corrected analysis."
    return text


def analyze(data: GapInput) -> GapAnalysis:
    """Return a validated analysis, or raise GapAnalysisFailed after MAX_ATTEMPTS.
    LLM errors (missing key, auth, rate limit) propagate for the caller to report."""
    client = get_client()
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=8000,
                system=PROMPT,
                messages=[{"role": "user", "content": _request(data, problems)}],
                output_format=GapAnalysis,
            )
            result = response.parsed_output
            if result is None:
                problems = ["The reply was empty or cut off."]
            else:
                result = repair(result, data)
                problems = check_rules(result, data)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return result
        log.warning("Gap analysis attempt rejected: %s", "; ".join(problems))
    raise GapAnalysisFailed("; ".join(problems))


def run_for_user(db: Session, user_id: str, corrections: list[Correction]) -> GapState:
    """Analyze the user's confirmed profile with their corrections and save the result."""
    profile = repository.get_profile(db, user_id)  # commits, so no DB lock is held during the LLM call
    if not profile.confirmed:
        raise ProfileNotConfirmed("Confirm your profile on the Intake step first.")
    snapshot = repository.gap_inputs(db, user_id, profile)
    analysis = analyze(GapInput(**snapshot, ai_level=profile.ai_level, corrections=corrections))
    return repository.save_gap_analysis(db, user_id, analysis, corrections, snapshot)
