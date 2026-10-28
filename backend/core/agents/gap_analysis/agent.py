"""Skill-gap analysis agent.

One structured-output call returns a GapAnalysis. Pydantic validates it and rule checks
enforce the user's corrections; a rejected attempt is retried with the problems fed back.
Transport errors (429/5xx/connection) are retried separately by the SDK client.
"""
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.gap_analysis.schemas import Correction, GapAnalysis, GapInput
from core.agents.scheduler.budget import WEEKS, budget
from core.llm import MODEL, get_client
from core.schemas import GapState

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 3
EFFORT_TOLERANCE = 1.1  # the gaps' total effort only has to fit the hour budget roughly


class GapAnalysisFailed(Exception):
    pass


class ProfileNotConfirmed(Exception):
    pass


def _norm(skill: str) -> str:
    return " ".join(skill.lower().split())


def check_rules(result: GapAnalysis, data: GapInput) -> list[str]:
    """Checks the schema cannot express. Returns problems; empty means OK."""
    problems = []
    strengths = [_norm(s.skill) for s in result.strengths]
    gaps = [_norm(g.skill) for g in result.gaps + result.later_gaps]  # a later gap is still a gap
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
    effort, limit = sum(g.effort_hours for g in result.gaps), budget(data.hours_per_week)
    if effort > limit * EFFORT_TOLERANCE:
        problems.append(
            f"The gaps total {effort} hours of effort, but the user has {limit} hours ({data.hours_per_week} per week "
            f"x {WEEKS} weeks). Move the least important gaps to later_gaps until the rest fits; do not shrink "
            "realistic estimates."
        )
    return problems


def _request(data: GapInput, problems: list[str]) -> str:
    profile = data.model_dump(exclude={"corrections"})
    corrections = [c.model_dump(exclude_none=True) for c in data.corrections]
    text = (
        f"Profile:\n{json.dumps(profile, indent=2)}\n\n"
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
            problems = ["The reply was empty or cut off."] if result is None else check_rules(result, data)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return result
    raise GapAnalysisFailed("; ".join(problems))


def run_for_user(db: Session, user_id: str, corrections: list[Correction]) -> GapState:
    """Analyze the user's confirmed profile with their corrections and save the result."""
    profile = repository.get_profile(db, user_id)  # commits, so no DB lock is held during the LLM call
    if not profile.confirmed:
        raise ProfileNotConfirmed("Confirm your profile on the Intake step first.")
    snapshot = repository.gap_inputs(db, user_id, profile)
    analysis = analyze(GapInput(**snapshot, ai_level=profile.ai_level, corrections=corrections))
    return repository.save_gap_analysis(db, user_id, analysis, corrections, snapshot)
