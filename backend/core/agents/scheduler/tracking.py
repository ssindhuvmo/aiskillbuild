"""Roadmap tracking (milestone 10): due dates, priority, status and the immediate next steps.

Pure Python, no DB and no LLM. Only the start date and the checked items are stored; everything here is
worked out again on every read, so dates and statuses always follow the saved plan and today's date.
A checked item is remembered with its fingerprint, so after a regenerate a check carries over only to the
same task (kind, resource and week).
"""
from collections.abc import Iterator
from datetime import date, timedelta

from core.agents.course_search.schemas import ApprovedList
from core.agents.scheduler.schemas import (
    GroupStatus, ItemTracking, NextStep, PhaseTracking, Priority, Roadmap, RoadmapTask, RoadmapTracking,
    WeekTracking,
)

RANK = {"high": 0, "medium": 1, "low": 2}
DEFAULT_PRIORITY: Priority = "medium"  # a gap the approved list doesn't mention (should not happen)
NEXT_STEPS = 3


def due_date(start: date, week: int) -> date:
    """The last day of a plan week (week 1 is the 7 days from the start date)."""
    return start + timedelta(days=7 * week - 1)


def week_of(start: date, today: date) -> int:
    """The plan week that contains today (below 1 before the start, above 26 after the end)."""
    return (today - start).days // 7 + 1


def milestone_id(month: int) -> str:
    return f"m{month}"


def task_id(task: RoadmapTask, week: int, n: int) -> str:
    return task.id or f"w{week}-{n}"  # roadmaps saved before task ids


def tasks(roadmap: Roadmap) -> Iterator[tuple[str, RoadmapTask, int]]:
    """(id, task, week number) for every task in plan order."""
    for month in roadmap.months:
        for week in month.weeks:
            for n, task in enumerate(week.tasks, start=1):
                yield task_id(task, week.number, n), task, week.number


def fingerprints(roadmap: Roadmap) -> dict[str, str]:
    """Every checkable item (tasks and month milestones) with what identifies it across a regenerate."""
    found = {
        tid: f"{task.kind}|{task.resource.id if task.resource else ''}|{week}"
        for tid, task, week in tasks(roadmap)
    }
    for month in roadmap.months:
        found[milestone_id(month.number)] = f"milestone|{month.number}|{month.weeks[-1].number}"
    return found


def _highest(priorities) -> Priority:
    return min(priorities, key=RANK.__getitem__, default=DEFAULT_PRIORITY)


def _item_status(done: bool, due: date, week: int, current: int, today: date) -> str:
    if done:
        return "done"
    if due < today:
        return "overdue"
    return "this_week" if week == current else "not_started"


def _group_status(done: list[bool], due: date, current_or_past: bool, today: date) -> GroupStatus:
    if not done:
        return "empty"
    if all(done):
        return "done"
    if due < today:
        return "overdue"
    return "in_progress" if any(done) or current_or_past else "not_started"


def track(roadmap: Roadmap, approved: ApprovedList | None, start: date, done: set[str], today: date) -> RoadmapTracking:
    """Status, priority and due date for every task, week, month milestone and phase, plus the next steps.
    `approved` is the list the roadmap was built from (its snapshot); priorities come from its gaps."""
    by_resource: dict[str, Priority] = {}
    by_gap: dict[str, Priority] = {}
    for item in (approved.resources if approved else []):
        by_resource.setdefault(item.resource.id, item.priority)
        by_gap.setdefault(item.gaps[0], item.priority)
    phase_of_month = {m: p for p in roadmap.phases for m in p.months}
    phase_priority = {p.number: _highest(by_gap.get(g, DEFAULT_PRIORITY) for g in p.gaps) for p in roadmap.phases}

    current = week_of(start, today)
    items: dict[str, ItemTracking] = {}
    weeks: list[WeekTracking] = []
    phase_done: dict[int, list[bool]] = {p.number: [] for p in roadmap.phases}
    steps: list[tuple[int, int, NextStep]] = []  # (0 overdue / 1 later, order, step)

    for month in roadmap.months:
        phase = phase_of_month.get(month.number)
        default = phase_priority.get(phase.number, DEFAULT_PRIORITY) if phase else DEFAULT_PRIORITY
        for week in month.weeks:
            due = due_date(start, week.number)
            week_done = []
            for n, task in enumerate(week.tasks, start=1):
                tid = task_id(task, week.number, n)
                is_done = tid in done
                priority = by_resource.get(task.resource.id, default) if task.resource else default
                status = _item_status(is_done, due, week.number, current, today)
                items[tid] = ItemTracking(done=is_done, status=status, due=due, priority=priority)
                week_done.append(is_done)
                if not is_done:
                    steps.append((0 if status == "overdue" else 1, len(steps), NextStep(
                        task_id=tid, title=task.title, kind=task.kind, hours=task.hours, week=week.number, due=due,
                        overdue=status == "overdue", resource=task.resource,
                    )))
            weeks.append(WeekTracking(
                number=week.number, due=due, status=_group_status(week_done, due, week.number <= current, today),
            ))
            if phase:
                phase_done[phase.number] += week_done
        last = month.weeks[-1].number
        mid = milestone_id(month.number)
        due = due_date(start, last)
        items[mid] = ItemTracking(
            done=mid in done, status=_item_status(mid in done, due, last, current, today), due=due, priority=default,
        )
        if phase:
            phase_done[phase.number].append(mid in done)

    phases = []
    for p in roadmap.phases:
        weeks_in = [w for m in roadmap.months if m.number in p.months for w in m.weeks]
        due = due_date(start, weeks_in[-1].number) if weeks_in else start
        started = bool(weeks_in) and weeks_in[0].number <= current
        phases.append(PhaseTracking(
            number=p.number, status=_group_status(phase_done[p.number], due, started, today),
            priority=phase_priority[p.number],
        ))

    all_tasks = list(tasks(roadmap))
    return RoadmapTracking(
        start_date=start,
        today=today,
        current_week=current if 1 <= current <= roadmap.weeks else None,
        items=items,
        weeks=weeks,
        phases=phases,
        next_steps=[s for _, _, s in sorted(steps)[:NEXT_STEPS]],
        done_tasks=sum(1 for tid, _, _ in all_tasks if tid in done),
        total_tasks=len(all_tasks),
        done_hours=sum(t.hours for tid, t, _ in all_tasks if tid in done),
        planned_hours=sum(t.hours for _, t, _ in all_tasks),
    )
