"""Scheduler agent: turns the approved resource list into a 6-month roadmap.

One structured-output call returns a RoadmapDraft. Pydantic validates it and budget.check_budget
enforces the calendar and the hour budget; a rejected attempt is retried with the problems fed
back. Transport errors (429/5xx/connection) are retried separately by the SDK client.
"""
import json
import logging
from pathlib import Path

from anthropic import transform_schema
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.scheduler.budget import MONTH_WEEKS, WEEKS, budget, check_budget, finalize, month_weeks
from core.agents.scheduler.schemas import Roadmap, RoadmapDraft, SchedulerInput
from core.llm import MODEL, get_client
from core.schemas import RoadmapState

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 3
# A 26-week roadmap is about 3-5k output tokens, so this leaves ample room. The SDK refuses
# non-streaming requests above ~21k; going higher means switching this call to streaming.
MAX_TOKENS = 20000
OUTPUT_FORMAT = {"type": "json_schema", "schema": transform_schema(RoadmapDraft)}


class SchedulerFailed(Exception):
    pass


class SchedulerTruncated(SchedulerFailed):
    """The reply hit MAX_TOKENS before the roadmap was complete."""


class ListNotApproved(Exception):
    pass


def _request(data: SchedulerInput, problems: list[str]) -> str:
    profile = data.model_dump(include={"current_role", "target_role", "ai_level", "capabilities", "domain"})
    gaps = [g.model_dump(include={"skill", "priority", "effort_hours", "domain_specific"}) for g in data.gaps]
    resources = [
        {
            **r.resource.model_dump(include={"id", "title", "format", "level", "hours", "description"}),
            "for_gaps": r.gaps,
            "priority": r.priority,
        }
        for r in data.resources
    ]
    calendar = "\n".join(
        f"- Month {m}: weeks {month_weeks(m)[0]}-{month_weeks(m)[-1]}" for m in range(1, len(MONTH_WEEKS) + 1)
    )
    limit = data.hours_per_week
    text = (
        f"Profile:\n{json.dumps(profile, indent=2)}\n\n"
        f"Skill gaps:\n{json.dumps(gaps, indent=2)}\n\n"
        f"Domain AI use cases:\n{json.dumps([u.model_dump() for u in data.domain_use_cases], indent=2)}\n\n"
        f"Approved resources ({sum(r.resource.hours for r in data.resources)} hours in total):\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        f"Calendar ({WEEKS} weeks):\n{calendar}\n\n"
        f"Weekly limit: {limit} hours. Total budget: {budget(limit)} hours."
    )
    if problems:
        text += "\n\nYour previous roadmap was rejected:\n- " + "\n- ".join(problems)
        text += "\nReturn a complete, corrected roadmap."
    return text


def build(data: SchedulerInput) -> Roadmap:
    """Return a roadmap that passed check_budget, or raise SchedulerFailed after MAX_ATTEMPTS.
    A truncated reply raises SchedulerTruncated at once: retrying with the same limit would cut
    off again. LLM errors (missing key, auth, rate limit) propagate for the caller to report."""
    client = get_client()
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=PROMPT,
            messages=[{"role": "user", "content": _request(data, problems)}],
            output_config={"format": OUTPUT_FORMAT},
        )
        # Checked before parsing: a cut-off reply is incomplete JSON, not an invalid roadmap.
        if response.stop_reason == "max_tokens":
            log.error(
                "Scheduler reply truncated: stop_reason=max_tokens at max_tokens=%d (model %s, attempt %d). "
                "Raise MAX_TOKENS (with streaming) or generate the roadmap month by month.",
                MAX_TOKENS, MODEL, attempt,
            )
            raise SchedulerTruncated(f"The roadmap was cut off at {MAX_TOKENS} output tokens.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            draft = RoadmapDraft.model_validate_json(text)
            problems = check_budget(draft, data)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return finalize(draft, data)
        log.warning("Scheduler attempt %d of %d rejected (stop_reason=%s): %s", attempt, MAX_ATTEMPTS, response.stop_reason, "; ".join(problems))
    raise SchedulerFailed("; ".join(problems))


def run_for_user(db: Session, user_id: str) -> RoadmapState:
    """Build and save the roadmap for the user's approved resource list."""
    gap_state = repository.get_gap_state(db, user_id)  # commits, so no DB lock is held during the LLM call
    approved = repository.get_approved_list(db, user_id)
    if approved is None:
        raise ListNotApproved("Approve your resource list on the Resources step first.")
    data = SchedulerInput(
        **{f: getattr(gap_state.profile, f) for f in repository.SCHEDULER_FIELDS},
        gaps=gap_state.analysis.gaps,
        domain_use_cases=gap_state.analysis.domain_use_cases,
        resources=approved.resources,
    )
    snapshot = repository.roadmap_snapshot(gap_state.profile, approved)
    return repository.save_roadmap(db, user_id, build(data), snapshot)
