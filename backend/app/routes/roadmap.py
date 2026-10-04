import anthropic
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from core import repository
from core.agents.scheduler import agent
from core.agents.scheduler.export import to_markdown
from core.auth import current_user
from core.db import get_db
from core.llm import LLMUnavailable, friendly_error
from core.models import User
from core.schemas import RoadmapState

router = APIRouter(prefix="/api/roadmap")


@router.get("", response_model=RoadmapState)
def get_roadmap(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return repository.get_roadmap_state(db, user.user_id)


# Plain def: FastAPI runs it in a worker thread, so the long LLM call doesn't block other requests.
@router.post("/generate", response_model=RoadmapState)
def generate(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.run_for_user(db, user.user_id)
    except agent.ListNotApproved as e:
        raise HTTPException(409, str(e))
    except agent.SchedulerTruncated:
        raise HTTPException(502, "The roadmap was too long for one AI reply and was cut off. Please try again.")
    except agent.SchedulerFailed:
        raise HTTPException(502, "The AI couldn't produce a roadmap that fits your weekly hours. Please try again.")
    except (LLMUnavailable, anthropic.APIError) as e:  # missing key, auth, rate limit, connection
        raise HTTPException(503, friendly_error(e))


@router.get("/export.md")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = repository.get_roadmap_state(db, user.user_id)
    if state.roadmap is None:
        raise HTTPException(404, "Generate your roadmap first.")
    return Response(
        to_markdown(state.roadmap, state.profile),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-career-roadmap.md"'},
    )
