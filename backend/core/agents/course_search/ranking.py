"""Deterministic ranking of candidate resources for one gap. Pure functions: no I/O, no LLM.

score = relevance (the retriever's match_score) + fit with the user's AI level
      + applicability to their industry domain + time cost relative to the gap's effort
      + match to the learning preferences from intake + quality signals from the source.
"""
import math

from core.agents.course_search.schemas import RankedResource, ScoreBreakdown
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, Level, Resource, SearchProfile

WEIGHTS = {"relevance": 0.40, "level": 0.15, "domain": 0.15, "time": 0.10, "preference": 0.15, "quality": 0.05}

# Intake learning preferences (intake/validation.py PREFERENCES) -> does this resource match it?
# "certifications" matches nothing yet: no source reports whether a resource gives a certificate.
PREFERENCE_MATCH = {
    "free_courses": lambda r: r.format == "course" and r.cost == "free",
    "paid_courses": lambda r: r.format == "course" and r.cost == "paid",
    "video": lambda r: r.format == "video",
    "articles": lambda r: r.format in ("article", "paper", "tutorial"),
    "books": lambda r: r.format == "book",
    "projects": lambda r: r.format in ("project", "repository"),
}
NEUTRAL = 0.5  # preference fit when the user gave no usable preference; quality when a source reports none
NO_PREFERENCE_MATCH = 0.2
CURATED_QUALITY = 0.8  # knowledge-base entries were reviewed by hand
VIEWS_FOR_FULL = 1_000_000  # quality: views on a log scale, 1M views or more = 1
GOOD_LIKE_RATE = 0.03  # quality: likes / views at or above this = 1
TRUSTED_QUALITY = 0.9  # a channel from data/youtube_channels.json gets at least this

LEVELS: list[Level] = ["beginner", "intermediate", "advanced"]
# The resource level each AI level is ready for.
EXPERIENCE_LEVEL = {"None": "beginner", "Beginner": "beginner", "Intermediate": "intermediate", "Experienced": "advanced"}

DOMAIN_MATCH, GENERAL, OTHER_DOMAIN = 1.0, 0.6, 0.1

# diversify(): penalties for repeating a format / cost already picked for the same gap.
FORMAT_PENALTY = 0.10
COST_PENALTY = 0.05


def level_fit(level: Level, ai_level: str) -> float:
    """1 at the user's level, 0.5 one level away, 0 two levels away."""
    target = EXPERIENCE_LEVEL.get(ai_level, "beginner")
    distance = abs(LEVELS.index(level) - LEVELS.index(target))
    return (1.0, 0.5, 0.0)[distance]


def domain_fit(resource_domains: list[str], domain: str) -> float:
    if domain in resource_domains:
        return DOMAIN_MATCH
    return GENERAL if not resource_domains else OTHER_DOMAIN


def time_fit(hours: int, effort_hours: int) -> float:
    """1 if the resource fits in the gap's estimated effort, then decreasing (effort / hours)."""
    return 1.0 if hours <= effort_hours else effort_hours / hours


def preference_fit(resource: Resource, preferences: list[str]) -> float:
    """1 if the resource matches any of the user's learning preferences, NO_PREFERENCE_MATCH if not,
    NEUTRAL when the user gave none that can be matched."""
    usable = [p for p in preferences if p in PREFERENCE_MATCH]
    if not usable:
        return NEUTRAL
    return 1.0 if any(PREFERENCE_MATCH[p](resource) for p in usable) else NO_PREFERENCE_MATCH


def quality_fit(resource: Resource, source: str) -> float:
    """From the source's own signals; never from an LLM."""
    q = resource.quality
    if q is None:
        return CURATED_QUALITY if source == "knowledge_base" else NEUTRAL
    parts = []
    if q.views:
        parts.append(min(1.0, math.log10(q.views) / math.log10(VIEWS_FOR_FULL)))
        if q.likes is not None:
            parts.append(min(1.0, q.likes / q.views / GOOD_LIKE_RATE))
    value = sum(parts) / len(parts) if parts else NEUTRAL
    return round(max(value, TRUSTED_QUALITY) if q.trusted else value, 3)


def score(candidate: Candidate, gap: Gap, profile: SearchProfile) -> tuple[float, ScoreBreakdown]:
    r = candidate.resource
    breakdown = ScoreBreakdown(
        relevance=candidate.match_score,
        level=level_fit(r.level, profile.ai_level),
        domain=domain_fit(r.domains, profile.domain),
        time=time_fit(r.hours, gap.effort_hours),
        preference=preference_fit(r, profile.preferences),
        quality=quality_fit(r, candidate.source),
    )
    total = sum(WEIGHTS[k] * v for k, v in breakdown.model_dump().items())
    return round(total, 3), breakdown


def rank(candidates: list[Candidate], gap: Gap, profile: SearchProfile) -> list[RankedResource]:
    """Score every candidate for the gap, best first."""
    ranked = []
    for c in candidates:
        total, breakdown = score(c, gap, profile)
        ranked.append(
            RankedResource(resource=c.resource, score=total, breakdown=breakdown, matched_on=c.matched_on, source=c.source)
        )
    ranked.sort(key=lambda r: (-r.score, r.resource.id))
    return ranked


def diversify(ranked: list[RankedResource], n: int) -> list[RankedResource]:
    """Pick n resources greedily by score, penalizing formats and costs already picked, so the
    default list mixes courses, papers and projects, and free and paid resources."""
    pool, picked = list(ranked), []
    while pool and len(picked) < n:

        def adjusted(r: RankedResource) -> float:
            same_format = sum(p.resource.format == r.resource.format for p in picked)
            same_cost = sum(p.resource.cost == r.resource.cost for p in picked)
            return r.score - FORMAT_PENALTY * same_format - COST_PENALTY * same_cost

        best = max(pool, key=adjusted)  # first max wins, so ties keep score order
        picked.append(best)
        pool.remove(best)
    return picked
