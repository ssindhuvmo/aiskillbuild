"""Job Match (milestone 12). The search model records JobFindings (copied from the postings it found); the
assessment model maps each required skill to one of the user's skills or plan gaps and writes the
explanation. The match score, the salary numbers and every link are worked out in Python."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
LinkStatus = Literal["ok", "blocked"]  # blocked: the site refuses automated checks (e.g. 403), kept unverified
MAX_REQUIRED = 15


class JobQuery(BaseModel):
    """What the user searched for; saved with the results so Refresh repeats it."""

    location: str = Field(default="", max_length=120)  # "" = anywhere
    remote: bool = False
    hybrid: bool = False


class JobFinding(BaseModel):
    """One posting as the search model recorded it. Text is copied from the posting, never invented."""

    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    location: str = Field(default="", max_length=120)
    work_mode: WorkMode = "unknown"
    salary: str | None = Field(default=None, max_length=120)  # as stated in the posting
    experience: str | None = Field(default=None, max_length=80)  # as stated, e.g. "5+ years"
    summary: str = Field(min_length=1, max_length=800)
    required_skills: list[str] = Field(min_length=1, max_length=MAX_REQUIRED)


# --- What the assessment model returns -------------------------------------------------


class SkillMatch(BaseModel):
    required: str = Field(min_length=1, max_length=120)  # one of the job's required skills, exactly
    have: str | None = Field(default=None, max_length=120)  # one of the user's skills, exactly, or null
    in_plan: str | None = Field(default=None, max_length=120)  # one of the user's plan gaps, exactly, or null


class JobAssessment(BaseModel):
    job_id: str = Field(min_length=1, max_length=40)
    matches: list[SkillMatch] = Field(min_length=1, max_length=MAX_REQUIRED)
    explanation: str = Field(min_length=1, max_length=600)  # no numbers, scores or links


class Assessments(BaseModel):
    jobs: list[JobAssessment] = Field(min_length=1, max_length=20)


# --- Saved -------------------------------------------------------------------------------


class Job(BaseModel):
    id: str  # job-<sha1 of the url>
    title: str
    company: str
    url: str
    location: str = ""
    work_mode: WorkMode = "unknown"
    salary: str | None = None
    salary_min: int | None = None  # parsed from `salary` in Python (annual amounts only)
    salary_max: int | None = None
    experience: str | None = None
    summary: str
    required_skills: list[str]
    link: LinkStatus = "ok"
    found_on: date
    matches: list[SkillMatch] = []
    explanation: str = ""
    explained_by: Literal["ai", "default"] = "ai"


# --- What the page gets -------------------------------------------------------------------


class MissingSkill(BaseModel):
    skill: str
    in_plan: str | None = None  # the plan gap that covers it
    phase: int | None = None  # the roadmap phase that studies that gap


class JobView(BaseModel):
    job: Job
    score: int  # 0-100: share of the required skills the user has today
    have: list[str]  # required skills covered
    missing: list[MissingSkill]
    saved: bool = False
    applied: bool = False
    applied_at: datetime | None = None


class JobState(BaseModel):
    status: Literal["none", "ready"]
    can_search: bool  # a gap analysis exists (the skills to match against)
    sites: list[str]  # the allowlist searched (JOB_SITES)
    query: JobQuery
    found_at: datetime | None = None
    notice: str | None = None
    jobs: list[JobView] = []  # current results, best match first
    kept: list[JobView] = []  # saved or applied jobs that are not in the current results


class JobMarkIn(BaseModel):
    """Save Job / Mark as applied. Fields left out stay as they are."""

    job_id: str = Field(min_length=1, max_length=40)
    saved: bool | None = None
    applied: bool | None = None
