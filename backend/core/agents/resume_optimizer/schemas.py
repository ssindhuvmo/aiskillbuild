"""Resume Optimizer (milestone 13, BR-27).

Evidence is what the user can truthfully claim, gathered in Python: the reviewed resume plus what they have
completed on the roadmap (plan skills, phase portfolio projects, courses). TailoredText is all the model
writes: text, plus references into Evidence. Employers, titles, dates, education and certifications are
copied by Python from the resume (assemble.build), so the model cannot invent them.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.agents.job_search.schemas import JobView, MissingSkill
from core.agents.resume_parser.schemas import Certification, Education, ResumeData
from core.agents.scheduler.schemas import Project

MAX_ROLES = 20
MAX_HIGHLIGHTS = 6
MAX_LINE = 300


def _lines(v: list[str]) -> list[str]:
    if any(not s.strip() or len(s) > MAX_LINE for s in v):
        raise ValueError(f"each line must be 1-{MAX_LINE} characters")
    return [s.strip() for s in v]


# --- Evidence (Python) --------------------------------------------------------------------


class DoneProject(BaseModel):
    id: str  # "p<phase>"
    phase: int
    project: Project


class DoneCourse(BaseModel):
    id: str  # the resource id
    title: str
    provider: str
    skills: list[str] = []  # the plan gaps it was chosen for


class PendingProject(BaseModel):
    id: str
    phase: int
    months: list[int]
    title: str


class Evidence(BaseModel):
    name: str
    email: str | None = None
    current_role: str
    target_role: str
    years_experience: int | None = None
    resume: ResumeData  # empty when the user has no reviewed resume
    has_resume: bool
    skills: list[str]  # every skill the resume may list (resume, confirmed strengths, completed gaps, ratings)
    completed_gaps: list[str]
    projects: list[DoneProject]
    courses: list[DoneCourse]
    pending_gaps: list[str]  # plan gaps not completed
    pending_projects: list[PendingProject]


# --- What the model writes ------------------------------------------------------------------


class RoleText(BaseModel):
    ref: int = Field(ge=0, lt=MAX_ROLES)  # index into resume.roles
    highlights: list[str] = Field(default=[], max_length=MAX_HIGHLIGHTS)

    @field_validator("highlights")
    @classmethod
    def _check(cls, v: list[str]) -> list[str]:
        return _lines(v)


class ProjectText(BaseModel):
    ref: str = Field(min_length=1, max_length=20)  # a completed project's id
    bullets: list[str] = Field(min_length=1, max_length=4)

    @field_validator("bullets")
    @classmethod
    def _check(cls, v: list[str]) -> list[str]:
        return _lines(v)


class ToAdd(BaseModel):
    kind: Literal["skill", "project", "detail"]
    name: str = Field(min_length=1, max_length=160)  # skill: a plan gap or required skill; project: its title
    note: str = Field(min_length=1, max_length=300)


class TailoredText(BaseModel):
    headline: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=800)
    roles: list[RoleText] = Field(default=[], max_length=MAX_ROLES)
    skills: list[str] = Field(default=[], max_length=40)
    projects: list[ProjectText] = Field(default=[], max_length=3)
    courses: list[str] = Field(default=[], max_length=10)  # completed course ids
    keywords: list[str] = Field(default=[], max_length=12)  # from the posting, now in the resume
    to_add: list[ToAdd] = Field(default=[], max_length=10)

    @field_validator("skills", "keywords")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        if any(not s.strip() or len(s) > 80 for s in v):
            raise ValueError("each item must be 1-80 characters")
        return [s.strip() for s in v]


class EditsIn(BaseModel):
    """The user's own changes. Employers, titles, dates, education and certifications are not editable here
    (they come from the reviewed resume)."""

    headline: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=800)
    roles: list[list[str]] = Field(default=[], max_length=MAX_ROLES)  # highlights, in the tailored role order
    skills: list[str] = Field(default=[], max_length=40)
    projects: list[list[str]] = Field(default=[], max_length=3)  # bullets, in the tailored project order

    @field_validator("roles", "projects")
    @classmethod
    def _groups(cls, v: list[list[str]]) -> list[list[str]]:
        if any(len(g) > MAX_HIGHLIGHTS for g in v):
            raise ValueError(f"at most {MAX_HIGHLIGHTS} lines each")
        return [_lines([s for s in g if s.strip()]) for g in v]

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s.strip()]
        if any(len(s) > 80 for s in v):
            raise ValueError("each skill must be 1-80 characters")
        return v


# --- The resume document and the page ------------------------------------------------------


class Segment(BaseModel):
    text: str
    added: bool = False  # added or reworded compared with the current resume


class DocRole(BaseModel):
    title: str
    employer: str
    dates: str  # "2019-03 – present"
    highlights: list[list[Segment]]


class DocSkill(BaseModel):
    name: str
    added: bool = False


class DocProject(BaseModel):
    title: str
    dataset: str
    bullets: list[list[Segment]]
    added: bool = True


class DocCourse(BaseModel):
    title: str
    provider: str
    added: bool = True


class ResumeDoc(BaseModel):
    """A resume ready to show or export. Plain text is the join of each segment list."""

    name: str
    email: str | None = None
    headline: list[Segment]
    summary: list[Segment]
    roles: list[DocRole]
    skills: list[DocSkill]
    projects: list[DocProject] = []
    courses: list[DocCourse] = []
    achievements: list[str] = []
    education: list[str] = []
    certifications: list[str] = []


class OptimizerView(BaseModel):
    job: JobView
    original: ResumeDoc
    tailored: ResumeDoc
    keywords: list[str]
    to_add: list[ToAdd]
    improvements: list[MissingSkill]  # the job's skills not covered today
    placeholders: int  # "[...]" left for the user to fill in
    source: Literal["ai", "default"]
    edited: bool
    stale: bool  # the user's progress or resume changed since it was written
    notice: str | None = None
    has_resume: bool
    updated_at: datetime
    text: str  # plain text for Copy Content


class JobOption(BaseModel):
    id: str
    title: str
    company: str
    score: int
    has_version: bool = False
    stale: bool = False
    updated_at: datetime | None = None


class OptimizerState(BaseModel):
    can_optimize: bool  # a gap analysis exists
    has_resume: bool
    jobs: list[JobOption]


def _education(e: Education) -> str:
    return ", ".join(str(x) for x in (e.qualification, e.institution, e.year) if x)


def _certification(c: Certification) -> str:
    return ", ".join(str(x) for x in (c.name, c.issuer, c.year) if x)
