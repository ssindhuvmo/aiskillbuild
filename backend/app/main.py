import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.routes import (
    account, auth, dashboard, feedback, gaps, intake, jobs, progress, report, resources, resume, resume_optimizer,
    roadmap,
)
from core.config import FRONTEND_ORIGIN, SESSION_COOKIE_SECURE, SESSION_MAX_AGE, SESSION_SECRET
from core.db import init_db


# Show the app's own INFO lines (e.g. web searches per run) alongside uvicorn's log.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
logging.getLogger("core").addHandler(_handler)
logging.getLogger("core").setLevel(logging.INFO)


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
app.include_router(resume.router)
app.include_router(gaps.router)
app.include_router(resources.router)
app.include_router(roadmap.router)
app.include_router(report.router)
app.include_router(dashboard.router)
app.include_router(progress.router)
app.include_router(jobs.router)
app.include_router(resume_optimizer.router)
app.include_router(feedback.router)
app.include_router(account.router)
