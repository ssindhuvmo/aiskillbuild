"""The roadmap's fixed calendar, hour budget and planning constants, in plain Python (no LLM, no DB).

placement.place builds plans that keep every rule here by construction. check_budget is a safety assertion:
it re-checks a finished roadmap, and the agent refuses to save one that fails it.
"""
from core.agents.scheduler.schemas import Roadmap, SchedulerInput

MONTH_WEEKS = (4, 4, 5, 4, 4, 5)  # weeks in months 1-6
WEEKS = sum(MONTH_WEEKS)  # 26
PHASE_MONTHS = ((1, 2), (3, 4), (5, 6))  # months in phases 1-3; each phase has one portfolio project

PRACTICE_SHARE = 0.35  # practice after each resource, as a share of its hours (at least 1 hour)
PROJECT_SHARE = 0.25  # the end of each phase reserved for its portfolio project, as a share of the phase's hours
PROJECT_MIN_HOURS = 4  # a portfolio project gets at least this much (or the whole reserve, if smaller)

MAX_PROBLEMS = 15


def budget(hours_per_week: int) -> int:
    return hours_per_week * WEEKS


def month_weeks(month: int) -> list[int]:
    """The week numbers that belong to a month (1-based), e.g. month 3 -> [9, 10, 11, 12, 13]."""
    start = sum(MONTH_WEEKS[: month - 1]) + 1
    return list(range(start, start + MONTH_WEEKS[month - 1]))


def phase_weeks(phase: int) -> list[int]:
    """The week numbers of a phase (1-based), e.g. phase 1 -> weeks 1 to 8."""
    return [w for m in PHASE_MONTHS[phase - 1] for w in month_weeks(m)]


def practice_hours(resource_hours: int) -> int:
    return max(1, round(PRACTICE_SHARE * resource_hours))


def project_reserve(hours_per_week: int, phase: int) -> int:
    """Hours held back at the end of a phase for its portfolio project."""
    return max(1, round(PROJECT_SHARE * hours_per_week * len(phase_weeks(phase))))


def check_budget(roadmap: Roadmap, data: SchedulerInput, from_week: int = 1) -> list[str]:
    """Returns problems; empty means the roadmap fits the calendar and the hour budget. Whole-plan problems
    come first so the MAX_PROBLEMS cut never drops them. from_week: a replan, where a phase that is over
    before from_week may have no project work left (its catch-up project moved to the open weeks)."""
    problems = []  # about the plan as a whole
    details = []  # about single weeks
    limit = data.hours_per_week
    resources = {r.resource.id: r.resource for r in data.resources}

    if [m.number for m in roadmap.months] != list(range(1, len(MONTH_WEEKS) + 1)):
        problems.append("Months must be numbered 1 to 6, in order.")
    total = 0
    learned: dict[str, int] = {}
    project_hours: dict[int, int] = {}  # month -> hours of project tasks
    for month in roadmap.months:
        expected = month_weeks(month.number) if 1 <= month.number <= len(MONTH_WEEKS) else []
        if [w.number for w in month.weeks] != expected:
            problems.append(f"Month {month.number} must contain exactly its calendar weeks, in order.")
        for week in month.weeks:
            hours = sum(t.hours for t in week.tasks)
            total += hours
            if hours != week.hours:
                details.append(f"Week {week.number} says {week.hours} hours but its tasks add up to {hours}.")
            if hours > limit:
                details.append(f"Week {week.number} plans {hours} hours; the limit is {limit} hours per week.")
            for task in week.tasks:
                if task.hours < 1:
                    details.append(f'Week {week.number}: "{task.title}" has {task.hours} hours.')
                if task.kind == "project":
                    project_hours[month.number] = project_hours.get(month.number, 0) + task.hours
                if task.resource is None:
                    if task.kind == "learn":
                        details.append(f'Week {week.number}: the learn task "{task.title}" has no resource.')
                    continue
                if task.resource.id not in resources or task.resource.url != str(resources[task.resource.id].url):
                    details.append(f'Week {week.number} uses "{task.resource.id}", which is not in the approved list.')
                elif task.kind == "learn":
                    learned[task.resource.id] = learned.get(task.resource.id, 0) + task.hours

    if total != roadmap.total_hours:
        problems.append(f"The roadmap says {roadmap.total_hours} hours but its weeks add up to {total}.")
    if total > budget(limit):
        problems.append(f"The plan totals {total} hours; the budget is {budget(limit)} hours.")
    for rid, hours in learned.items():
        if hours > resources[rid].hours:
            problems.append(f"{rid} takes {resources[rid].hours} hours but has {hours} hours of learn tasks.")
    if [p.months for p in roadmap.phases] != [list(m) for m in PHASE_MONTHS]:
        problems.append("The roadmap must have exactly 3 phases of 2 months.")
    for phase, months in enumerate(PHASE_MONTHS, start=1):
        if phase_weeks(phase)[-1] < from_week:
            continue
        if not any(project_hours.get(m) for m in months):
            problems.append(f"Phase {phase} has no portfolio project work.")
    return (problems + details)[:MAX_PROBLEMS]
