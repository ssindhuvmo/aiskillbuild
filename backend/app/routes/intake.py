import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core import repository
from core.agents.intake import agent
from core.auth import current_user
from core.config import load_domains
from core.db import SessionLocal, get_db
from core.models import User
from core.repository import ValidationFailed
from core.schemas import ChatIn, IntakeState, ProfileOut, ProfileUpdate

# Every route acts only on the signed-in user's data; the user comes from the session.
router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/domains")
def domains(_: User = Depends(current_user)):
    return {"domains": load_domains()}


@router.get("/intake", response_model=IntakeState)
def get_intake(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return repository.get_intake_state(db, user.user_id)


@router.post("/intake/chat")
def chat(body: ChatIn, user: User = Depends(current_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty.")
    user_id = user.user_id

    def event_stream():
        # Own session: the generator outlives the request-scoped dependency.
        db = SessionLocal()
        try:
            for event in agent.run_turn(db, user_id, message):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.put("/profile", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return repository.update_profile(db, user.user_id, body)
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})


@router.post("/profile/confirm", response_model=ProfileOut)
def confirm_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return repository.confirm_profile(db, user.user_id)
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})
