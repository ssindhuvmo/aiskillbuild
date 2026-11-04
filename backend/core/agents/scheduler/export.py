"""Markdown export of a saved roadmap (pure: no LLM, no DB)."""
from core.agents.scheduler.schemas import Roadmap, RoadmapTask
from core.schemas import ProfileOut


def _task(task: RoadmapTask) -> str:
    line = f"- [ ] {task.title} ({task.hours} h)"
    if task.resource:
        line += f" — [{task.resource.title}]({task.resource.url})"
    return line


def to_markdown(roadmap: Roadmap, profile: ProfileOut) -> str:
    phase_ending = {p.months[-1]: p for p in roadmap.phases}
    phase_starting = {p.months[0]: p for p in roadmap.phases}
    lines = [
        f"# AI roadmap: {profile.current_role} → {profile.target_role}",
        "",
        f"{profile.domain} · {roadmap.weeks} weeks at {roadmap.hours_per_week} hours per week · "
        f"{roadmap.total_hours} of {roadmap.budget_hours} budgeted hours planned",
    ]
    for month in roadmap.months:
        phase = phase_starting.get(month.number)
        if phase:
            lines += ["", f"## Phase {phase.number}: {phase.name} (months {phase.months[0]}–{phase.months[-1]})"]
        lines += ["", f"### Month {month.number}: {month.theme} ({month.hours} h)", "", month.summary]
        for week in month.weeks:
            lines += ["", f"#### Week {week.number}: {week.focus} ({week.hours} h)", ""]
            lines += [_task(t) for t in week.tasks] or ["_Nothing planned: catch up or rest._"]
        lines += ["", f"**Milestone:** {month.milestone}"]
        phase = phase_ending.get(month.number)
        if phase:
            project = phase.project
            lines += [
                "",
                f"### Portfolio project (phase {phase.number}): {project.title}",
                "",
                project.problem,
                "",
                f"**Dataset:** {project.dataset}",
                "",
                "**Deliverables:**",
                "",
                *[f"- {d}" for d in project.deliverables],
            ]
    if roadmap.unscheduled:
        lines += ["", "## Approved but not scheduled", "", "These did not fit in the hour budget:", ""]
        lines += [f"- [{r.title}]({r.url}) ({r.hours} h)" for r in roadmap.unscheduled]
    return "\n".join(lines) + "\n"
