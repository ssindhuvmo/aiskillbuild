"""Resume parser agent.

One structured-output call reads the resume text into ResumeData. Pydantic validates it and
`rules.check_rules` requires every name to appear in the text and every date to be valid; a rejected
attempt is retried with the problems fed back. If the last valid reply still has problems after
MAX_ATTEMPTS, the items that pass are kept and the rest are listed as dropped. The user reviews
the result before anything else uses it.
"""
import logging
import re
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.resume_parser import extract, rules, storage
from core.agents.resume_parser.schemas import ResumeData, ResumeDraft
from core.llm import MODEL, get_client
from core.schemas import ResumeState

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 3
log = logging.getLogger(__name__)


class ResumeParseFailed(Exception):
    pass


def _request(text: str, problems: list[str]) -> str:
    # The resume can't close the tag early, so all of it stays inside <resume>.
    safe = re.sub(r"</?\s*resume\s*>", "", text, flags=re.IGNORECASE)
    request = f"<resume>\n{safe}\n</resume>"
    if problems:
        request += "\n\nYour previous extraction was rejected:\n- " + "\n- ".join(problems[:20])
        request += "\nReturn a complete, corrected extraction."
    return request


def parse(text: str) -> ResumeDraft:
    """Return the extracted data for review, or raise ResumeParseFailed when no reply validated or
    nothing usable is left. LLM errors (missing key, auth, rate limit) propagate for the caller."""
    client = get_client()
    problems: list[str] = []
    last_valid: ResumeData | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=8000,
                system=PROMPT,
                messages=[{"role": "user", "content": _request(text, problems)}],
                output_format=ResumeData,
            )
            result = response.parsed_output
            if result is None:
                problems = ["The reply was empty or cut off."]
                continue
            last_valid = result
            problems = rules.check_rules(result, text)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
            continue
        if not problems:
            return ResumeDraft(data=result)
        log.warning("Resume parse attempt rejected: %s", "; ".join(problems[:10]))
    if last_valid is None:
        log.error("Resume parse failed, no valid reply: %s", "; ".join(problems[:10]))
        raise ResumeParseFailed("; ".join(problems))
    data, dropped = rules.filter_unverified(last_valid, text)
    if dropped:
        log.warning("Resume parse kept partial result, dropped: %s", ", ".join(dropped))
    if data.is_empty():
        log.error("Resume parse failed, nothing in the extraction was found in the text")
        raise ResumeParseFailed("Nothing in the extraction could be found in the resume text.")
    return ResumeDraft(data=data, dropped=dropped)


def _safe_filename(filename: str | None) -> str:
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    return name[:255] or "resume"


def upload_for_user(db: Session, user_id: str, filename: str | None, content: bytes) -> ResumeState:
    """Validate, read and parse an upload, then store it for review. Raises extract.InvalidFile,
    ResumeParseFailed or an LLM error; nothing is stored unless parsing succeeds."""
    name = _safe_filename(filename)
    kind, text = extract.read(name, content)
    draft = parse(text)
    path = storage.save(user_id, kind, content)
    return repository.save_resume_draft(
        db, user_id, filename=name, stored_path=str(path), content_type=extract.CONTENT_TYPES[kind],
        size=len(content), text=text, draft=draft,
    )


def save_for_user(db: Session, user_id: str, data: ResumeData) -> ResumeState:
    """Save the user's reviewed data and pre-fill the profile from it. The user's edits are not
    checked against the text (they may add what the parser missed), only for valid dates."""
    problems = rules.check_rules(data)
    if problems:
        raise repository.ValidationFailed({"resume": " ".join(problems)})
    return repository.save_reviewed_resume(db, user_id, data, rules.prefill(data))


def delete_for_user(db: Session, user_id: str) -> ResumeState:
    repository.delete_resume(db, user_id)
    storage.delete_user_files(user_id)
    return repository.get_resume_state(db, user_id)


def delete_files(user_id: str) -> None:
    """Start over: the uploaded file goes with the user's rows."""
    storage.delete_user_files(user_id)
