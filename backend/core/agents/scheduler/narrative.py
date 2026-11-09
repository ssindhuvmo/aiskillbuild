"""The scheduler's only LLM step: the text of one phase of an already placed roadmap.

write() makes one structured-output call (PhaseNarrative) per phase; the agent runs the three phases in
parallel. The reply has no hours, weeks, resources or links, so the model cannot change the plan. Pydantic
plus check() validate it, with one retry that feeds the problems back; after that the phase keeps the plain
default text from placement (narrative = "default"), so a roadmap is always produced.
"""
import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from core.agents.scheduler.schemas import PhaseNarrative, Roadmap, RoadmapPhase, SchedulerInput
from core.llm import MODEL, get_client

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_ATTEMPTS = 2  # one retry
MAX_TOKENS = 3000  # one phase's text is well under 1.5k tokens
LINK = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)


class NarrativeFailed(Exception):
    pass


def _months(roadmap: Roadmap, phase: RoadmapPhase):
    return [m for m in roadmap.months if m.number in phase.months]


def practice_ids(roadmap: Roadmap, phase: RoadmapPhase) -> list[str]:
    return [t.id for m in _months(roadmap, phase) for w in m.weeks for t in w.tasks if t.kind == "practice"]


def request(data: SchedulerInput, roadmap: Roadmap, phase: RoadmapPhase, problems: list[str] = ()) -> str:
    profile = data.model_dump(include={"current_role", "target_role", "ai_level", "capabilities", "domain"})
    gaps = [g.model_dump(include={"skill", "why_needed", "priority"}) for g in data.gaps if g.skill in phase.gaps]
    resources = {r.resource.id: r.resource for r in data.resources}
    used = {t.resource.id for m in _months(roadmap, phase) for w in m.weeks for t in w.tasks if t.resource}
    plan = [
        {
            "month": m.number,
            "weeks": [
                {"week": w.number, "tasks": [
                    {"id": t.id, "kind": t.kind, "hours": t.hours, "title": t.title,
                     **({"resource_id": t.resource.id} if t.resource else {})}
                    for t in w.tasks
                ]}
                for w in m.weeks
            ],
        }
        for m in _months(roadmap, phase)
    ]
    project_hours = sum(t.hours for m in _months(roadmap, phase) for w in m.weeks for t in w.tasks if t.kind == "project")
    text = (
        f"Profile:\n{json.dumps(profile, indent=2)}\n\n"
        f"Phase {phase.number} of 3 (months {phase.months[0]}-{phase.months[1]}).\n\n"
        f"Skill gaps studied in this phase:\n{json.dumps(gaps, indent=2)}\n\n"
        f"Resources in this phase:\n"
        f"{json.dumps([resources[i].model_dump(include={'id', 'title', 'format', 'level', 'hours', 'description'}) for i in sorted(used) if i in resources], indent=2)}\n\n"
        f"Domain AI use cases:\n{json.dumps([u.model_dump() for u in data.domain_use_cases], indent=2)}\n\n"
        f"Placed plan (fixed):\n{json.dumps(plan, indent=2)}\n\n"
        f"Portfolio project time in this phase: {project_hours} hours.\n"
        f"Practice task ids to reword: {json.dumps(practice_ids(roadmap, phase))}"
    )
    if problems:
        text += "\n\nYour previous reply was rejected:\n- " + "\n- ".join(problems) + "\nReturn a corrected reply."
    return text


def _texts(n: PhaseNarrative) -> list[str]:
    return [n.name, n.first_month.theme, n.first_month.milestone, n.second_month.theme, n.second_month.milestone,
            *(p.title for p in n.practice), n.project.title, n.project.problem, n.project.dataset, *n.project.deliverables]


def check(n: PhaseNarrative, roadmap: Roadmap, phase: RoadmapPhase) -> list[str]:
    """Rules Pydantic can't express. Missing practice ids are allowed: those tasks keep their default title."""
    problems = []
    allowed = set(practice_ids(roadmap, phase))
    if unknown := [p.id for p in n.practice if p.id not in allowed]:
        problems.append(f"practice ids {unknown} are not practice tasks of this phase; use only {sorted(allowed)}.")
    if any(LINK.search(t) for t in _texts(n)):
        problems.append("Do not write URLs or links anywhere; name datasets and resources instead.")
    return problems


def write(data: SchedulerInput, roadmap: Roadmap, phase: RoadmapPhase) -> PhaseNarrative:
    """A checked narrative for one phase, or NarrativeFailed after MAX_ATTEMPTS. LLM errors (missing key,
    auth, rate limit) propagate; the caller falls back to the default text either way."""
    client = get_client()
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.parse(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=PROMPT,
                messages=[{"role": "user", "content": request(data, roadmap, phase, problems)}],
                output_format=PhaseNarrative,
            )
            result = response.parsed_output
            problems = ["The reply was empty or cut off."] if result is None else check(result, roadmap, phase)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return result
        log.warning("Scheduler narrative for phase %d, attempt %d of %d rejected: %s",
                    phase.number, attempt, MAX_ATTEMPTS, "; ".join(problems))
    raise NarrativeFailed("; ".join(problems))


def _project_title(title: str, task_title: str) -> str:
    part = re.search(r" \(part \d+ of \d+\)$", task_title)
    return f"Portfolio project: {title}" + (part.group(0) if part else "")


def apply(roadmap: Roadmap, number: int, n: PhaseNarrative) -> Roadmap:
    """Copy a checked narrative into phase `number`. Only text changes; hours, weeks and links stay."""
    phase = roadmap.phases[number - 1]
    phase.name, phase.project, phase.narrative = n.name, n.project, "ai"
    first, second = _months(roadmap, phase)
    for month, text in ((first, n.first_month), (second, n.second_month)):
        month.theme, month.milestone = text.theme, text.milestone
    titles = {p.id: p.title for p in n.practice}
    for month in (first, second):
        for week in month.weeks:
            for task in week.tasks:
                if task.kind == "practice" and task.id in titles:
                    task.title = titles[task.id]
                elif task.kind == "project" and task.title.startswith("Portfolio project"):
                    # (a replan's catch-up project of an earlier phase keeps its own title)
                    task.title = _project_title(n.project.title, task.title)
    return roadmap


def use_default(roadmap: Roadmap, number: int) -> Roadmap:
    """Keep placement's plain text for phase `number`."""
    roadmap.phases[number - 1].narrative = "default"
    return roadmap
