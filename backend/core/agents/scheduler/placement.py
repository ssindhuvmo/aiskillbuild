"""Places the approved resources on the 26-week calendar in plain Python (no LLM, no DB).

place() returns a complete Roadmap with plain default text; narrative.apply later replaces that text with the
AI's wording without touching hours, weeks or resources. The rules hold by construction:

- Resources go in order of gap priority, then the gap's order in the analysis, then level (beginner first).
- Weeks fill in order, at most hours_per_week each. A long resource is split over consecutive weeks, with
  exactly its own hours of learn time, followed by practice on the same resource (budget.PRACTICE_SHARE).
- The last budget.project_reserve hours of each phase are kept free of study; the phase's portfolio project
  is placed right after its last study hour, sized to the study it follows (never more than the reserve).
- Nothing pads the plan: a resource that does not fit in the study time left goes to `unscheduled` (later,
  smaller ones may still fit) and weeks with nothing to do stay empty.
"""
from dataclasses import dataclass, field

from core.agents.course_search.schemas import ApprovedResource
from core.agents.scheduler.budget import (
    MONTH_WEEKS, PHASE_MONTHS, PROJECT_MIN_HOURS, PROJECT_SHARE, WEEKS, budget, month_weeks, phase_weeks,
    practice_hours, project_reserve,
)
from core.agents.scheduler.schemas import (
    Project, ResourceLink, Roadmap, RoadmapMonth, RoadmapPhase, RoadmapTask, RoadmapWeek, SchedulerInput,
)

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}

DEFAULT_DATASET = (
    "Pick a well-known public dataset that fits the problem, e.g. from Kaggle, the UCI Machine Learning "
    "Repository, Hugging Face or a government open-data portal."
)
DEFAULT_DELIVERABLES = ["A notebook or repository with your code", "A short write-up of the approach and the results"]


@dataclass
class _Task:
    kind: str
    hours: int
    title: str
    resource: ResourceLink | None = None
    gap: str | None = None
    last: bool = False  # the resource's (or project's) final chunk: it is finished this week


@dataclass
class _Week:
    number: int
    study_cap: int  # hours available for learn + practice (the rest is the project reserve)
    tasks: list[_Task] = field(default_factory=list)

    @property
    def used(self) -> int:
        return sum(t.hours for t in self.tasks)


def phase_of_month(month: int) -> int:
    return next(n for n, months in enumerate(PHASE_MONTHS, start=1) if month in months)


def ordered(data: SchedulerInput) -> list[ApprovedResource]:
    """Gap priority, then the gap's position in the analysis, then level; the approved order breaks ties."""
    position = {g.skill: i for i, g in enumerate(data.gaps)}
    indexed = list(enumerate(data.resources))
    indexed.sort(key=lambda p: (
        PRIORITY_ORDER[p[1].priority],
        position.get(p[1].gaps[0] if p[1].gaps else "", len(position)),
        LEVEL_ORDER.get(p[1].resource.level, 1),
        p[0],
    ))
    return [r for _, r in indexed]


def _link(item: ApprovedResource) -> ResourceLink:
    r = item.resource
    return ResourceLink(id=r.id, title=r.title, provider=r.provider, url=str(r.url), hours=r.hours)


def _calendar(hours_per_week: int) -> list[_Week]:
    weeks = []
    for phase in range(1, len(PHASE_MONTHS) + 1):
        numbers = phase_weeks(phase)
        caps = [hours_per_week] * len(numbers)
        reserve = project_reserve(hours_per_week, phase)
        for i in reversed(range(len(caps))):  # the reserve is taken from the end of the phase
            taken = min(caps[i], reserve)
            caps[i] -= taken
            reserve -= taken
        weeks += [_Week(n, cap) for n, cap in zip(numbers, caps)]
    return weeks


def _fill(weeks: list[_Week], start: int, hours: int, room) -> list[tuple[_Week, int]]:
    """Split `hours` over weeks from index `start` on, using room(week) per week. Returns (week, hours) chunks."""
    chunks = []
    for week in weeks[start:]:
        if hours == 0:
            break
        take = min(room(week), hours)
        if take > 0:
            chunks.append((week, take))
            hours -= take
    return chunks


def _parts(title: str, n: int, i: int) -> str:
    return title if n == 1 else f"{title} (part {i} of {n})"


def _place_study(weeks: list[_Week], items: list[ApprovedResource]) -> list[ResourceLink]:
    """Learn then practice per resource, filling weeks in order. Returns the resources that did not fit."""
    unscheduled = []
    cursor = 0  # first week that may still have study room
    room = lambda w: w.study_cap - w.used  # noqa: E731
    for item in items:
        while cursor < len(weeks) and room(weeks[cursor]) <= 0:
            cursor += 1
        link, gap = _link(item), (item.gaps[0] if item.gaps else None)
        learn, practice = item.resource.hours, practice_hours(item.resource.hours)
        if learn + practice > sum(room(w) for w in weeks[cursor:]):
            unscheduled.append(link)
            continue
        chunks = _fill(weeks, cursor, learn, room)
        for i, (week, hours) in enumerate(chunks, start=1):
            week.tasks.append(_Task("learn", hours, _parts(link.title, len(chunks), i), link, gap, i == len(chunks)))
        chunks = _fill(weeks, cursor, practice, room)
        for i, (week, hours) in enumerate(chunks, start=1):
            week.tasks.append(_Task("practice", hours, _parts(f"Practice: apply {link.title}", len(chunks), i), link, gap))
    return unscheduled


