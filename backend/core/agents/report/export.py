"""Markdown and PDF exports of the Transition Report (pure: no LLM, no DB). Sections in SPEC.md order."""
from core.agents.report.schemas import TransitionReport
from core.agents.scheduler.export import STATUS, day, next_step_text
from core.pdf import Document

SOURCE = {"resume": "from your resume", "user": "from you", "assumed": "assumed, to confirm"}
SECTIONS = [
    "Career Goal", "Current Career Profile", "Career Fit Assessment", "Transferable Skills",
    "Capability Gap Analysis", "Recommended Career Strategy", "Prioritized Learning Plan",
    "Recommended Learning Resources", "Six-Month Career Transition Roadmap", "Recommended Portfolio Projects",
    "Immediate Next Steps",
]


def title(r: TransitionReport) -> str:
    return f"AI Career Transition Report: {r.career_goal.current_role} → {r.career_goal.target_role}"


def _goal(r: TransitionReport) -> list[str]:
    g = r.career_goal
    return [f"Move from {g.current_role} to {g.target_role} in {g.domain}, over {g.weeks} weeks at up to "
            f"{g.hours_per_week} hours a week, starting {day(r.start_date)}."]


def _profile(r: TransitionReport) -> list[tuple[str, str]]:
    p = r.current_profile
    rows = []
    if p.years_experience is not None:
        rows.append(("Experience", f"{p.years_experience} years"))
    if p.ai_level:
        rows.append(("Overall AI level", p.ai_level))
    rows += [(area, level) for area, level in p.capabilities.items()]
    if p.learning_preferences:
        rows.append(("Learning preferences", ", ".join(p.learning_preferences)))
    if p.constraints:
        rows.append(("Constraints", "; ".join(p.constraints)))
    if p.additional_context:
        rows.append(("Context", p.additional_context))
    if p.resume:
        if p.resume.roles:
            rows.append(("Roles", "; ".join(p.resume.roles)))
        if p.resume.certifications:
            rows.append(("Certifications", "; ".join(p.resume.certifications)))
        if p.resume.education:
            rows.append(("Education", "; ".join(p.resume.education)))
        if p.resume.skills:
            rows.append(("Resume skills", ", ".join(p.resume.skills)))
    return rows


def _gap(g) -> str:
    return f"{g.skill} ({g.priority} priority): {g.current_level} → {g.target_level}. {g.why_needed}"


def _plan(i) -> str:
    where = f"phase {i.phase}" if i.phase else "not scheduled"
    return f"{i.skill} ({i.priority} priority, {i.current_level} → {i.target_level}, {where}, {i.resource_hours} h of resources)"


def _resource_note(x) -> str:
    return f"{x.provider} · {x.format} · {x.cost} · {x.hours} h · for {x.gap}" + ("" if x.scheduled else " · not scheduled")


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def to_markdown(r: TransitionReport) -> str:
    out = [f"# {title(r)}", "", f"Written {day(r.written_at.date())}."]

    def section(n: int):
        out.extend(["", f"## {n}. {SECTIONS[n - 1]}", ""])

    section(1)
    out += _goal(r)
    section(2)
    out += [f"- **{k}:** {v}" for k, v in _profile(r)]
    section(3)
    out += "\n\n".join(_paragraphs(r.career_fit)).split("\n")
    section(4)
    out += [f"- **{s.skill}** ({SOURCE[s.source]}): {s.basis}" for s in r.transferable_skills]
    section(5)
    out += [f"- {_gap(g)}" for g in r.gaps]
    if r.later_gaps:
        out += ["", "Later / optional:", ""] + [f"- {_gap(g)}" for g in r.later_gaps]
    section(6)
    out += "\n\n".join(_paragraphs(r.strategy)).split("\n")
    section(7)
    out += [f"{n}. {_plan(i)}" for n, i in enumerate(r.learning_plan, start=1)]
    section(8)
    out += [f"- [{x.title}]({x.url}) — {_resource_note(x)}" for x in r.resources]
    section(9)
    out.append(f"{r.planned_hours} of {r.budget_hours} budgeted hours planned, starting {day(r.start_date)}.")
    for ph in r.roadmap:
        out += ["", f"### Phase {ph.number}: {ph.name} (months {ph.months[0]}–{ph.months[-1]}, {ph.hours} h) · "
                    f"{STATUS.get(ph.status, ph.status)}", ""]
        if ph.gaps:
            out.append(f"Skills: {', '.join(ph.gaps)}")
            out.append("")
        out += [f"- [{'x' if m.done else ' '}] Month {m.month}, {m.theme} (due {day(m.due)}): {m.milestone}"
                for m in ph.milestones]
    section(10)
    for p in r.projects:
        out += [f"### Phase {p.phase}: {p.title}", "", p.problem, "", f"**Dataset:** {p.dataset}", "",
                *[f"- {d}" for d in p.deliverables], ""]
    section(11)
    out += [f"{n}. {next_step_text(s)}" for n, s in enumerate(r.next_steps, start=1)] or ["Every task is done."]
    return "\n".join(out).rstrip() + "\n"


def to_pdf(r: TransitionReport) -> bytes:
    doc = Document(title(r))
    doc.title(title(r))
    doc.subtitle(f"Written {day(r.written_at.date())}")

    def section(n: int):
        doc.h2(f"{n}. {SECTIONS[n - 1]}")

    section(1)
    for line in _goal(r):
        doc.para(line)
    section(2)
    for k, v in _profile(r):
        doc.kv(k, v)
    section(3)
    for p in _paragraphs(r.career_fit):
        doc.para(p)
    section(4)
    for s in r.transferable_skills:
        doc.bullet(f"{s.skill} ({SOURCE[s.source]}): {s.basis}")
    section(5)
    for g in r.gaps:
        doc.bullet(_gap(g))
    if r.later_gaps:
        doc.para("Later / optional:", muted=True)
        for g in r.later_gaps:
            doc.bullet(_gap(g))
    section(6)
    for p in _paragraphs(r.strategy):
        doc.para(p)
    section(7)
    for n, i in enumerate(r.learning_plan, start=1):
        doc.numbered(n, _plan(i))
    section(8)
    for x in r.resources:
        doc.link(x.title, x.url, _resource_note(x))
    section(9)
    doc.para(f"{r.planned_hours} of {r.budget_hours} budgeted hours planned, starting {day(r.start_date)}.")
    for ph in r.roadmap:
        doc.h3(f"Phase {ph.number}: {ph.name}")
        doc.para(f"Months {ph.months[0]}–{ph.months[-1]} · {ph.hours} h · {STATUS.get(ph.status, ph.status)}"
                 + (f" · {', '.join(ph.gaps)}" if ph.gaps else ""), muted=True)
        for m in ph.milestones:
            doc.check(f"Month {m.month}, {m.theme} (due {day(m.due)}): {m.milestone}", m.done)
    section(10)
    for p in r.projects:
        doc.h3(f"Phase {p.phase}: {p.title}")
        doc.para(p.problem)
        doc.kv("Dataset", p.dataset)
        for d in p.deliverables:
            doc.bullet(d)
    section(11)
    if r.next_steps:
        for n, s in enumerate(r.next_steps, start=1):
            doc.numbered(n, next_step_text(s))
    else:
        doc.para("Every task is done.")
    return doc.output()
