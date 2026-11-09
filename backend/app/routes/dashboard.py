from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth import current_user
from core.db import get_db
from core.models import User
from core.progress import service
from core.schemas import DashboardState

router = APIRouter(prefix="/api/dashboard")


@router.get("", response_model=DashboardState)
def get_dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.dashboard_for_user(db, user.user_id)


@router.post("/readiness", response_model=DashboardState)
def recalculate(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.recalculate(db, user.user_id)
