from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core import repository
from core.auth import current_user
from core.db import get_db
from core.models import User
from core.progress import service
from core.progress.schemas import ProgressReviewIn
from core.schemas import ProgressState

router = APIRouter(prefix="/api/progress")


@router.get("", response_model=ProgressState)
def get_progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.review_for_user(db, user.user_id)


@router.put("", response_model=ProgressState)
def save_progress(body: ProgressReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return service.save_review(db, user.user_id, body)
    except repository.NotReady as e:
        raise HTTPException(409, str(e))
    except repository.ValidationFailed as e:
        raise HTTPException(422, e.errors["skills"])
