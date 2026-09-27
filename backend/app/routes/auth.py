from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core import auth, repository
from core.db import get_db
from core.models import User
from core.schemas import GoogleLoginIn, UserOut

router = APIRouter(prefix="/api/auth")


@router.post("/google", response_model=UserOut)
def google_login(body: GoogleLoginIn, request: Request, db: Session = Depends(get_db)):
    try:
        claims = auth.verify_google_token(body.credential)
    except auth.InvalidToken:
        raise HTTPException(401, "Google sign-in failed. Please try again.")
    user = repository.upsert_google_user(db, claims)
    request.session.clear()
    request.session[auth.SESSION_KEY] = user.user_id
    return UserOut(email=user.email, name=user.name, picture=user.picture)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth.current_user)):
    return UserOut(email=user.email, name=user.name, picture=user.picture)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}
