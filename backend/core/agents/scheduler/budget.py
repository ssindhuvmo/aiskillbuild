"""The roadmap's hour budget and fixed calendar, enforced in plain Python (no LLM, no DB).

A draft from the model is only accepted when check_budget returns no problems, so a saved
roadmap never plans more than hours_per_week in any week or hours_per_week x WEEKS in total.
"""
from core.agents.scheduler.schemas import (
    ResourceLink, Roadmap, RoadmapDraft, RoadmapMonth, RoadmapPhase, RoadmapTask, RoadmapWeek, SchedulerInput,
)

MONTH_WEEKS = (4, 4, 5, 4, 4, 5)  # weeks in months 1-6
WEEKS = sum(MONTH_WEEKS)  # 26
PHASE_MONTHS = ((1, 2), (3, 4), (5, 6))  # months in phases 1-3; each phase has one portfolio project
MAX_PROBLEMS = 15  # enough feedback for a retry without flooding the prompt


def budget(hours_per_week: int) -> int:
    return hours_per_week * WEEKS


def month_weeks(month: int) -> list[int]:
    """The week numbers that belong to a month (1-based), e.g. month 3 -> [9, 10, 11, 12, 13]."""
    start = sum(MONTH_WEEKS[: month - 1]) + 1
    return list(range(start, start + MONTH_WEEKS[month - 1]))


def check_budget(draft: RoadmapDraft, data: SchedulerInput) -> list[str]:
    """Returns problems; empty means the draft fits the calendar and the hour budget. Whole-plan
    problems come first so the MAX_PROBLEMS cut never drops them."""
    problems = []  # about the plan as a whole
    details = []  # about single weeks
    limit = data.hours_per_week
    resources = {r.resource.id: r.resource for r in data.resources}

    if [m.number for m in draft.months] != list(range(1, len(MONTH_WEEKS) + 1)):
        problems.append("Months must be numbered 1 to 6, in order.")
    if [p.number for p in draft.phases] != list(range(1, len(PHASE_MONTHS) + 1)):
        problems.append("Phases must be numbered 1 to 3, in order.")

    total = 0
    studied: dict[str, int] = {}  # resource id -> hours of "learn" tasks
    project_hours: dict[int, int] = {}  # month -> hours of project tasks
    for month in draft.months:
        expected = month_weeks(month.number)
        if [w.number for w in month.weeks] != expected:
            problems.append(f"Month {month.number} must contain exactly weeks {expected[0]} to {expected[-1]}, in order.")
        for week in month.weeks:
            hours = sum(t.hours for t in week.tasks)
            total += hours
            if hours > limit:
                details.append(f"Week {week.number} plans {hours} hours; the limit is {limit} hours per week.")
            for task in week.tasks:
                if task.kind == "project":
                    project_hours[month.number] = project_hours.get(month.number, 0) + task.hours
                if task.resource_id is None:
                    if task.kind == "learn":  # so every learn task gets a link
                        details.append(
                            f'Week {week.number}: the learn task "{task.title}" has no resource_id. Set it to the '
                            'approved resource being studied, or make the task kind "practice".'
                        )
                    continue
                if task.resource_id not in resources:
                    details.append(f'Week {week.number} uses resource_id "{task.resource_id}", which is not in the approved list.')
                elif task.kind == "learn":  # practice and project work may build on a resource for longer
                    studied[task.resource_id] = studied.get(task.resource_id, 0) + task.hours

    if total > budget(limit):
        problems.append(f"The plan totals {total} hours; the budget is {budget(limit)} hours ({limit} per week x {WEEKS} weeks).")
    for rid, hours in studied.items():
        if hours > resources[rid].hours:
            problems.append(f'Resource "{rid}" takes {resources[rid].hours} hours but has {hours} hours of "learn" tasks.')
    for phase, months in enumerate(PHASE_MONTHS, start=1):
        if not any(project_hours.get(m) for m in months):
            problems.append(f'Phase {phase} (months {months[0]}-{months[1]}) needs at least one task of kind "project" for its portfolio project.')
    return (problems + details)[:MAX_PROBLEMS]


def finalize(draft: RoadmapDraft, data: SchedulerInput) -> Roadmap:
    """Turn an accepted draft into the saved roadmap: attach links from the approved list and
    add up the hours. Call only after check_budget passed."""
    links = {
        r.resource.id: ResourceLink(
            id=r.resource.id, title=r.resource.title, provider=r.resource.provider,
            url=str(r.resource.url), hours=r.resource.hours,
        )
        for r in data.resources
    }
    used: set[str] = set()
    months = []
    for month in draft.months:
        weeks = []
        for week in month.weeks:
            tasks = [
                RoadmapTask(title=t.title, kind=t.kind, hours=t.hours, resource=links.get(t.resource_id))
                for t in week.tasks
            ]
            used |= {t.resource_id for t in week.tasks if t.resource_id}
            weeks.append(RoadmapWeek(number=week.number, focus=week.focus, hours=sum(t.hours for t in tasks), tasks=tasks))
        months.append(
            RoadmapMonth(
                number=month.number, theme=month.theme, summary=month.summary, milestone=month.milestone,
                hours=sum(w.hours for w in weeks), weeks=weeks,
            )
        )
    return Roadmap(
        hours_per_week=data.hours_per_week,
        weeks=WEEKS,
        budget_hours=budget(data.hours_per_week),
        total_hours=sum(m.hours for m in months),
        months=months,
        phases=[
            RoadmapPhase(number=p.number, name=p.name, months=list(PHASE_MONTHS[p.number - 1]), project=p.project)
            for p in draft.phases
        ],
        unscheduled=[link for rid, link in links.items() if rid not in used],
    )
