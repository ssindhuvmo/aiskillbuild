import json

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.agents.scheduler import agent
from core.agents.scheduler.export import to_markdown
from core.auth import current_user
from core.db import get_db
from core.models import User
from core.schemas import RoadmapState

router = APIRouter(prefix="/api/roadmap")


@router.get("", response_model=RoadmapState)
def get_roadmap(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.state_for_user(db, user.user_id)


@router.post("/generate")
def generate(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """SSE: the placed roadmap at once, then each phase's text as it arrives (see agent.generate)."""
    try:
        agent.check_ready(db, user.user_id)
    except (agent.ListNotApproved, agent.AlreadyRunning) as e:
        raise HTTPException(409, str(e))
    user_id = user.user_id

    def event_stream():
        for event in agent.generate(user_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/export.md")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = agent.state_for_user(db, user.user_id)
    if state.roadmap is None:
        raise HTTPException(404, "Generate your roadmap first.")
    return Response(
        to_markdown(state.roadmap, state.profile),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-career-roadmap.md"'},
    )
