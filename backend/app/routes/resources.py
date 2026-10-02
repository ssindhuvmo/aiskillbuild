from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core import repository
from core.agents.course_search import agent
from core.auth import current_user
from core.db import get_db
from core.models import User
from core.schemas import ResourceState

router = APIRouter(prefix="/api/resources")


@router.get("", response_model=ResourceState)
def get_resources(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return repository.get_resource_state(db, user.user_id)


@router.post("/search", response_model=ResourceState)
def search(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.run_for_user(db, user.user_id)
    except agent.GapsNotConfirmed as e:
        raise HTTPException(409, str(e))
