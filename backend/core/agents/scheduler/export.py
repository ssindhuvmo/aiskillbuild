"""Markdown and PDF exports of a saved roadmap with its tracking (pure: no LLM, no DB)."""
from datetime import date

from core.agents.scheduler.schemas import Roadmap, RoadmapTracking
from core.agents.scheduler.tracking import milestone_id, task_id
from core.pdf import Document
from core.schemas import ProfileOut

STATUS = {
    "done": "Done", "overdue": "Overdue", "this_week": "This week", "not_started": "Not started",
    "in_progress": "In progress", "empty": "Nothing planned",
}


def day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _title(profile: ProfileOut) -> str:
    return f"AI roadmap: {profile.current_role} → {profile.target_role}"


def _summary(roadmap: Roadmap, profile: ProfileOut, tracking: RoadmapTracking) -> str:
    return (
        f"{profile.domain} · {roadmap.weeks} weeks at {roadmap.hours_per_week} hours per week · started "
        f"{day(tracking.start_date)} · {roadmap.total_hours} of {roadmap.budget_hours} budgeted hours planned · "
        f"{tracking.done_tasks} of {tracking.total_tasks} tasks done"
    )


def next_step_text(step) -> str:
    when = f"overdue since {day(step.due)}" if step.overdue else f"week {step.week}, due {day(step.due)}"
    return f"{step.title} ({step.hours} h, {when})"


def _phases_by_month(roadmap: Roadmap):
    return {p.months[0]: p for p in roadmap.phases}, {p.months[-1]: p for p in roadmap.phases}


def to_markdown(roadmap: Roadmap, profile: ProfileOut, tracking: RoadmapTracking) -> str:
    starting, ending = _phases_by_month(roadmap)
    weeks = {w.number: w for w in tracking.weeks}
    phases = {p.number: p for p in tracking.phases}
    lines = [f"# {_title(profile)}", "", _summary(roadmap, profile, tracking)]
    if tracking.next_steps:
        lines += ["", "## Immediate next steps", ""]
        lines += [f"{n}. {next_step_text(s)}" for n, s in enumerate(tracking.next_steps, start=1)]
    for month in roadmap.months:
        phase = starting.get(month.number)
        if phase:
            t = phases[phase.number]
            lines += ["", f"## Phase {phase.number}: {phase.name} (months {phase.months[0]}–{phase.months[-1]})", "",
                      f"{STATUS[t.status]} · {t.priority} priority"]
        lines += ["", f"### Month {month.number}: {month.theme} ({month.hours} h)", "", month.summary]
        for week in month.weeks:
            w = weeks[week.number]
            lines += ["", f"#### Week {week.number}: {week.focus} ({week.hours} h) · {STATUS[w.status]} · due {day(w.due)}", ""]
            for n, task in enumerate(week.tasks, start=1):
                item = tracking.items[task_id(task, week.number, n)]
                line = f"- [{'x' if item.done else ' '}] {task.title} ({task.hours} h, {item.priority} priority)"
                if task.resource:
                    line += f" — [{task.resource.title}]({task.resource.url})"
                lines.append(line)
            if not week.tasks:
                lines.append("_Nothing planned: catch up or rest._")
        m = tracking.items[milestone_id(month.number)]
        lines += ["", f"- [{'x' if m.done else ' '}] **Milestone (due {day(m.due)}):** {month.milestone}"]
        phase = ending.get(month.number)
        if phase:
            project = phase.project
            lines += [
                "", f"### Portfolio project (phase {phase.number}): {project.title}", "", project.problem, "",
                f"**Dataset:** {project.dataset}", "", "**Deliverables:**", "",
                *[f"- {d}" for d in project.deliverables],
            ]
    if roadmap.unscheduled:
        lines += ["", "## Approved but not scheduled", "", "These did not fit in the hour budget:", ""]
        lines += [f"- [{r.title}]({r.url}) ({r.hours} h)" for r in roadmap.unscheduled]
    return "\n".join(lines) + "\n"


def to_pdf(roadmap: Roadmap, profile: ProfileOut, tracking: RoadmapTracking) -> bytes:
    starting, ending = _phases_by_month(roadmap)
    weeks = {w.number: w for w in tracking.weeks}
    phases = {p.number: p for p in tracking.phases}
    doc = Document(_title(profile))
    doc.title(_title(profile))
    doc.subtitle(_summary(roadmap, profile, tracking))
    if tracking.next_steps:
        doc.h2("Immediate next steps")
        for n, step in enumerate(tracking.next_steps, start=1):
            doc.numbered(n, next_step_text(step))
    for month in roadmap.months:
        phase = starting.get(month.number)
        if phase:
            t = phases[phase.number]
            doc.h2(f"Phase {phase.number}: {phase.name}")
            doc.para(f"Months {phase.months[0]}–{phase.months[-1]} · {STATUS[t.status]} · {t.priority} priority", muted=True)
        doc.h3(f"Month {month.number}: {month.theme} ({month.hours} h)")
        doc.para(month.summary, muted=True)
        for week in month.weeks:
            w = weeks[week.number]
            doc.para(f"Week {week.number}: {week.focus} · {week.hours} h · {STATUS[w.status]} · due {day(w.due)}")
            for n, task in enumerate(week.tasks, start=1):
                item = tracking.items[task_id(task, week.number, n)]
                doc.check(f"{task.title} ({task.hours} h)", item.done, indent=4)
                if task.resource:
                    doc.link(task.resource.title, task.resource.url, task.resource.provider, indent=10)
            if not week.tasks:
                doc.para("Nothing planned: catch up or rest.", muted=True)
        m = tracking.items[milestone_id(month.number)]
        doc.check(f"Milestone (due {day(m.due)}): {month.milestone}", m.done)
        phase = ending.get(month.number)
        if phase:
            project = phase.project
            doc.h3(f"Portfolio project: {project.title}")
            doc.para(project.problem)
            doc.kv("Dataset", project.dataset)
            for d in project.deliverables:
                doc.bullet(d)
    if roadmap.unscheduled:
        doc.h2("Approved but not scheduled")
        doc.para("These did not fit in the hour budget.", muted=True)
        for r in roadmap.unscheduled:
            doc.link(r.title, r.url, f"{r.hours} h")
    return doc.output()
