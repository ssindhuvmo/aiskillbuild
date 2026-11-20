"""What the user can truthfully claim (pure: no DB, no LLM). repository.optimizer_evidence gathers the inputs.

- skills: the resume's skills, strengths the user or the resume confirmed (never "assumed"), plan gaps marked
  completed on Progress Review, and capability areas rated Intermediate or above.
- projects: a roadmap phase's portfolio project once every one of its project tasks is checked.
- courses: an approved resource marked Complete, or whose roadmap tasks are all checked.
Everything else the plan holds is pending: the optimizer may suggest it under "To add", never claim it.
"""
from core.agents.course_search.schemas import ApprovedList
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.job_search.matching import capability_skills, norm
from core.agents.resume_optimizer.schemas import DoneCourse, DoneProject, Evidence, PendingProject
from core.agents.resume_parser.schemas import ResumeData
from core.agents.scheduler.schemas import Roadmap
from core.agents.scheduler.tracking import tasks
from core.knowledge.schemas import Resource

CONFIRMED_SOURCES = {"resume", "user"}


def unique(names: list[str]) -> list[str]:
    seen, out = set(), []
    for n in names:
        if n.strip() and norm(n) not in seen:
            seen.add(norm(n))
            out.append(n)
    return out


def allowed_skills(resume: ResumeData, analysis: GapAnalysis, completed_gaps: list[str],
                   capabilities: dict[str, str]) -> list[str]:
    strengths = [s.skill for s in analysis.strengths if s.source in CONFIRMED_SOURCES]
    return unique([*resume.skills, *strengths, *completed_gaps, *capability_skills(capabilities)])


def projects(roadmap: Roadmap | None, done: set[str]) -> tuple[list[DoneProject], list[PendingProject]]:
    """Completed and pending phase projects. A phase's project tasks are the project tasks in its months."""
    if roadmap is None:
        return [], []
    by_week = {}
    for tid, task, week in tasks(roadmap):
        if task.kind == "project":
            by_week.setdefault(week, []).append(tid)
    month_weeks = {m.number: [w.number for w in m.weeks] for m in roadmap.months}
    finished, pending = [], []
    for phase in roadmap.phases:
        ids = [tid for month in phase.months for week in month_weeks.get(month, []) for tid in by_week.get(week, [])]
        pid = f"p{phase.number}"
        if ids and all(tid in done for tid in ids):
            finished.append(DoneProject(id=pid, phase=phase.number, project=phase.project))
        else:
            pending.append(PendingProject(id=pid, phase=phase.number, months=phase.months, title=phase.project.title))
    return finished, pending


def courses(approved: ApprovedList | None, roadmap: Roadmap | None, done: set[str],
            completed: dict[str, Resource]) -> list[DoneCourse]:
    """Resources marked Complete (`completed`: id -> Resource) and approved resources whose roadmap tasks are
    all checked, in approved-list order first."""
    gaps_of = {a.resource.id: a.gaps for a in approved.resources} if approved else {}
    resources = {a.resource.id: a.resource for a in approved.resources} if approved else {}
    task_ids: dict[str, list[str]] = {}
    if roadmap is not None:
        for tid, task, _ in tasks(roadmap):
            if task.resource is not None and task.kind in ("learn", "practice"):
                task_ids.setdefault(task.resource.id, []).append(tid)
    ids = [rid for rid in resources if task_ids.get(rid) and all(t in done for t in task_ids[rid])]
    ids += [rid for rid in completed if rid not in ids]
    found = []
    for rid in ids:
        r = completed.get(rid) or resources[rid]
        found.append(DoneCourse(id=rid, title=r.title, provider=r.provider, skills=gaps_of.get(rid, [])))
    return found


def build(name: str, email: str | None, current_role: str, target_role: str, years: int | None,
          resume: ResumeData | None, analysis: GapAnalysis, completed_gaps: list[str],
          capabilities: dict[str, str], roadmap: Roadmap | None, approved: ApprovedList | None,
          done: set[str], completed_resources: dict[str, Resource]) -> Evidence:
    source = resume or ResumeData()
    finished, pending = projects(roadmap, done)
    return Evidence(
        name=name, email=email, current_role=current_role, target_role=target_role, years_experience=years,
        resume=source, has_resume=resume is not None,
        skills=allowed_skills(source, analysis, completed_gaps, capabilities),
        completed_gaps=completed_gaps,
        projects=finished,
        courses=courses(approved, roadmap, done, completed_resources),
        pending_gaps=[g.skill for g in analysis.gaps if norm(g.skill) not in {norm(c) for c in completed_gaps}],
        pending_projects=pending,
    )
