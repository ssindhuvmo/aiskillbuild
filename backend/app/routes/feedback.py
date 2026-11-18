from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core import repository
from core.auth import current_user
from core.db import get_db
from core.models import User
from core.schemas import FeedbackIn

router = APIRouter(prefix="/api/feedback")


@router.post("")
def send_feedback(body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The feedback form: rating and area are optional, the message is required (422 when blank)."""
    repository.save_feedback(db, user.user_id, body)
    return {"ok": True}
