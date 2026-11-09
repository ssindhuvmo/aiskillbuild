"""What the Dashboard and Progress Review routes call (milestone 11)."""
from sqlalchemy.orm import Session

from core import repository
from core.progress import assemble
from core.progress.schemas import ProgressReviewIn
from core.schemas import DashboardState, ProgressState


def dashboard_for_user(db: Session, user_id: str) -> DashboardState:
    data = repository.progress_data(db, user_id)
    if data is None:
        return DashboardState(status="none")
    return DashboardState(status="ready", dashboard=assemble.dashboard(data))


def recalculate(db: Session, user_id: str) -> DashboardState:
    """Recalculate Readiness Score: record today's score for the trend, then the dashboard."""
    repository.record_readiness(db, user_id)
    return dashboard_for_user(db, user_id)


def review_for_user(db: Session, user_id: str) -> ProgressState:
    data = repository.progress_data(db, user_id)
    if data is None:
        return ProgressState(status="none")
    return ProgressState(status="ready", review=assemble.review(data))


def save_review(db: Session, user_id: str, body: ProgressReviewIn) -> ProgressState:
    """Update Progress. Raises repository.NotReady (no analysis) or ValidationFailed (a skill not in the plan)."""
    repository.save_progress_review(db, user_id, body)
    return review_for_user(db, user_id)
