from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core import repository
from core.auth import current_user
from core.db import get_db
from core.models import User

router = APIRouter(prefix="/api/account")


@router.delete("/data")
def start_over(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the signed-in user's saved data. The session stays, so they remain signed in."""
    repository.delete_user_data(db, user.user_id)
    return {"ok": True}
