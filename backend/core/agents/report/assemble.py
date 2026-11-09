"""Assembles the Transition Report from saved data (pure: no DB, no LLM).

Only `narrative` comes from the LLM (or its plain default); everything else is copied or summed here from the
profile, the reviewed resume, the gap analysis, the approved list and the roadmap with its tracking.
"""
from dataclasses import dataclass
from datetime import datetime

from core.agents.course_search.schemas import ApprovedList
from core.agents.gap_analysis.schemas import GapAnalysis
from core.agents.intake.validation import CONSTRAINT_FLAGS, CONSTRAINT_LABELS, PREFERENCES
from core.agents.report.schemas import (
    CareerGoal, CurrentProfile, PlanItem, ReportMilestone, ReportNarrative, ReportPhase, ReportProject,
    ReportResource, ResumeSummary, TransitionReport,
)
from core.agents.resume_parser.schemas import ResumeData
from core.agents.scheduler.schemas import Roadmap, RoadmapTracking
from core.agents.scheduler.tracking import milestone_id, tasks
from core.schemas import ProfileOut


@dataclass
class ReportData:
    """Everything the report is built from (repository.report_data)."""

    profile: ProfileOut
    analysis: GapAnalysis
    resume: ResumeData | None
    approved: ApprovedList | None  # the list the roadmap was built from
    roadmap: Roadmap
    tracking: RoadmapTracking


def _resume(data: ResumeData | None) -> ResumeSummary | None:
    if data is None:
        return None
    return ResumeSummary(
        roles=[f"{r.title}, {r.employer} ({r.start}–{r.end or 'present'})" for r in data.roles],
        skills=data.skills,
        certifications=[c.name + (f" ({c.issuer})" if c.issuer else "") for c in data.certifications],
        education=[f"{e.qualification}, {e.institution}" + (f" ({e.year})" if e.year else "") for e in data.education],
    )


def constraint_lines(constraints: dict | None) -> list[str]:
    c = constraints or {}
    lines = []
    if c.get("budget") == "free_only":
        lines.append("Budget: free resources only")
    elif c.get("budget") == "monthly":
        lines.append(f"Budget: up to {c.get('monthly_budget')} a month")
    lines += [CONSTRAINT_LABELS[f] for f in CONSTRAINT_FLAGS if c.get(f)]
    if c.get("other"):
        lines.append(c["other"])
    return lines


def _profile(p: ProfileOut, resume: ResumeData | None) -> CurrentProfile:
    return CurrentProfile(
        years_experience=p.years_experience,
        ai_level=p.ai_level,
        capabilities=p.capabilities,
        learning_preferences=[PREFERENCES.get(k, k) for k in p.learning_preferences or []],
        constraints=constraint_lines(p.constraints),
        additional_context=p.additional_context or None,
        resume=_resume(resume),
    )


def _phase_of_gap(roadmap: Roadmap) -> dict[str, int]:
    found: dict[str, int] = {}
    for phase in roadmap.phases:
        for gap in phase.gaps:
            found.setdefault(gap, phase.number)
    return found


def build(data: ReportData, narrative: ReportNarrative, source: str, written_at: datetime) -> TransitionReport:
    p, roadmap, tracking = data.profile, data.roadmap, data.tracking
    phase_of = _phase_of_gap(roadmap)
    scheduled = {t.resource.id for _, t, _ in tasks(roadmap) if t.resource}
    approved = data.approved.resources if data.approved else []

    resource_hours: dict[str, int] = {}
    for item in approved:
        if item.resource.id in scheduled:
            resource_hours[item.gaps[0]] = resource_hours.get(item.gaps[0], 0) + item.resource.hours
    # Study order: the roadmap's phase order, then any plan gap none of whose resources fit.
    order = list(phase_of)
    ordered = sorted(data.analysis.gaps, key=lambda g: order.index(g.skill) if g.skill in phase_of else len(order))
    plan = [
        PlanItem(skill=g.skill, priority=g.priority, current_level=g.current_level, target_level=g.target_level,
                 phase=phase_of.get(g.skill), resource_hours=resource_hours.get(g.skill, 0))
        for g in ordered
    ]

    phase_status = {t.number: t.status for t in tracking.phases}
    phases = []
    for phase in roadmap.phases:
        months = [m for m in roadmap.months if m.number in phase.months]
        phases.append(ReportPhase(
            number=phase.number, name=phase.name, months=phase.months, gaps=phase.gaps,
            hours=sum(m.hours for m in months), status=phase_status.get(phase.number, "not_started"),
            milestones=[
                ReportMilestone(month=m.number, theme=m.theme, milestone=m.milestone,
                                due=tracking.items[milestone_id(m.number)].due,
                                done=tracking.items[milestone_id(m.number)].done)
                for m in months
            ],
        ))

    return TransitionReport(
        written_at=written_at,
        narrative_source=source,
        career_goal=CareerGoal(current_role=p.current_role or "", target_role=p.target_role or "",
                               domain=p.domain or "", hours_per_week=roadmap.hours_per_week, weeks=roadmap.weeks),
        current_profile=_profile(p, data.resume),
        career_fit=narrative.career_fit,
        transferable_skills=data.analysis.strengths,
        gaps=data.analysis.gaps,
        later_gaps=data.analysis.later_gaps,
        strategy=narrative.strategy,
        learning_plan=plan,
        resources=[
            ReportResource(title=i.resource.title, provider=i.resource.provider, url=str(i.resource.url),
                           format=i.resource.format, cost=i.resource.cost, hours=i.resource.hours, gap=i.gaps[0],
                           scheduled=i.resource.id in scheduled)
            for i in approved
        ],
        start_date=tracking.start_date,
        planned_hours=roadmap.total_hours,
        budget_hours=roadmap.budget_hours,
        roadmap=phases,
        projects=[ReportProject(phase=ph.number, **ph.project.model_dump()) for ph in roadmap.phases],
        next_steps=tracking.next_steps,
    )


def default_narrative(data: ReportData) -> ReportNarrative:
    """Plain text from the saved analysis and roadmap, used when the AI's text isn't available."""
    p = data.profile
    strengths = ", ".join(s.skill for s in data.analysis.strengths[:4])
    top = ", ".join(g.skill for g in data.analysis.gaps[:3])
    career_fit = (
        f"You are moving from {p.current_role} to {p.target_role} in {p.domain}. "
        f"Strengths that carry over: {strengths}. The gaps that matter most: {top}.\n\n"
        f"{data.analysis.rationale}"
    )
    phases = " ".join(
        f"Phase {ph.number} ({ph.name}) covers {', '.join(ph.gaps) or 'project work'} and ends with the "
        f"portfolio project \"{ph.project.title}\"."
        for ph in data.roadmap.phases
    )
    strategy = (
        f"Work through the roadmap phase by phase at about {data.roadmap.hours_per_week} hours a week. {phases} "
        f"Publish each project with a short write-up so employers in {p.domain} can see the new skills next to "
        f"your experience as a {p.current_role}."
    )
    return ReportNarrative(career_fit=career_fit[:2000], strategy=strategy[:2000])
