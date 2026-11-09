import json

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core import repository
from core.agents.scheduler import agent
from core.agents.scheduler.export import to_markdown, to_pdf
from core.auth import current_user
from core.db import get_db
from core.models import User
from core.schemas import RoadmapItemIn, RoadmapState, StartDateIn

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


@router.post("/refresh")
def refresh(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """SSE (Progress Review, "Refresh my plan"): done work stays, the remaining weeks are replanned and the
    phases that are not over get new text (see agent.refresh)."""
    try:
        agent.check_refresh(db, user.user_id)
    except (agent.NoCurrentRoadmap, agent.AlreadyRunning) as e:
        raise HTTPException(409, str(e))
    user_id = user.user_id

    def event_stream():
        for event in agent.refresh(user_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.put("/start-date", response_model=RoadmapState)
def set_start_date(body: StartDateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        repository.set_start_date(db, user.user_id, body.start_date)
    except repository.NotReady as e:
        raise HTTPException(404, str(e))
    return agent.state_for_user(db, user.user_id)


@router.put("/items", response_model=RoadmapState)
def set_item(body: RoadmapItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        repository.set_item_done(db, user.user_id, body.item_id, body.done)
    except repository.NotReady as e:
        raise HTTPException(404, str(e))
    except repository.ValidationFailed as e:
        raise HTTPException(422, e.errors["item_id"])
    return agent.state_for_user(db, user.user_id)


def _saved(db: Session, user_id: str) -> RoadmapState:
    state = agent.state_for_user(db, user_id)
    if state.roadmap is None:
        raise HTTPException(404, "Generate your roadmap first.")
    return state


@router.get("/export.md")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = _saved(db, user.user_id)
    return Response(
        to_markdown(state.roadmap, state.profile, state.tracking),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-career-roadmap.md"'},
    )


@router.get("/export.pdf")
def export_pdf(user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = _saved(db, user.user_id)
    return Response(
        to_pdf(state.roadmap, state.profile, state.tracking),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ai-career-roadmap.pdf"'},
    )
