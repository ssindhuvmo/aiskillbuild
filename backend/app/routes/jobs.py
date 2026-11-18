from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core import repository
from core.agents.job_search import agent
from core.agents.job_search.schemas import JobMarkIn, JobQuery, JobState
from core.auth import current_user
from core.db import get_db
from core.models import User

router = APIRouter(prefix="/api/jobs")


@router.get("", response_model=JobState)
def get_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.state_for_user(db, user.user_id)


@router.post("/search", response_model=JobState)
def search(body: JobQuery, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Blocking (about 30-60 s): search the allowed job sites, check the links, match the skills, save."""
    try:
        return agent.run_for_user(db, user.user_id, body)
    except (agent.NoAnalysis, agent.AlreadyRunning) as e:
        raise HTTPException(409, str(e))
    except agent.SearchFailed as e:
        raise HTTPException(503, str(e))


@router.put("/marks", response_model=JobState)
def mark(body: JobMarkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.mark_for_user(db, user.user_id, body.job_id, body.saved, body.applied)
    except repository.ValidationFailed as e:
        raise HTTPException(422, e.errors["job_id"])
