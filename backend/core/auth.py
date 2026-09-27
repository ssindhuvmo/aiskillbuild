"""Google sign-in: ID-token verification and the current-user dependency."""
from fastapi import Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from core.config import GOOGLE_CLIENT_ID
from core.db import get_db
from core.models import User

SESSION_KEY = "uid"
_transport = google_requests.Request()  # caches Google's signing certs between calls


class InvalidToken(Exception):
    pass


def verify_google_token(credential: str) -> dict:
    """Return the verified claims of a Google ID token (signature, audience, issuer
    and expiry are checked). Tests replace this function so they need no network."""
    try:
        claims = id_token.verify_oauth2_token(credential, _transport, GOOGLE_CLIENT_ID)
    except ValueError as e:
        raise InvalidToken(str(e)) from e
    if not claims.get("email_verified"):
        raise InvalidToken("Google account email is not verified.")
    return claims


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get(SESSION_KEY)
    user = db.get(User, uid) if uid else None
    if user is None:
        request.session.clear()
        raise HTTPException(401, "Please sign in.")
    return user
