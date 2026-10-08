import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.agents.course_search import agent
from core.auth import current_user
from core.db import SessionLocal, get_db
from core.models import User
from core.repository import NotReady, ValidationFailed
from core.schemas import ChatIn, RemoveIn, ResourceState

router = APIRouter(prefix="/api/resources")


@router.get("", response_model=ResourceState)
def get_resources(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.state_for_user(db, user.user_id)


@router.post("/search", response_model=ResourceState)
def search(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.run_for_user(db, user.user_id)
    except agent.GapsNotConfirmed as e:
        raise HTTPException(409, str(e))


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty.")
    user_id = user.user_id
    try:
        agent.check_ready(db, user_id)
    except NotReady as e:
        raise HTTPException(409, str(e))

    def event_stream():
        # Own session: the generator outlives the request-scoped dependency.
        db = SessionLocal()
        try:
            for event in agent.chat_turn(db, user_id, message):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/remove", response_model=ResourceState)
def remove(body: RemoveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.remove_for_user(db, user.user_id, body.resource_id)
    except NotReady as e:
        raise HTTPException(409, str(e))
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})


@router.post("/approve", response_model=ResourceState)
def approve(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.approve_for_user(db, user.user_id)
    except NotReady as e:
        raise HTTPException(409, str(e))
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})
