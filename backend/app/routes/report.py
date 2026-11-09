from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from core.agents.report import agent
from core.agents.report.export import to_markdown, to_pdf
from core.agents.report.schemas import ReportState, TransitionReport
from core.auth import current_user
from core.db import get_db
from core.models import User

router = APIRouter(prefix="/api/report")


@router.get("", response_model=ReportState)
def get_report(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.state_for_user(db, user.user_id)


@router.post("/generate", response_model=ReportState)
def generate(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Blocking (one LLM call, about 10-20 s). The plain default text is used if the AI's text fails."""
    try:
        return agent.generate(db, user.user_id)
    except agent.NotReady as e:
        raise HTTPException(409, str(e))


def _saved(db: Session, user_id: str) -> TransitionReport:
    state = agent.state_for_user(db, user_id)
    if state.report is None:
        raise HTTPException(404, "Create your Transition Report first.")
    return state.report


@router.get("/export.md")
def export_md(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return Response(
        to_markdown(_saved(db, user.user_id)),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-career-transition-report.md"'},
    )


@router.get("/export.pdf")
def export_pdf(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return Response(
        to_pdf(_saved(db, user.user_id)),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ai-career-transition-report.pdf"'},
    )
