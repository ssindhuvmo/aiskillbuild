"""The Skill Analysis buttons: direct edits to a saved analysis, in plain Python (no LLM call).

Each edit is also stored as a correction, so a re-analysis keeps it (see check_rules). Adding a gap to the
plan never goes over the hour budget or MAX_GAPS: when it would, nothing changes and a BudgetSuggestion
names the plan gaps to move to later; sending those back as `make_room` does the swap.
"""
from typing import Literal

from sqlalchemy.orm import Session

from core import repository
from core.agents.gap_analysis.agent import EFFORT_TOLERANCE, ProfileNotConfirmed, _norm
from core.agents.gap_analysis.schemas import (
    MAX_GAPS, MAX_LATER, BudgetSuggestion, Correction, Gap, GapAnalysis, Strength,
)
from core.agents.scheduler.budget import budget
from core.schemas import GapState

Action = Literal["knows", "not_needed", "later", "plan", "restore"]
# The corrections the buttons write; at most one per skill, the newest wins.
BUTTON_KINDS = {"knows", "not_needed", "later", "plan"}
PRIORITY = {"high": 0, "medium": 1, "low": 2}
MAX_STRENGTHS = 15


class AdjustRefused(Exception):
    """The edit would break the analysis' limits (e.g. an empty plan); the message says why."""


def _find(gaps: list[Gap], name: str) -> int | None:
    return next((i for i, g in enumerate(gaps) if _norm(g.skill) == name), None)


def _named(c: Correction, name: str) -> bool:
    return c.skill is not None and _norm(c.skill) == name


def _take(a: GapAnalysis, name: str, skill: str) -> tuple[Gap, bool]:
    """Remove the named gap from the plan or later list; returns it and whether it was in the plan."""
    i = _find(a.gaps, name)
    if i is not None:
        if len(a.gaps) == 1:
            raise AdjustRefused("Your plan needs at least one skill gap. Add another one to your plan first.")
        return a.gaps.pop(i), True
    i = _find(a.later_gaps, name)
    if i is None:
        raise AdjustRefused(f'"{skill}" is not one of your skill gaps.')
    return a.later_gaps.pop(i), False


def _to_later(a: GapAnalysis, gaps: list[Gap]) -> None:
    if len(a.later_gaps) + len(gaps) > MAX_LATER:
        raise AdjustRefused(f"Later / optional holds at most {MAX_LATER} skills. Mark one as not needed first.")
    a.later_gaps[:0] = gaps


def room_needed(gaps: list[Gap], gap: Gap, hours_per_week: int, pinned: set[str]) -> BudgetSuggestion | None:
    """None if `gap` fits in the plan as it is; else which plan gaps to move to later: lowest priority first,
    then the last listed, and gaps the user put in the plan only if nothing else is enough."""
    limit, hours = budget(hours_per_week), sum(g.effort_hours for g in gaps) + gap.effort_hours
    fits = lambda total, count: total <= limit * EFFORT_TOLERANCE and count <= MAX_GAPS  # noqa: E731
    if fits(hours, len(gaps) + 1):
        return None
    if gap.effort_hours > limit * EFFORT_TOLERANCE:
        return BudgetSuggestion(
            skill=gap.skill, move=[], fits=False,
            message=f'"{gap.skill}" alone needs {gap.effort_hours} hours, more than the {limit} hours in your plan. '
                    "Raise your weekly hours on your profile to fit it, or keep it for later.",
        )
    order = sorted(range(len(gaps)), key=lambda i: (_norm(gaps[i].skill) in pinned, -PRIORITY[gaps[i].priority], -i))
    move, total, count = [], hours, len(gaps) + 1
    for i in order:
        if fits(total, count):
            break
        move.append(gaps[i].skill)
        total, count = total - gaps[i].effort_hours, count - 1
    reason = (f"Your plan already has {MAX_GAPS} skill gaps" if len(gaps) >= MAX_GAPS
              else f'Adding "{gap.skill}" brings your plan to {hours} of your {limit} hours')
    names = ", ".join(f'"{m}"' for m in move)
    return BudgetSuggestion(skill=gap.skill, move=move, fits=True,
                            message=f"{reason}. Move {names} to Later / optional to make room.")