def _place_projects(weeks: list[_Week], hours_per_week: int) -> None:
    by_number = {w.number: w for w in weeks}
    for phase in range(1, len(PHASE_MONTHS) + 1):
        own = [by_number[n] for n in phase_weeks(phase)]
        study = sum(t.hours for w in own for t in w.tasks)
        # Proportionate: a full study block (1 - PROJECT_SHARE of the phase) gets the whole reserve.
        hours = min(project_reserve(hours_per_week, phase),
                    max(PROJECT_MIN_HOURS, round(study * PROJECT_SHARE / (1 - PROJECT_SHARE))))
        start = max((i for i, w in enumerate(own) if w.tasks), default=0)
        chunks = _fill(own, start, hours, lambda w: hours_per_week - w.used)
        for i, (week, h) in enumerate(chunks, start=1):
            week.tasks.append(_Task("project", h, _parts("Portfolio project", len(chunks), i), last=i == len(chunks)))


def _unique(values) -> list:
    return list(dict.fromkeys(v for v in values if v))


def _join(names: list[str], limit: int = 2) -> str:
    if len(names) <= limit:
        return " and ".join(names)
    return f"{', '.join(names[:limit])} and {len(names) - limit} more"


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def week_focus(tasks: list[_Task] | list[RoadmapTask], gaps: list[str]) -> str:
    parts = list(gaps)
    if any(t.kind == "project" for t in tasks):
        parts.append("Portfolio project")
    return " · ".join(parts) if parts else "Free week: catch up or rest"


def default_theme(gaps: list[str], has_project: bool) -> str:
    if gaps:
        return _clip(_join(gaps), 120)
    return "Portfolio project" if has_project else "Catch-up time"


def default_milestone(finished: list[str], project_done: int | None, busy: bool) -> str:
    parts = []
    if finished:
        parts.append(f"Complete {_join(finished)}")
    if project_done:
        parts.append(f"finish the phase {project_done} portfolio project")
    if parts:
        text = "; ".join(parts)
        return _clip(text[0].upper() + text[1:] + ".", 300)
    return "Keep up the weekly plan." if busy else "Catch up on anything left over."


def default_project(phase: int, gaps: list[str], domain: str) -> Project:
    topic = _join(gaps) if gaps else "what you have learned so far"
    return Project(
        title=_clip(f"{domain} project: {topic}" if gaps else f"{domain} portfolio project {phase}", 120),
        problem=_clip(f"Apply {topic} to a realistic problem in {domain}, end to end, and show the results.", 500),
        dataset=DEFAULT_DATASET,
        deliverables=DEFAULT_DELIVERABLES,
    )


def default_phase_name(gaps: list[str]) -> str:
    return _clip(_join(gaps), 120) if gaps else "Portfolio project"


def month_summary(learn: int, practice: int, project: int) -> str:
    total = learn + practice + project
    if not total:
        return "Nothing is planned this month: use it to catch up or rest."
    return f"{total} hours planned: {learn} learning, {practice} practice, {project} project."


def place(data: SchedulerInput) -> Roadmap:
    """The whole plan with default text. Every phase's narrative is "pending" until narrative.apply runs."""
    weeks = _calendar(data.hours_per_week)
    unscheduled = _place_study(weeks, ordered(data))
    _place_projects(weeks, data.hours_per_week)
    by_number = {w.number: w for w in weeks}

    months = []
    for m in range(1, len(MONTH_WEEKS) + 1):
        own = [by_number[n] for n in month_weeks(m)]
        tasks = [t for w in own for t in w.tasks]
        gaps = _unique(t.gap for t in tasks)
        kind_hours = {k: sum(t.hours for t in tasks if t.kind == k) for k in ("learn", "practice", "project")}
        project_done = phase_of_month(m) if any(t.kind == "project" and t.last for t in tasks) else None
        months.append(RoadmapMonth(
            number=m,
            theme=default_theme(gaps, kind_hours["project"] > 0),
            summary=month_summary(kind_hours["learn"], kind_hours["practice"], kind_hours["project"]),
            milestone=default_milestone(
                _unique(t.resource.title for t in tasks if t.kind == "learn" and t.last), project_done, bool(tasks)),
            hours=sum(kind_hours.values()),
            weeks=[
                RoadmapWeek(
                    number=w.number,
                    focus=week_focus(w.tasks, _unique(t.gap for t in w.tasks)),
                    hours=w.used,
                    tasks=[
                        RoadmapTask(id=f"w{w.number}-{i}", title=t.title, kind=t.kind, hours=t.hours, resource=t.resource)
                        for i, t in enumerate(w.tasks, start=1)
                    ],
                )
                for w in own
            ],
        ))

    phases = []
    for n, phase_months in enumerate(PHASE_MONTHS, start=1):
        gaps = _unique(t.gap for w in phase_weeks(n) for t in by_number[w].tasks)
        phases.append(RoadmapPhase(
            number=n, name=default_phase_name(gaps), months=list(phase_months),
            project=default_project(n, gaps, data.domain), gaps=gaps, narrative="pending",
        ))
    return Roadmap(
        hours_per_week=data.hours_per_week,
        weeks=WEEKS,
        budget_hours=budget(data.hours_per_week),
        total_hours=sum(m.hours for m in months),
        months=months,
        phases=phases,
        unscheduled=unscheduled,
    )
