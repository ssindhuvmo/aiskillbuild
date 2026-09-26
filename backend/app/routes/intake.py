import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core import repository
from core.agents.intake import agent
from core.config import load_domains
from core.db import SessionLocal
from core.repository import ValidationFailed
from core.schemas import ChatIn, IntakeState, ProfileOut, ProfileUpdate

router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _check_user_id(user_id: str) -> str:
    user_id = user_id.strip()
    if not user_id or len(user_id) > 64:
        raise HTTPException(400, "User identifier must be 1–64 characters.")
    return user_id


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/domains")
def domains():
    return {"domains": load_domains()}


@router.get("/users/{user_id}/intake", response_model=IntakeState)
def get_intake(user_id: str, db: Session = Depends(get_db)):
    user_id = _check_user_id(user_id)
    return IntakeState(
        user_id=user_id,
        messages=repository.get_messages(db, user_id),
        profile=repository.get_profile(db, user_id),
    )


@router.post("/users/{user_id}/intake/chat")
def chat(user_id: str, body: ChatIn):
    user_id = _check_user_id(user_id)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty.")

    def event_stream():
        # Own session: the generator outlives the request-scoped dependency.
        db = SessionLocal()
        try:
            for event in agent.run_turn(db, user_id, message):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.put("/users/{user_id}/profile", response_model=ProfileOut)
def update_profile(user_id: str, body: ProfileUpdate, db: Session = Depends(get_db)):
    user_id = _check_user_id(user_id)
    try:
        return repository.update_profile(db, user_id, body)
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})


@router.post("/users/{user_id}/profile/confirm", response_model=ProfileOut)
def confirm_profile(user_id: str, db: Session = Depends(get_db)):
    user_id = _check_user_id(user_id)
    try:
        return repository.confirm_profile(db, user_id)
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})