def adjust(
    analysis: GapAnalysis, corrections: list[Correction], action: Action, skill: str, hours_per_week: int,
    make_room: list[str] = (),
) -> tuple[GapAnalysis, list[Correction], BudgetSuggestion | None]:
    """Apply one button to a copy of the analysis. Returns the new analysis, the new corrections and, when
    adding to the plan does not fit, the suggestion (the plan is then unchanged)."""
    a = analysis.model_copy(deep=True)
    name, restoring = _norm(skill), action == "restore"
    rest = [c for c in corrections if not (c.kind in BUTTON_KINDS and _named(c, name))]

    if action == "restore":
        removed = next((c for c in corrections if c.kind == "not_needed" and _named(c, name) and c.gap), None)
        if removed is None:
            raise AdjustRefused(f'"{skill}" is not in your removed skills.')
        _to_later(a, [removed.gap])  # back where it was; a plan gap goes through the budget check below
        if not removed.in_plan:
            return a, rest, None
        action, corrections = "plan", rest

    if action == "knows":
        gap, _ = _take(a, name, skill)
        if len(a.strengths) >= MAX_STRENGTHS:
            raise AdjustRefused(f"You already have {MAX_STRENGTHS} strengths listed. Update the analysis instead.")
        a.strengths.append(Strength(
            skill=gap.skill, category="domain" if gap.category == "domain" else "technical", source="user",
            basis="You said you already know this.",
        ))
        return a, [*rest, Correction(kind="knows", skill=gap.skill, text=f"I already know {gap.skill}")], None

    if action == "not_needed":
        gap, in_plan = _take(a, name, skill)
        return a, [*rest, Correction(kind="not_needed", skill=gap.skill, text=f"Not needed: {gap.skill}", gap=gap,
                                     in_plan=in_plan)], None

    if action == "later":
        if _find(a.gaps, name) is None:
            raise AdjustRefused(f'"{skill}" is not in your plan.')
        gap, _ = _take(a, name, skill)
        _to_later(a, [gap])
        return a, [*rest, Correction(kind="later", skill=gap.skill, text=f"Later: {gap.skill}")], None

    # action == "plan": a later gap into the plan, making room if the user accepted a suggestion.
    i = _find(a.later_gaps, name)
    if i is None:
        raise AdjustRefused(f'"{skill}" is not in Later / optional.')
    gap = a.later_gaps[i]
    pinned = {_norm(c.skill) for c in rest if c.kind == "plan" and c.skill}
    wanted = {_norm(m) for m in make_room} - {name}
    kept = [g for g in a.gaps if _norm(g.skill) not in wanted]
    if room_needed(kept, gap, hours_per_week, pinned) is not None:
        # Not enough room (none offered, or too little): the plan stays as it is, with a suggestion for all of it.
        return a, corrections, room_needed(a.gaps, gap, hours_per_week, pinned)
    moved = [g for g in a.gaps if _norm(g.skill) in wanted]
    a.later_gaps.pop(i)
    _to_later(a, moved)
    a.gaps = [*kept, gap]
    later = [Correction(kind="later", skill=g.skill, text=f"Later: {g.skill}") for g in moved]
    moved_names = {_norm(g.skill) for g in moved}
    rest = [c for c in rest if not (c.kind in BUTTON_KINDS and c.skill and _norm(c.skill) in moved_names)]
    if not restoring:  # Restore is an undo: the gap is back as the analysis had it, not pinned
        later.append(Correction(kind="plan", skill=gap.skill, text=f"In my plan: {gap.skill}"))
    return a, [*rest, *later], None


def adjust_for_user(db: Session, user_id: str, action: Action, skill: str, make_room: list[str]) -> GapState:
    """Apply one button to the user's current analysis and save it; a suggestion comes back on the state."""
    state = repository.get_gap_state(db, user_id)
    if state.status != "ready" or state.stale:
        raise ProfileNotConfirmed("Run the skill-gap analysis for your current profile first.")
    analysis, corrections, suggestion = adjust(
        state.analysis, state.corrections, action, skill, state.profile.hours_per_week, make_room
    )
    if analysis != state.analysis or corrections != state.corrections:
        state = repository.update_gap_analysis(db, user_id, analysis, corrections)
    return state.model_copy(update={"suggestion": suggestion})
