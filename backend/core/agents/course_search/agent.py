"""Course search agent entry points. They only start, resume and read the LangGraph graph
(graph.py); FastAPI routes call these and nothing else."""
import logging
import threading
from collections.abc import Iterator

from langgraph.types import Command
from sqlalchemy.orm import Session

from core import repository
from core.agents.course_search.graph import get_graph
from core.agents.course_search.schemas import Preferences
from core.llm import friendly_error
from core.repository import NotReady, ValidationFailed
from core.schemas import ChatMessage, FilterIn, ProgressIn, ResourceState

log = logging.getLogger(__name__)

BUSY = "Still working on your last request. Try again in a moment."

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class GapsNotConfirmed(Exception):
    pass


def _config(user_id: str) -> dict:
    return {"configurable": {"thread_id": user_id}}


def _lock(user_id: str) -> threading.Lock:
    """One graph run per user at a time: a second resume of the same pause would corrupt the thread."""
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def _paused(user_id: str) -> dict | None:
    """The graph state if the user's thread is waiting for their next message, else None."""
    snapshot = get_graph().get_state(_config(user_id))
    return snapshot.values if snapshot.next == ("await_user",) else None


def state_for_user(db: Session, user_id: str) -> ResourceState:
    """The saved resource list plus the refinement chat. A list without a paused thread (e.g. built
    before the chat existed) is reported stale, so the page offers to rebuild it."""
    state = repository.get_resource_state(db, user_id)
    if state.status != "ready":
        return state
    values = _paused(user_id)
    if values is None:
        return state.model_copy(update={"stale": True})
    return state.model_copy(update={
        "messages": [ChatMessage(**m) for m in values.get("messages", [])],
        "notice": values.get("notice"),
        "preferences": Preferences(**values.get("preferences", {})),
    })


def check_ready(db: Session, user_id: str) -> ResourceState:
    state = state_for_user(db, user_id)
    if state.status != "ready" or state.stale:
        raise NotReady("Build an up-to-date resource list first.")
    return state


def run_for_user(db: Session, user_id: str) -> ResourceState:
    """Start the graph for the user's confirmed skill gaps: it builds and saves the ranked list,
    then pauses for the refinement chat. Any earlier chat is discarded."""
    gap_state = repository.get_gap_state(db, user_id)
    if gap_state.status != "ready" or not gap_state.confirmed or gap_state.stale:
        raise GapsNotConfirmed("Confirm your skill gaps on the Skill Gaps step first.")
    start = {
        "gaps": [g.model_dump() for g in gap_state.analysis.gaps],
        "profile": repository.search_profile(gap_state.profile).model_dump(),
        "search_requests": None,
    }
    with _lock(user_id):
        graph = get_graph()
        graph.checkpointer.delete_thread(user_id)
        graph.invoke(start, _config(user_id))
    db.expire_all()  # the graph saved the list in its own session
    return state_for_user(db, user_id)


def chat_turn(db: Session, user_id: str, message: str) -> Iterator[dict]:
    """Resume the graph with the user's message. Yields {"type": "token", "text"} as the reply is
    written, then {"type": "state", "resources"} and {"type": "done"}, or {"type": "error"}."""
    lock = _lock(user_id)
    if not lock.acquire(blocking=False):
        yield {"type": "error", "message": BUSY}
        return
    try:
        resume = Command(resume={"type": "message", "text": message})
        yield from get_graph().stream(resume, _config(user_id), stream_mode="custom")
        db.expire_all()
        yield {"type": "state", "resources": state_for_user(db, user_id).model_dump(mode="json")}
        yield {"type": "done"}
    except Exception as exc:  # surfaced to the UI as a friendly message
        log.exception("Refinement turn failed")
        yield {"type": "error", "message": friendly_error(exc)}
    finally:
        lock.release()


def approve_for_user(db: Session, user_id: str) -> ResourceState:
    """Approve the current list (the "Approve list" button): resumes the graph, which saves it
    with save_approved_list(via="refinement")."""
    state = check_ready(db, user_id)
    repository.build_approved_list(state.resources)  # raises ValidationFailed for an empty list
    with _lock(user_id):
        get_graph().invoke(Command(resume={"type": "approve"}), _config(user_id))
    db.expire_all()
    return state_for_user(db, user_id)


def remove_for_user(db: Session, user_id: str, resource_id: str) -> ResourceState:
    """Remove one resource (the "Remove" button on a card): resumes the graph with the same remove
    operation the chat produces, without a model call."""
    state = check_ready(db, user_id)
    if resource_id not in {r.resource.id for g in state.resources.gaps for r in g.resources}:
        raise ValidationFailed({"resource_id": "That resource is not on your list. Reload the page."})
    with _lock(user_id):
        get_graph().invoke(Command(resume={"type": "remove", "resource_id": resource_id}), _config(user_id))
    db.expire_all()
    return state_for_user(db, user_id)


def filter_for_user(db: Session, user_id: str, filters: FilterIn) -> ResourceState:
    """The filter chips: resume the graph with the filters directly (no model call, no web search). The
    list is rebuilt from what is already known, so what is shown is what gets approved."""
    check_ready(db, user_id)
    request = {"type": "filter", **filters.model_dump()}
    with _lock(user_id):
        get_graph().invoke(Command(resume=request), _config(user_id))
    db.expire_all()
    return state_for_user(db, user_id)


def progress_for_user(db: Session, user_id: str, change: ProgressIn) -> ResourceState:
    """Save / Start / Complete on a resource that is on the user's list, or that they marked before. Not a
    list change, so the graph is not involved."""
    state = state_for_user(db, user_id)
    listed = {r.resource.id: r.resource for g in (state.resources.gaps if state.resources else []) for r in g.resources}
    known = {p.resource.id: p.resource for p in state.progress}
    resource = listed.get(change.resource_id) or known.get(change.resource_id)
    if resource is None:
        raise ValidationFailed({"resource_id": "That resource is not on your list. Reload the page."})
    repository.set_progress(db, user_id, resource, change.saved, change.status)
    return state_for_user(db, user_id)


def reset_for_user(user_id: str) -> None:
    """Start over: forget the user's graph thread (list state and chat)."""
    with _lock(user_id):
        get_graph().checkpointer.delete_thread(user_id)
