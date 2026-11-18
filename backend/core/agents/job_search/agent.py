"""Job Match agent (milestone 12): search the allowed job sites, verify the links, map the required skills to
the user's, save. The routes call only state_for_user, run_for_user and mark_for_user.

1. source.get_job_source().search: postings from the JOB_SITES allowlist, URLs only from the search results.
2. verify.get_checker(): a link that fails is dropped; one the site refuses to check (401/403/429) is kept and
   shown as not checked.
3. One structured-output call (Assessments) maps each required skill to one of the user's skills or plan
   gaps and writes the explanation; check() accepts only names from the user's own lists, with one retry. If
   it still fails (or the LLM is unavailable), a name-only mapping is used and the page says so.
4. matching.view works out the score on every read, so it rises as the user reports progress.
"""
import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import anthropic
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import repository
from core.agents.course_search import verify
from core.agents.course_search.search import url_key
from core.agents.job_search import matching, source
from core.agents.job_search.schemas import Assessments, Job, JobFinding, JobQuery, JobState
from core.llm import MODEL, LLMUnavailable, friendly_error, get_client

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # one retry with the problems fed back
CHECK_WORKERS = 5

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class NoAnalysis(Exception):
    pass


class AlreadyRunning(Exception):
    pass


class SearchFailed(Exception):
    """The job source failed (the message is safe to show)."""


def _lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def job_id(url: str) -> str:
    return "job-" + hashlib.sha1(url_key(url).encode()).hexdigest()[:12]


def to_job(f: JobFinding, link: str, found_on) -> Job:
    low, high = matching.parse_salary(f.salary)
    return Job(
        id=job_id(f.url), title=f.title, company=f.company, url=f.url, location=f.location, work_mode=f.work_mode,
        salary=f.salary, salary_min=low, salary_max=high, experience=f.experience, summary=f.summary,
        required_skills=f.required_skills, link=link, found_on=found_on,
    )


def _verified(findings: list[JobFinding], found_on) -> list[Job]:
    checker = verify.get_checker()
    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        statuses = list(pool.map(lambda f: checker(f.url)[0], findings))
    jobs = []
    for f, status in zip(findings, statuses):
        if status == "fail":
            log.info("Job dropped, link failed the check: %s", f.url)
            continue
        jobs.append(to_job(f, "ok" if status == "ok" else "blocked", found_on))
    return jobs


def _assess_request(jobs: list[Job], skills: list[str], plan: list[str], problems: list[str]) -> str:
    postings = [{"job_id": j.id, "title": j.title, "company": j.company, "summary": j.summary,
                 "required_skills": j.required_skills} for j in jobs]
    text = (
        f"Your skills:\n{json.dumps(skills, indent=2)}\n\n"
        f"Your plan (skill gaps you are learning):\n{json.dumps(plan, indent=2)}\n\n"
        f"<postings>\n{json.dumps(postings, indent=2).replace('</postings>', '')}\n</postings>"
    )
    if problems:
        text += "\n\nYour previous reply was rejected:\n- " + "\n- ".join(problems) + "\nReturn a corrected reply."
    return text


def assess(jobs: list[Job], skills: list[str], plan: list[str]) -> list[Job]:
    """Map the required skills with the LLM (checked), or by name when that fails. Raises nothing for LLM
    problems: those are logged and the name-only mapping is used (see notice_for)."""
    client = get_client()
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=8000,
                system=source.section("assess"),
                messages=[{"role": "user", "content": _assess_request(jobs, skills, plan, problems)}],
                output_format=Assessments,
            )
            result = response.parsed_output
            problems = ["The reply was empty or cut off."] if result is None else matching.check(result, jobs, skills, plan)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            by_id = {a.job_id: a for a in result.jobs}
            return [matching.apply(j, by_id[j.id].matches, by_id[j.id].explanation, skills, plan) for j in jobs]
        log.warning("Job assessment attempt %d of %d rejected: %s", attempt, MAX_ATTEMPTS, "; ".join(problems))
    raise AssessmentFailed("; ".join(problems))


class AssessmentFailed(Exception):
    pass


def state_for_user(db: Session, user_id: str) -> JobState:
    return repository.get_job_state(db, user_id)


def run_for_user(db: Session, user_id: str, query: JobQuery) -> JobState:
    """Search, verify, assess and save (blocking, about 30-60 s). Raises NoAnalysis, AlreadyRunning or
    SearchFailed; an assessment failure only adds a notice."""
    inputs = repository.job_inputs(db, user_id)  # commits, so no DB lock is held during the LLM calls
    if inputs is None:
        raise NoAnalysis("Run your skill-gap analysis first: jobs are matched against your skills.")
    lock = _lock(user_id)
    if not lock.acquire(blocking=False):
        raise AlreadyRunning("A job search is already running. Wait for it to finish.")
    try:
        try:
            findings = source.get_job_source().search(query, inputs.seeker)
        except (LLMUnavailable, anthropic.APIError) as e:
            raise SearchFailed(f"Job search is unavailable: {friendly_error(e)}")
        except Exception:
            log.exception("Job search failed")
            raise SearchFailed("Job search failed. Please try again in a moment.")
        jobs = _verified(findings, repository.today())
        notice = None
        if not jobs:
            notice = ("No open postings matched on the job sites searched. Try a broader location, or both "
                      "Remote and Hybrid.")
        else:
            try:
                jobs = assess(jobs, inputs.skills, inputs.plan)
            except (AssessmentFailed, LLMUnavailable, anthropic.APIError) as e:
                if not isinstance(e, AssessmentFailed):
                    log.warning("Job assessment unavailable: %s", friendly_error(e))
                jobs = [matching.fallback_matches(j, inputs.skills, inputs.plan) for j in jobs]
                notice = ("Skills were matched by name only this time, because the AI's matching wasn't available. "
                          "Refresh to try again.")
        log.info("Job search: %d found, %d kept after link checks (%s)", len(findings), len(jobs),
                 "ai" if not notice else "fallback" if jobs else "none")
        repository.save_job_search(db, user_id, query, jobs, notice)
        return repository.get_job_state(db, user_id)
    finally:
        lock.release()


def mark_for_user(db: Session, user_id: str, job_id_: str, saved: bool | None, applied: bool | None) -> JobState:
    """Save Job / Mark as applied (self-reported; nothing is sent anywhere). Raises ValidationFailed for a job
    that is neither in the results nor already marked."""
    repository.set_job_mark(db, user_id, job_id_, saved, applied)
    return repository.get_job_state(db, user_id)
