import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core import repository
from core.agents.gap_analysis import agent
from core.auth import current_user
from core.db import get_db
from core.llm import LLMUnavailable, friendly_error
from core.models import User
from core.repository import ValidationFailed
from core.schemas import AnalyzeIn, GapState

router = APIRouter(prefix="/api/gaps")


@router.get("", response_model=GapState)
def get_gaps(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return repository.get_gap_state(db, user.user_id)


# Plain def: FastAPI runs it in a worker thread, so the 20-40 s LLM call doesn't block other requests.
@router.post("/analyze", response_model=GapState)
def analyze(body: AnalyzeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.run_for_user(db, user.user_id, body.corrections)
    except agent.ProfileNotConfirmed as e:
        raise HTTPException(409, str(e))
    except agent.GapAnalysisFailed:
        raise HTTPException(502, "The AI couldn't produce a valid skill analysis. Please try again.")
    except (LLMUnavailable, anthropic.APIError) as e:  # missing key, auth, rate limit, connection
        raise HTTPException(503, friendly_error(e))


@router.post("/confirm", response_model=GapState)
def confirm(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return repository.confirm_gaps(db, user.user_id)
    except ValidationFailed as e:
        raise HTTPException(409, e.errors["analysis"])
