from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core import repository
from core.agents.course_search import agent as course_search
from core.agents.resume_parser import agent as resume_parser
from core.auth import current_user
from core.db import get_db
from core.models import User

router = APIRouter(prefix="/api/account")


@router.delete("/data")
def start_over(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the signed-in user's saved data. The session stays, so they remain signed in."""
    repository.delete_user_data(db, user.user_id)
    course_search.reset_for_user(user.user_id)  # the refinement chat lives in the graph's checkpoints
    resume_parser.delete_files(user.user_id)  # the uploaded resume file
    return {"ok": True}
