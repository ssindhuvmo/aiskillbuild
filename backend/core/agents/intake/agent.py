"""Conversational intake agent.

The LLM extracts field values via the `record_profile` tool; deterministic validation
(validation.py) decides what is accepted. The server's stored profile is the source of
truth, so the model can never mark a field collected that failed validation. Structured
answers (resume, capability ratings, preferences, constraints) can also come from widgets
on the page, which save through the profile API; the chat then simply moves on.
"""
import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.intake.validation import (
    BUDGETS, CAPABILITY_AREAS, CONSTRAINT_FLAGS, LEVELS, PREFERENCES, SKIPPABLE, STEPS,
)
from core.config import load_domains
from core.llm import MODEL, friendly_error, get_client
from core.schemas import RoleSuggestion

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 3

RECORD_PROFILE_TOOL = {
    "name": "record_profile",
    "description": "Save profile values the user just provided. Only include fields learned this turn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target_role": {"type": "string"},
            "current_role": {"type": "string"},
            "years_experience": {"type": "integer", "description": "Years of professional experience"},
            "domain": {"type": "string", "description": "Industry; for 'Other' the actual industry name"},
            "hours_per_week": {"type": "integer"},
            "capabilities": {
                "type": "object",
                "description": "Self-ratings; include only the areas the user rated this turn",
                "properties": {a: {"type": "string", "enum": LEVELS} for a in CAPABILITY_AREAS},
            },
            "learning_preferences": {"type": "array", "items": {"type": "string", "enum": list(PREFERENCES)}},
            "constraints": {
                "type": "object",
                "properties": {
                    "budget": {"type": "string", "enum": BUDGETS},
                    "monthly_budget": {"type": "integer"},
                    **{f: {"type": "boolean"} for f in CONSTRAINT_FLAGS},
                    "other": {"type": "string"},
                },
            },
            "additional_context": {"type": "string"},
            "skip": {
                "type": "array",
                "items": {"type": "string", "enum": SKIPPABLE},
                "description": "Optional steps the user chose to skip",
            },
            "help_choose": {"type": "boolean", "description": "True when the user wants help choosing a target role"},
        },
    },
}

SUGGEST_ROLES_TOOL = {
    "name": "suggest_roles",
    "description": "Offer 2-3 AI roles that suit the user, each with a one-sentence reason. The app shows them as "
    "cards the user can pick from.",
    "input_schema": {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {"role": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["role", "reason"],
                },
            }
        },
        "required": ["roles"],
    },
}


def _resume_summary(data: dict | None) -> dict | None:
    """Only reviewed fields reach the intake model, never the resume text."""
    if not data:
        return None
    return {
        "roles": [f"{r['title']} at {r['employer']}" for r in data.get("roles", [])[:5]],
        "skills": data.get("skills", [])[:20],
        "certifications": [c["name"] for c in data.get("certifications", [])],
    }


def _system_prompt(db: Session, user_id: str) -> str:
    profile = repository.get_profile(db, user_id)
    data = profile.model_dump()
    collected = {
        f: data[f] for f in ("target_role", "current_role", "years_experience", "domain", "hours_per_week",
                             "capabilities", "learning_preferences", "constraints", "additional_context")
        if data[f] not in (None, "", {}, [])
    }
    state = {
        "collected": collected,
        "from_resume": [f for f, s in profile.field_sources.items() if s == "resume"],
        "steps": [{"step": s.id, "done": s.done} for s in profile.steps],
        "next_step": profile.next_step,
        "resume": profile.resume_status or ("skipped" if profile.resume_skipped else "not uploaded"),
        "reviewed_resume": _resume_summary(repository.reviewed_resume(db, user_id)),
        "help_choose": bool(repository.intake_flags(db, user_id).get("help_choose")),
        "roles_suggested": [s.role for s in repository.get_suggestions(db, user_id)],
        "missing_required": profile.missing,
    }
    return (
        PROMPT.replace("{domains}", ", ".join(d for d in load_domains() if d != "Other") + ", Other")
        .replace("{steps}", "\n".join(f"- {k}: {v}" for k, v in STEPS.items()))
        .replace("{areas}", ", ".join(f"{k} ({v})" for k, v in CAPABILITY_AREAS.items()))
        .replace("{preferences}", ", ".join(f"{k} ({v})" for k, v in PREFERENCES.items()))
        .replace("{state}", json.dumps(state, indent=2))
    )


def _record(db: Session, user_id: str, values: dict) -> dict:
    if values.pop("help_choose", False):
        repository.set_intake_flags(db, user_id, help_choose=True)
    accepted, errors = repository.apply_updates(db, user_id, values)
    profile = repository.get_profile(db, user_id)
    return {"accepted": accepted, "rejected": errors, "next_step": profile.next_step, "missing": profile.missing}


def _suggest(db: Session, user_id: str, values: dict) -> dict:
    try:
        roles = [RoleSuggestion.model_validate(r) for r in values.get("roles", [])]
    except ValidationError as e:
        return {"accepted": False, "problems": [err["msg"] for err in e.errors()[:5]]}
    if not 2 <= len(roles) <= 3:
        return {"accepted": False, "problems": ["Suggest 2 or 3 roles."]}
    repository.set_intake_flags(db, user_id, suggestions=[r.model_dump() for r in roles])
    return {"accepted": True, "shown_to_user_as_cards": [r.role for r in roles]}


TOOLS = {"record_profile": _record, "suggest_roles": _suggest}


def _state_event(db: Session, user_id: str) -> dict:
    state = repository.get_intake_state(db, user_id)
    return {"type": "state", "profile": state.profile.model_dump(), "suggestions": [s.model_dump() for s in state.suggestions]}


def run_turn(db: Session, user_id: str, user_message: str) -> Iterator[dict]:
    """Yield events: {"type": "token", "text"}, {"type": "state", "profile", "suggestions"}, {"type": "done"}
    or {"type": "error"}."""
    repository.append_message(db, user_id, "user", user_message)
    history = [m.model_dump() for m in repository.get_messages(db, user_id)]
    messages: list[dict] = list(history)
    reply_parts: list[str] = []

    try:
        client = get_client()
        for _ in range(MAX_TOOL_ROUNDS + 1):
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                system=_system_prompt(db, user_id),
                messages=messages,
                tools=[RECORD_PROFILE_TOOL, SUGGEST_ROLES_TOOL],
            ) as stream:
                for text in stream.text_stream:
                    reply_parts.append(text)
                    yield {"type": "token", "text": text}
                final = stream.get_final_message()

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if not tool_uses:
                break

            results = []
            for block in tool_uses:
                handler = TOOLS.get(block.name)
                outcome = handler(db, user_id, dict(block.input)) if handler else {"error": f"Unknown tool {block.name}."}
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(outcome)})
            yield _state_event(db, user_id)
            messages.append({"role": "assistant", "content": [b.model_dump() for b in final.content]})
            messages.append({"role": "user", "content": results})
            if reply_parts and not reply_parts[-1].endswith("\n"):
                reply_parts.append("\n\n")
                yield {"type": "token", "text": "\n\n"}

        reply = "".join(reply_parts).strip()
        if reply:
            repository.append_message(db, user_id, "assistant", reply)
        yield _state_event(db, user_id)
        yield {"type": "done"}
    except Exception as exc:  # surfaced to the UI as a friendly message
        yield {"type": "error", "message": friendly_error(exc)}
