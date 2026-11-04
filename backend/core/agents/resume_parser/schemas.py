"""The resume parser's output. ResumeData is also the JSON schema the model answers in (structured
outputs) and what the user edits on the review screen; Pydantic re-validates both, including the
limits the API schema cannot express."""
import re

from pydantic import BaseModel, Field, field_validator

DATE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")  # "YYYY-MM" or "YYYY"


def _date(value: str | None) -> str | None:
    if value is not None and not DATE.match(value):
        raise ValueError('use "YYYY-MM" or "YYYY"')
    return value


class Role(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    employer: str = Field(min_length=1, max_length=120)
    start: str  # "YYYY-MM" or "YYYY"
    end: str | None = None  # None = present
    highlights: list[str] = Field(default=[], max_length=5)

    @field_validator("start", "end")
    @classmethod
    def _dates(cls, v: str | None) -> str | None:
        return _date(v)

    @field_validator("highlights")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        if any(len(h) > 300 for h in v):
            raise ValueError("keep each highlight under 300 characters")
        return v


class Education(BaseModel):
    qualification: str = Field(min_length=1, max_length=160)
    institution: str = Field(min_length=1, max_length=160)
    year: int | None = None


class Certification(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    issuer: str | None = Field(default=None, max_length=120)
    year: int | None = None


class ResumeData(BaseModel):
    skills: list[str] = Field(default=[], max_length=60)
    roles: list[Role] = Field(default=[], max_length=20)  # most recent first
    education: list[Education] = Field(default=[], max_length=10)
    certifications: list[Certification] = Field(default=[], max_length=20)
    achievements: list[str] = Field(default=[], max_length=15)
    industry: str | None = Field(default=None, max_length=100)

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        if any(not s.strip() or len(s) > 80 for s in v):
            raise ValueError("each skill must be 1-80 characters")
        return v

    @field_validator("achievements")
    @classmethod
    def _achievements(cls, v: list[str]) -> list[str]:
        if any(not a.strip() or len(a) > 300 for a in v):
            raise ValueError("each achievement must be 1-300 characters")
        return v

    def is_empty(self) -> bool:
        return not (self.skills or self.roles or self.education or self.certifications or self.achievements)


class ResumeDraft(BaseModel):
    """The parser's result awaiting review. `dropped` lists what failed the checks against the resume
    text and was left out (the review screen asks the user to add anything that is missing)."""

    data: ResumeData
    dropped: list[str] = []
