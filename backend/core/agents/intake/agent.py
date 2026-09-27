"""Conversational intake agent.

The LLM extracts field values via the `record_profile` tool; deterministic validation
(validation.py) decides what is accepted. The server's stored profile is the source of
truth, so the model can never mark a field collected that failed validation.
"""
import json
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session

from core import repository
from core.agents.intake.validation import AI_EXPERIENCE, FIELDS, missing_fields
from core.config import load_domains
from core.llm import MODEL, friendly_error, get_client

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 3

RECORD_PROFILE_TOOL = {
    "name": "record_profile",
    "description": "Save profile values the user just provided. Only include fields learned this turn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "current_role": {"type": "string"},
            "target_role": {"type": "string"},
            "ai_experience": {"type": "string", "enum": AI_EXPERIENCE},
            "domain": {"type": "string", "description": "Industry; for 'Other' the actual industry name"},
            "hours_per_week": {"type": "integer"},
        },
    },
}


def _system_prompt(profile: dict) -> str:
    state = {
        "collected": {f: profile[f] for f in FIELDS if profile.get(f) not in (None, "")},
        "missing": missing_fields(profile),
    }
    return PROMPT.replace("{domains}", ", ".join(d for d in load_domains() if d != "Other") + ", Other").replace(
        "{state}", json.dumps(state, indent=2)
    )


def _profile_dict(db: Session, user_id: str) -> dict:
    return repository.get_profile(db, user_id).model_dump()


def run_turn(db: Session, user_id: str, user_message: str) -> Iterator[dict]:
    """Yield events: {"type": "token", "text"}, {"type": "state", "profile"}, {"type": "done"} or {"type": "error"}."""
    repository.append_message(db, user_id, "user", user_message)
    history = [m.model_dump() for m in repository.get_messages(db, user_id)]
    messages: list[dict] = list(history)
    reply_parts: list[str] = []

    try:
        client = get_client()
        for _ in range(MAX_TOOL_ROUNDS + 1):
            profile = _profile_dict(db, user_id)
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                system=_system_prompt(profile),
                messages=messages,
                tools=[RECORD_PROFILE_TOOL],
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
                accepted, errors = repository.apply_updates(db, user_id, dict(block.input))
                current = _profile_dict(db, user_id)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(
                            {"accepted": accepted, "rejected": errors, "still_missing": missing_fields(current)}
                        ),
                    }
                )
            yield {"type": "state", "profile": repository.get_profile(db, user_id).model_dump()}
            messages.append({"role": "assistant", "content": [b.model_dump() for b in final.content]})
            messages.append({"role": "user", "content": results})
            if reply_parts and not reply_parts[-1].endswith("\n"):
                reply_parts.append("\n\n")
                yield {"type": "token", "text": "\n\n"}

        reply = "".join(reply_parts).strip()
        if reply:
            repository.append_message(db, user_id, "assistant", reply)
        yield {"type": "state", "profile": repository.get_profile(db, user_id).model_dump()}
        yield {"type": "done"}
    except Exception as exc:  # surfaced to the UI as a friendly message
        yield {"type": "error", "message": friendly_error(exc)}
