"""Deterministic ranking of candidate resources for one gap. Pure functions: no I/O, no LLM.

score = relevance (the retriever's match_score) + fit with the user's AI level
      + applicability to their industry domain + time cost relative to the gap's effort.
"""
from core.agents.course_search.schemas import RankedResource, ScoreBreakdown
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, Level, SearchProfile

WEIGHTS = {"relevance": 0.45, "level": 0.20, "domain": 0.20, "time": 0.15}

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


def score(candidate: Candidate, gap: Gap, profile: SearchProfile) -> tuple[float, ScoreBreakdown]:
    r = candidate.resource
    breakdown = ScoreBreakdown(
        relevance=candidate.match_score,
        level=level_fit(r.level, profile.ai_level),
        domain=domain_fit(r.domains, profile.domain),
        time=time_fit(r.hours, gap.effort_hours),
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
