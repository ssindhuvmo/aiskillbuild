"""Turn Evidence + TailoredText (+ the user's edits) into resume documents (pure: no DB, no LLM).

Employers, titles, dates, education and certifications are always copied from the resume here. `marked`
compares each tailored line with the current resume word by word, so the page can highlight what was added
or reworded.
"""
import re
from difflib import SequenceMatcher

from core.agents.job_search.matching import norm
from core.agents.job_search.schemas import Job, JobView
from core.agents.resume_optimizer.rules import PLACEHOLDER
from core.agents.resume_optimizer.schemas import (
    DocCourse, DocProject, DocRole, DocSkill, EditsIn, Evidence, ProjectText, ResumeDoc, RoleText, Segment,
    TailoredText, ToAdd, _certification, _education,
)
from core.agents.resume_parser.schemas import Role

TOKEN = re.compile(r"\S+\s*")


def dates(r: Role) -> str:
    return f"{r.start} – {r.end or 'present'}"


def plain(segments: list[Segment]) -> str:
    return "".join(s.text for s in segments)


def unchanged(text: str) -> list[Segment]:
    return [Segment(text=text)] if text else []


def added(text: str) -> list[Segment]:
    return [Segment(text=text, added=True)] if text else []


def _key(token: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", token.lower())


def marked(new: str, old: str | None) -> list[Segment]:
    """`new` split into segments, with the words that are not in `old` (in order) marked as added."""
    if not old:
        return added(new)
    a, b = TOKEN.findall(old), TOKEN.findall(new)
    out: list[Segment] = []
    matcher = SequenceMatcher(a=[_key(t) for t in a], b=[_key(t) for t in b], autojunk=False)
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        text = "".join(b[j1:j2])
        if not text:
            continue
        flag = tag != "equal"
        if out and out[-1].added == flag:
            out[-1].text += text
        else:
            out.append(Segment(text=text, added=flag))
    return out


def _closest(line: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    return max(candidates, key=lambda c: SequenceMatcher(a=_key(c), b=_key(line)).ratio())


def original_headline(e: Evidence) -> str:
    return e.resume.roles[0].title if e.resume.roles else e.current_role


def original(e: Evidence) -> ResumeDoc:
    r = e.resume
    return ResumeDoc(
        name=e.name, email=e.email,
        headline=unchanged(original_headline(e)), summary=[],
        roles=[DocRole(title=x.title, employer=x.employer, dates=dates(x),
                       highlights=[unchanged(h) for h in x.highlights]) for x in r.roles],
        skills=[DocSkill(name=s) for s in r.skills],
        achievements=r.achievements,
        education=[_education(x) for x in r.education],
        certifications=[_certification(x) for x in r.certifications],
    )


def with_edits(t: TailoredText, edits: dict | None) -> TailoredText:
    """The text with the user's saved edits applied (shapes were checked when they were saved)."""
    if not edits:
        return t
    ed = EditsIn.model_validate(edits)
    return t.model_copy(update={
        "headline": ed.headline, "summary": ed.summary, "skills": ed.skills,
        "roles": [RoleText(ref=r.ref, highlights=h) for r, h in zip(t.roles, ed.roles)],
        "projects": [ProjectText(ref=p.ref, bullets=b) for p, b in zip(t.projects, ed.projects)],
    })


def tailored(e: Evidence, t: TailoredText) -> ResumeDoc:
    r = e.resume
    have = {norm(s) for s in r.skills}
    projects = {p.id: p for p in e.projects}
    courses = {c.id: c for c in e.courses}
    return ResumeDoc(
        name=e.name, email=e.email,
        headline=marked(t.headline, original_headline(e)),
        summary=marked(t.summary, None),
        roles=[
            DocRole(title=r.roles[x.ref].title, employer=r.roles[x.ref].employer, dates=dates(r.roles[x.ref]),
                    highlights=[marked(h, _closest(h, r.roles[x.ref].highlights)) for h in x.highlights])
            for x in t.roles if x.ref < len(r.roles)
        ],
        skills=[DocSkill(name=s, added=norm(s) not in have) for s in t.skills],
        projects=[DocProject(title=projects[p.ref].project.title, dataset=projects[p.ref].project.dataset,
                             bullets=[added(b) for b in p.bullets])
                  for p in t.projects if p.ref in projects],
        courses=[DocCourse(title=courses[c].title, provider=courses[c].provider) for c in t.courses if c in courses],
        achievements=r.achievements,
        education=[_education(x) for x in r.education],
        certifications=[_certification(x) for x in r.certifications],
    )


def default_text(e: Evidence, view: JobView) -> TailoredText:
    """Used when the AI's text fails the checks or the LLM is unavailable: the resume as it is, plus everything
    completed on the roadmap, and "To add" from the job's missing skills and the unfinished projects."""
    r = e.resume
    summary = f"{e.current_role} building toward a {e.target_role} role"
    if e.completed_gaps:
        summary += f", with completed work in {', '.join(e.completed_gaps)}"
    claimed = {norm(s) for s in e.skills}
    to_add = [ToAdd(kind="skill", name=m.skill,
                    note=f"Covered in phase {m.phase} of your roadmap." if m.phase else "Not in your plan yet.")
              for m in view.missing if norm(m.skill) not in claimed]
    to_add += [ToAdd(kind="project", name=p.title, note=f"Phase {p.phase} portfolio project.")
               for p in e.pending_projects]
    return TailoredText(
        headline=original_headline(e), summary=summary + ".",
        roles=[RoleText(ref=i, highlights=x.highlights) for i, x in enumerate(r.roles)],
        skills=e.skills[:40],
        projects=[ProjectText(ref=p.id, bullets=p.project.deliverables[:4]) for p in e.projects[:3]],
        courses=[c.id for c in e.courses[:10]],
        to_add=to_add[:10],
    )


def placeholders(doc: ResumeDoc) -> int:
    return len(PLACEHOLDER.findall(to_text(doc)))


def to_text(doc: ResumeDoc) -> str:
    """Plain text of the resume (Copy Content), sections in export order."""
    lines = [doc.name]
    if doc.email:
        lines.append(doc.email)
    lines.append(plain(doc.headline))
    if doc.summary:
        lines += ["", "SUMMARY", plain(doc.summary)]
    if doc.roles:
        lines += ["", "EXPERIENCE"]
        for r in doc.roles:
            lines.append(f"{r.title} · {r.employer} · {r.dates}")
            lines += [f"- {plain(h)}" for h in r.highlights]
    if doc.projects:
        lines += ["", "PROJECTS"]
        for p in doc.projects:
            lines.append(f"{p.title} (dataset: {p.dataset})")
            lines += [f"- {plain(b)}" for b in p.bullets]
    if doc.skills:
        lines += ["", "SKILLS", ", ".join(s.name for s in doc.skills)]
    if doc.achievements:
        lines += ["", "ACHIEVEMENTS", *[f"- {a}" for a in doc.achievements]]
    if doc.courses:
        lines += ["", "COURSES AND PROFESSIONAL DEVELOPMENT", *[f"- {c.title}, {c.provider}" for c in doc.courses]]
    if doc.education:
        lines += ["", "EDUCATION", *[f"- {x}" for x in doc.education]]
    if doc.certifications:
        lines += ["", "CERTIFICATIONS", *[f"- {x}" for x in doc.certifications]]
    return "\n".join(lines) + "\n"


def file_stem(job: Job) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"resume {job.company} {job.title}".lower()).strip("-")
    return slug[:80] or "resume"
