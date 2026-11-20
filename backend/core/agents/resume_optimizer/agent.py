"""Resume Optimizer agent (milestone 13): tailor the resume to one job without inventing anything.
The routes call only state_for_user, view_for_user, optimize, save_edits, reset_edits and document.

1. repository.optimizer_evidence: what the user can claim (resume + completed roadmap work) and what is pending.
2. One structured-output call (TailoredText): text plus references into the evidence; rules.check rejects
   unknown references, skills the user can't claim, numbers not in their data, links and "To add" items that
   are not pending, with one retry. If it still fails (or the LLM is unavailable), assemble.default_text is
   saved with a notice, so a version is always produced.
3. assemble builds the documents on every read (employers, titles and dates copied from the resume).
"""
import json
import logging
import threading
from pathlib import Path

import anthropic
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.job_search.schemas import Job, JobView
from core.agents.resume_optimizer import assemble, rules
from core.agents.resume_optimizer.schemas import (
    EditsIn, Evidence, JobOption, OptimizerState, OptimizerView, ResumeDoc, TailoredText,
)
from core.llm import MODEL, LLMUnavailable, friendly_error, get_client

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 2  # one retry with the problems fed back
MAX_TOKENS = 4000
NO_RESUME = ("You haven't uploaded a resume, so this version has no work history. Upload one on the Intake page "
             "to include your experience.")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class NoAnalysis(Exception):
    pass


class AlreadyRunning(Exception):
    pass


class UnknownJob(Exception):
    pass


class NotFound(Exception):
    pass


class TextFailed(Exception):
    pass


def _lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


# --- the model call --------------------------------------------------------------------


def request(e: Evidence, job: Job, view: JobView, problems: list[str] = ()) -> str:
    r = e.resume
    facts = {
        "target_role": e.target_role,
        "current_role": e.current_role,
        "years_experience": e.years_experience,
        "resume": {
            "roles": [{"ref": i, "title": x.title, "employer": x.employer, "highlights": x.highlights}
                      for i, x in enumerate(r.roles)],
            "skills": r.skills,
            "achievements": r.achievements,
        },
        "allowed_skills": e.skills,
        "completed_projects": [{"id": p.id, **p.project.model_dump()} for p in e.projects],
        "completed_courses": [c.model_dump() for c in e.courses],
        "pending_gaps": e.pending_gaps,
        "pending_projects": [p.model_dump() for p in e.pending_projects],
        "job_match": {"have": view.have, "missing": [m.model_dump() for m in view.missing]},
    }
    posting = {"title": job.title, "company": job.company, "summary": job.summary,
               "required_skills": job.required_skills, "experience": job.experience}
    text = (f"<facts>\n{json.dumps(facts, indent=2, ensure_ascii=False)}\n</facts>\n\n"
            f"<job>\n{json.dumps(posting, indent=2, ensure_ascii=False)}\n</job>")
    if problems:
        text += "\n\nYour previous reply was rejected:\n- " + "\n- ".join(problems) + "\nReturn a corrected reply."
    return text


def write(e: Evidence, job: Job, view: JobView) -> TailoredText:
    """Checked text, or TextFailed after MAX_ATTEMPTS. LLM errors propagate."""
    client = get_client()
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=PROMPT,
                messages=[{"role": "user", "content": request(e, job, view, problems)}],
                output_format=TailoredText,
            )
            result = response.parsed_output
            problems = ["The reply was empty or cut off."] if result is None else rules.check(result, e, job)
        except ValidationError as err:
            problems = [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in err.errors()[:10]]
        if not problems:
            return result
        log.warning("Resume optimizer attempt %d of %d rejected: %s", attempt, MAX_ATTEMPTS, "; ".join(problems))
    raise TextFailed("; ".join(problems))


# --- reads ---------------------------------------------------------------------------


def _snapshot(e: Evidence) -> dict:
    return e.model_dump(mode="json")


def state_for_user(db: Session, user_id: str) -> OptimizerState:
    e = repository.optimizer_evidence(db, user_id)
    jobs = repository.get_job_state(db, user_id)
    versions = {r.job_id: r for r in repository.tailored_records(db, user_id)}
    snapshot = _snapshot(e) if e else None
    options, seen = [], set()

    def option(job: Job, score: int):
        seen.add(job.id)
        row = versions.get(job.id)
        options.append(JobOption(id=job.id, title=job.title, company=job.company, score=score,
                                 has_version=row is not None, stale=bool(row and row.snapshot != snapshot),
                                 updated_at=row.updated_at if row else None))

    for v in [*jobs.jobs, *jobs.kept]:
        option(v.job, v.score)
    for job_id, row in versions.items():
        if job_id not in seen:
            job = Job.model_validate(row.job)
            option(job, repository.job_view(db, user_id, job).score)
    return OptimizerState(can_optimize=e is not None, has_resume=bool(e and e.has_resume), jobs=options)


