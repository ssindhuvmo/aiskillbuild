"""Transition Report agent: one structured-output call for the two narrative sections; Python does the rest.

write() asks for a ReportNarrative, checks it (no links, no percentages) and retries once with the problems
fed back. If the text still fails, or the LLM is unavailable, generate() keeps a plain default text built
from the saved analysis and roadmap (source "default", with a notice), so a report is always produced.
The routes call only check_ready, state_for_user and generate.
"""
import json
import logging
import re
from pathlib import Path

import anthropic
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.report.assemble import ReportData, build, default_narrative
from core.agents.report.schemas import ReportNarrative, ReportState
from core.llm import MODEL, LLMUnavailable, friendly_error, get_client

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 2  # one retry
MAX_TOKENS = 2000
LINK = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)
PERCENT = re.compile(r"\d\s*%|\bpercent\b|\d+\s*/\s*10\b", re.IGNORECASE)


class NotReady(Exception):
    pass


class NarrativeFailed(Exception):
    pass


def check_ready(db: Session, user_id: str) -> ReportData:
    state = repository.get_roadmap_state(db, user_id)
    if state.roadmap is None or state.stale:
        raise NotReady("Build your roadmap from your current approved resources first.")
    data = repository.report_data(db, user_id)
    if data is None:
        raise NotReady("Run your skill analysis and build your roadmap first.")
    return data


def state_for_user(db: Session, user_id: str) -> ReportState:
    record = repository.get_report_record(db, user_id)
    data = repository.report_data(db, user_id)
    can_generate = data is not None and not repository.get_roadmap_state(db, user_id).stale
    if record is None or data is None:
        return ReportState(status="none", can_generate=can_generate)
    try:
        narrative = ReportNarrative.model_validate(record.narrative)
    except ValidationError:
        return ReportState(status="none", can_generate=can_generate)
    return ReportState(
        status="ready",
        can_generate=can_generate,
        stale=record.snapshot != repository.report_snapshot(db, user_id, data),
        report=build(data, narrative, record.source, record.updated_at),
    )


def request(data: ReportData, problems: list[str] = ()) -> str:
    p = data.profile
    facts = {
        "career_goal": {"current_role": p.current_role, "target_role": p.target_role, "domain": p.domain},
        "profile": {
            "years_experience": p.years_experience, "ai_level": p.ai_level, "capabilities": p.capabilities,
            "additional_context": p.additional_context or None,
        },
        "resume": {
            "roles": [f"{r.title}, {r.employer}" for r in data.resume.roles],
            "skills": data.resume.skills,
            "certifications": [c.name for c in data.resume.certifications],
        } if data.resume else None,
        "strengths": [s.model_dump(include={"skill", "category", "source", "basis"}) for s in data.analysis.strengths],
        "gaps": [g.model_dump(include={"skill", "priority", "why_needed", "current_level", "target_level"})
                 for g in data.analysis.gaps],
        "later_gaps": [g.skill for g in data.analysis.later_gaps],
        "rationale": data.analysis.rationale,
        "phases": [
            {"phase": ph.number, "name": ph.name, "months": ph.months, "gaps": ph.gaps,
             "project": ph.project.model_dump(include={"title", "problem", "dataset"})}
            for ph in data.roadmap.phases
        ],
    }
    text = f"<facts>\n{json.dumps(facts, indent=2, ensure_ascii=False)}\n</facts>"
    if problems:
        text += "\n\nYour previous reply was rejected:\n- " + "\n- ".join(problems) + "\nReturn a corrected reply."
    return text


def check(n: ReportNarrative) -> list[str]:
    problems = []
    for name in ("career_fit", "strategy"):
        value = getattr(n, name)
        if LINK.search(value):
            problems.append(f"{name}: do not write URLs or links.")
        if PERCENT.search(value):
            problems.append(f"{name}: do not give scores, ratings or percentages.")
    return problems


def write(data: ReportData) -> ReportNarrative:
    """A checked narrative, or NarrativeFailed after MAX_ATTEMPTS. LLM errors propagate."""
    client = get_client()
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=PROMPT,
                messages=[{"role": "user", "content": request(data, problems)}],
                output_format=ReportNarrative,
            )
            result = response.parsed_output
            problems = ["The reply was empty or cut off."] if result is None else check(result)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return result
        log.warning("Report narrative attempt %d of %d rejected: %s", attempt, MAX_ATTEMPTS, "; ".join(problems))
    raise NarrativeFailed("; ".join(problems))


def generate(db: Session, user_id: str) -> ReportState:
    """Write (or rewrite) the report. Raises NotReady; never fails because of the LLM."""
    data = check_ready(db, user_id)
    notice = None
    try:
        narrative, source = write(data), "ai"
    except NarrativeFailed:
        notice = "The AI's text didn't pass the checks, so the assessment and strategy show plain text."
    except (LLMUnavailable, anthropic.APIError) as e:
        notice = f"The assessment and strategy show plain text: {friendly_error(e)}"
    except Exception:
        log.exception("Report narrative failed")
        notice = f"The assessment and strategy show plain text: {friendly_error(Exception())}"
    if notice:
        narrative, source = default_narrative(data), "default"
    repository.save_report(db, user_id, narrative.model_dump(), source,
                           repository.report_snapshot(db, user_id, data))
    state = state_for_user(db, user_id)
    state.notice = notice
    return state
