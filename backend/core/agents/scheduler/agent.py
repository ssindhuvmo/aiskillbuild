"""Scheduler agent: turns the approved resource list into a 6-month roadmap.

Python builds the plan (placement.place) and budget.check_budget asserts it; it is saved and sent at once.
Then the three phases' text is written by the LLM in parallel (narrative.write), and each phase is applied,
saved and streamed as it arrives. A phase whose text fails keeps placement's default text, so generating
never fails because of the LLM. The routes call only check_ready, state_for_user and generate.
"""
import logging
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
from sqlalchemy.orm import Session

from core import repository
from core.agents.scheduler import narrative
from core.agents.scheduler.budget import check_budget
from core.agents.scheduler.placement import place
from core.agents.scheduler.schemas import Roadmap, SchedulerInput
from core.db import SessionLocal
from core.llm import LLMUnavailable, friendly_error
from core.schemas import RoadmapState

log = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class ListNotApproved(Exception):
    pass


class AlreadyRunning(Exception):
    pass


class PlacementFailed(Exception):
    """check_budget rejected a placed plan: a bug in placement, never an LLM problem."""


def _lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def check_ready(db: Session, user_id: str) -> None:
    if repository.get_approved_list(db, user_id) is None:
        raise ListNotApproved("Approve your resource list on the Resources step first.")
    if _lock(user_id).locked():
        raise AlreadyRunning("Your roadmap is already being built. Wait for it to finish.")


def state_for_user(db: Session, user_id: str) -> RoadmapState:
    """The saved roadmap. A phase left "pending" by an interrupted run (e.g. a server restart) shows as default."""
    state = repository.get_roadmap_state(db, user_id)
    if state.roadmap and not _lock(user_id).locked():
        for phase in state.roadmap.phases:
            if phase.narrative == "pending":
                phase.narrative = "default"
    return state


def _input(db: Session, user_id: str) -> tuple[SchedulerInput, dict]:
    gap_state = repository.get_gap_state(db, user_id)
    approved = repository.get_approved_list(db, user_id)
    if approved is None:
        raise ListNotApproved("Approve your resource list on the Resources step first.")
    data = SchedulerInput(
        **{f: getattr(gap_state.profile, f) for f in repository.SCHEDULER_FIELDS},
        gaps=gap_state.analysis.gaps,
        domain_use_cases=gap_state.analysis.domain_use_cases,
        resources=approved.resources,
    )
    return data, repository.roadmap_snapshot(gap_state.profile, approved)


def build(data: SchedulerInput) -> Roadmap:
    """The placed plan with default text, checked against the budget rules."""
    roadmap = place(data)
    if problems := check_budget(roadmap, data):
        log.error("Scheduler placement broke the budget rules: %s", "; ".join(problems))
        raise PlacementFailed("Something went wrong while planning your weeks. Please try again.")
    return roadmap


def _event(state: RoadmapState | None, **extra) -> dict:
    return {"type": "state", **({"state": state.model_dump(mode="json")} if state else {}), **extra}


def generate(user_id: str) -> Iterator[dict]:
    """SSE events: `state` with the placed roadmap, then one `state` per phase as its text arrives (`phase`,
    and `notice` when the default text was kept), then `done`; `error` if the plan can't be built.
    Opens its own DB session (it outlives the request)."""
    lock = _lock(user_id)
    if not lock.acquire(blocking=False):
        yield {"type": "error", "message": "Your roadmap is already being built. Wait for it to finish."}
        return
    db = SessionLocal()
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="roadmap-narrative")
    roadmap = None
    started = time.monotonic()
    timings: list[str] = []
    try:
        try:
            data, snapshot = _input(db, user_id)
            roadmap = build(data)
        except (ListNotApproved, PlacementFailed) as e:
            yield {"type": "error", "message": str(e)}
            return
        yield _event(repository.save_roadmap(db, user_id, roadmap, snapshot, log=False))
        placed = time.monotonic() - started

        futures = {
            pool.submit(narrative.write, data, roadmap.model_copy(deep=True), phase): phase.number
            for phase in roadmap.phases
        }
        for future in as_completed(futures):
            number, notice = futures[future], None
            try:
                narrative.apply(roadmap, number, future.result())
            except narrative.NarrativeFailed:
                notice = f"The AI's text for phase {number} didn't pass the checks, so it shows plain text."
            except (LLMUnavailable, anthropic.APIError) as e:
                notice = f"Phase {number} shows plain text: {friendly_error(e)}"
            except Exception:
                log.exception("Scheduler narrative for phase %d failed", number)
                notice = f"Phase {number} shows plain text: {friendly_error(Exception())}"
            if notice:
                narrative.use_default(roadmap, number)
            timings.append(f"phase {number} {roadmap.phases[number - 1].narrative} {time.monotonic() - started:.1f} s")
            last = all(p.narrative != "pending" for p in roadmap.phases)
            state = repository.update_roadmap(db, user_id, roadmap, log_snapshot=snapshot if last else None)
            yield _event(state, phase=number, notice=notice)
        log.info("Roadmap generated: plan placed in %.2f s; %s; total %.1f s",
                 placed, ", ".join(timings), time.monotonic() - started)
        yield {"type": "done"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        # The client went away (or something failed) before every phase arrived: keep the default text.
        if roadmap is not None and any(p.narrative == "pending" for p in roadmap.phases):
            for phase in roadmap.phases:
                if phase.narrative == "pending":
                    narrative.use_default(roadmap, phase.number)
            try:
                repository.update_roadmap(db, user_id, roadmap)
            except Exception:
                log.exception("Could not save the roadmap's default text")
        db.close()
        lock.release()