def _build(e: Evidence, job: Job, view: JobView, row) -> OptimizerView:
    text = assemble.with_edits(TailoredText.model_validate(row.text), row.edits)
    tailored = assemble.tailored(e, text)
    notice = row.notice
    if not e.has_resume:
        notice = f"{notice} {NO_RESUME}" if notice else NO_RESUME
    return OptimizerView(
        job=view, original=assemble.original(e), tailored=tailored, keywords=text.keywords, to_add=text.to_add,
        improvements=view.missing, placeholders=assemble.placeholders(tailored), source=row.source,
        edited=row.edits is not None, stale=row.snapshot != _snapshot(e), notice=notice,
        has_resume=e.has_resume, updated_at=row.updated_at, text=assemble.to_text(tailored),
    )


def view_for_user(db: Session, user_id: str, job_id: str) -> OptimizerView:
    """Raises NotFound before a version exists for this job."""
    row = repository.get_tailored(db, user_id, job_id)
    e = repository.optimizer_evidence(db, user_id)
    if row is None or e is None:
        raise NotFound("Optimize your resume for this job first.")
    try:
        job = Job.model_validate(row.job)
        return _build(e, job, repository.job_view(db, user_id, job), row)
    except (ValidationError, IndexError, KeyError):
        log.exception("Saved tailored resume no longer loads")
        raise NotFound("Optimize your resume for this job again.")


def document(db: Session, user_id: str, job_id: str) -> tuple[ResumeDoc, Job]:
    view = view_for_user(db, user_id, job_id)
    return view.tailored, view.job.job


# --- writes --------------------------------------------------------------------------


def optimize(db: Session, user_id: str, job_id: str) -> OptimizerView:
    """Write (or rewrite) the tailored resume for one job (blocking, one LLM call). Raises NoAnalysis,
    UnknownJob or AlreadyRunning; never fails because of the LLM."""
    e = repository.optimizer_evidence(db, user_id)
    if e is None:
        raise NoAnalysis("Run your skill-gap analysis first: the optimizer works from your confirmed skills.")
    job = repository.find_job(db, user_id, job_id)
    if job is None:
        raise UnknownJob("That job is not in your Job Match results. Reload the page.")
    view = repository.job_view(db, user_id, job)
    db.commit()  # no DB lock held during the LLM call
    lock = _lock(user_id)
    if not lock.acquire(blocking=False):
        raise AlreadyRunning("Your resume is already being optimized. Wait for it to finish.")
    try:
        notice = None
        try:
            text, source = write(e, job, view), "ai"
        except TextFailed:
            notice = ("The AI's version didn't pass the checks, so this shows your resume as it is plus what "
                      "you have completed. Try Optimize again.")
        except (LLMUnavailable, anthropic.APIError) as err:
            notice = f"This shows your resume as it is plus what you have completed: {friendly_error(err)}"
        except Exception:
            log.exception("Resume optimizer failed")
            notice = f"This shows your resume as it is plus what you have completed: {friendly_error(Exception())}"
        if notice:
            text, source = assemble.default_text(e, view), "default"
        repository.save_tailored(db, user_id, job, _snapshot(e), text.model_dump(), source, notice)
    finally:
        lock.release()
    return view_for_user(db, user_id, job_id)


def save_edits(db: Session, user_id: str, job_id: str, edits: EditsIn) -> OptimizerView:
    """Save the user's own wording. The shape must match the saved version (same roles and projects); the
    employers, titles and dates are not part of the edit. Raises NotFound or ValidationFailed."""
    row = repository.get_tailored(db, user_id, job_id)
    if row is None:
        raise NotFound("Optimize your resume for this job first.")
    text = TailoredText.model_validate(row.text)
    errors = {}
    if len(edits.roles) != len(text.roles):
        errors["roles"] = f"Send the highlights of all {len(text.roles)} roles."
    if len(edits.projects) != len(text.projects):
        errors["projects"] = f"Send the bullets of all {len(text.projects)} projects."
    for where, line in [("headline", edits.headline), ("summary", edits.summary),
                        *[("roles", h) for g in edits.roles for h in g],
                        *[("projects", b) for g in edits.projects for b in g]]:
        if rules.LINK.search(line):
            errors.setdefault(where, "Links can't go in the resume text.")
    if errors:
        raise repository.ValidationFailed(errors)
    repository.save_tailored_edits(db, user_id, job_id, edits.model_dump())
    return view_for_user(db, user_id, job_id)


def reset_edits(db: Session, user_id: str, job_id: str) -> OptimizerView:
    if repository.get_tailored(db, user_id, job_id) is None:
        raise NotFound("Optimize your resume for this job first.")
    repository.save_tailored_edits(db, user_id, job_id, None)
    return view_for_user(db, user_id, job_id)
