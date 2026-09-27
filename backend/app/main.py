from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.routes import auth, intake
from core.config import FRONTEND_ORIGIN, SESSION_COOKIE_SECURE, SESSION_MAX_AGE, SESSION_SECRET
from core.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Career Strategist", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
# Signed (not encrypted) cookie holding only the user's Google sub; httpOnly by default.
# SameSite=Lax keeps it off cross-site POSTs.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
)
app.include_router(auth.router)
app.include_router(intake.router)
