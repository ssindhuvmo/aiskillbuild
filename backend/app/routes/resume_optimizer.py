from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from core import repository
from core.agents.resume_optimizer import agent
from core.agents.resume_optimizer.assemble import file_stem
from core.agents.resume_optimizer.export import to_docx, to_pdf
from core.agents.resume_optimizer.schemas import EditsIn, OptimizerState, OptimizerView
from core.auth import current_user
from core.db import get_db
from core.models import User

router = APIRouter(prefix="/api/resume-optimizer")

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("", response_model=OptimizerState)
def get_state(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.state_for_user(db, user.user_id)


@router.get("/{job_id}", response_model=OptimizerView)
def get_version(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.view_for_user(db, user.user_id, job_id)
    except agent.NotFound as e:
        raise HTTPException(404, str(e))


@router.post("/{job_id}", response_model=OptimizerView)
def optimize(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Blocking (one LLM call, about 15-30 s). Your resume plus completed work is used if the AI's text fails."""
    try:
        return agent.optimize(db, user.user_id, job_id)
    except (agent.NoAnalysis, agent.AlreadyRunning) as e:
        raise HTTPException(409, str(e))
    except agent.UnknownJob as e:
        raise HTTPException(422, str(e))


@router.put("/{job_id}", response_model=OptimizerView)
def save_edits(job_id: str, body: EditsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.save_edits(db, user.user_id, job_id, body)
    except agent.NotFound as e:
        raise HTTPException(404, str(e))
    except repository.ValidationFailed as e:
        raise HTTPException(422, e.errors)


@router.delete("/{job_id}/edits", response_model=OptimizerView)
def reset_edits(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.reset_edits(db, user.user_id, job_id)
    except agent.NotFound as e:
        raise HTTPException(404, str(e))


def _document(db: Session, user_id: str, job_id: str):
    try:
        return agent.document(db, user_id, job_id)
    except agent.NotFound as e:
        raise HTTPException(404, str(e))


@router.get("/{job_id}/export.pdf")
def export_pdf(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, job = _document(db, user.user_id, job_id)
    return Response(to_pdf(doc), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{file_stem(job)}.pdf"'})


@router.get("/{job_id}/export.docx")
def export_docx(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, job = _document(db, user.user_id, job_id)
    return Response(to_docx(doc), media_type=DOCX,
                    headers={"Content-Disposition": f'attachment; filename="{file_stem(job)}.docx"'})
