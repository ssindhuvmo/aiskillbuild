import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from core import repository
from core.agents.resume_parser import agent
from core.agents.resume_parser.extract import MAX_BYTES, InvalidFile
from core.agents.resume_parser.schemas import ResumeData
from core.auth import current_user
from core.db import get_db
from core.llm import LLMUnavailable, friendly_error
from core.models import User
from core.repository import NotReady, ValidationFailed
from core.schemas import ResumeState

router = APIRouter(prefix="/api/resume")


@router.get("", response_model=ResumeState)
def get_resume(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return repository.get_resume_state(db, user.user_id)


# Plain def: FastAPI runs it in a worker thread, so the 10-20 s parse doesn't block other requests.
@router.post("", response_model=ResumeState)
def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    content = file.file.read(MAX_BYTES + 1)  # one byte over is enough to reject it
    try:
        return agent.upload_for_user(db, user.user_id, file.filename, content)
    except InvalidFile as e:
        raise HTTPException(e.status, str(e))
    except agent.ResumeParseFailed:
        raise HTTPException(502, "The AI couldn't read your resume reliably. Please try again, or skip this step.")
    except (LLMUnavailable, anthropic.APIError) as e:  # missing key, auth, rate limit, connection
        raise HTTPException(503, friendly_error(e))


@router.put("", response_model=ResumeState)
def save(body: ResumeData, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return agent.save_for_user(db, user.user_id, body)
    except NotReady as e:
        raise HTTPException(409, str(e))
    except ValidationFailed as e:
        raise HTTPException(422, {"errors": e.errors})


@router.delete("", response_model=ResumeState)
def delete(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return agent.delete_for_user(db, user.user_id)
