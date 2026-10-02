"""Course search agent entry point. Milestone 4: knowledge base only (no LLM calls).
Milestone 5 replaces the body of run_for_user with the LangGraph graph."""
from sqlalchemy.orm import Session

from core import repository
from core.agents.course_search.search import find_resources
from core.schemas import ResourceState


class GapsNotConfirmed(Exception):
    pass


def run_for_user(db: Session, user_id: str) -> ResourceState:
    """Build and save the ranked resource list for the user's confirmed skill gaps."""
    gap_state = repository.get_gap_state(db, user_id)
    if gap_state.status != "ready" or not gap_state.confirmed or gap_state.stale:
        raise GapsNotConfirmed("Confirm your skill gaps on the Skill Gaps step first.")
    profile = repository.search_profile(gap_state.profile)
    result = find_resources(gap_state.analysis.gaps, profile)
    return repository.save_resource_list(db, user_id, result, gap_state)
