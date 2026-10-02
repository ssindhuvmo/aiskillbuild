"""Course search pipeline: retrieve -> merge_dedupe -> rank -> present.

Each step is a plain function over plain data so milestone 5 can wrap them as LangGraph
nodes (adding live web search before merge_dedupe and URL verification before rank).
"""
from core.agents.course_search.ranking import diversify, rank
from core.agents.course_search.schemas import GapResources, RankedResource, ResourceList
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.retriever import Retriever, get_retriever
from core.knowledge.schemas import Candidate, SearchProfile

PER_GAP = 4  # resources shown per gap
RETRIEVE_LIMIT = 12  # candidates fetched per gap before ranking
MIN_SCORE = 0.55  # weaker matches (e.g. another industry's compliance guide) are not shown
MIN_RELEVANCE = 0.5  # a resource must cover at least half of what the gap needs, however well it fits otherwise
PRIORITY = {"high": 0, "medium": 1, "low": 2}

NO_MATCH = "No curated resources match this skill yet. Live web search (next milestone) will fill this in."
COVERED_ELSEWHERE = "Covered by resources listed under other skills (see “Also covers”)."


def url_key(url) -> str:
    return str(url).lower().rstrip("/")


def retrieve(gaps: list[Gap], profile: SearchProfile, retriever: Retriever) -> list[list[Candidate]]:
    """Candidates for each gap, in the same order as `gaps`."""
    return [retriever.search(gap, profile, limit=RETRIEVE_LIMIT) for gap in gaps]


def merge_dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse candidates with the same URL (e.g. found in the knowledge base and on the web),
    keeping the best match score and all matched terms."""
    merged: dict[str, Candidate] = {}
    for c in candidates:
        key = url_key(c.resource.url)
        seen = merged.get(key)
        if seen is None:
            merged[key] = c
            continue
        best = c if c.match_score > seen.match_score else seen
        merged[key] = best.model_copy(update={"matched_on": sorted(set(seen.matched_on) | set(c.matched_on))})
    return list(merged.values())


def present(gaps: list[Gap], ranked: list[list[RankedResource]], per_gap: int = PER_GAP) -> ResourceList:
    """Build the final list: gaps by priority, up to `per_gap` diverse resources each that pass
    MIN_SCORE and MIN_RELEVANCE. A resource
    that fits several gaps is shown once, under the gap it scores best for, with "also covers"."""
    order = sorted(range(len(gaps)), key=lambda i: PRIORITY[gaps[i].priority])  # stable: ties keep input order
    ranked = [[r for r in rs if r.score >= MIN_SCORE and r.breakdown.relevance >= MIN_RELEVANCE] for rs in ranked]

    # The gap each resource scores best for (ties go to the higher-priority gap).
    owner: dict[str, int] = {}
    best_score: dict[str, float] = {}
    for i in order:
        for r in ranked[i]:
            key = url_key(r.resource.url)
            if key not in owner or r.score > best_score[key]:
                owner[key], best_score[key] = i, r.score

    picks: dict[int, list[RankedResource]] = {
        i: diversify([r for r in ranked[i] if owner[url_key(r.resource.url)] == i], per_gap) for i in order
    }
    # Top up gaps that came up short with resources not shown anywhere else.
    shown = {url_key(r.resource.url) for rs in picks.values() for r in rs}
    for i in order:
        if len(picks[i]) < per_gap:
            extra = diversify([r for r in ranked[i] if url_key(r.resource.url) not in shown], per_gap - len(picks[i]))
            picks[i] += extra
            shown |= {url_key(r.resource.url) for r in extra}

    matched_by: dict[str, list[int]] = {}
    for i in order:
        for r in ranked[i]:
            matched_by.setdefault(url_key(r.resource.url), []).append(i)

    result = []
    for i in order:
        resources = [
            r.model_copy(update={"also_covers": [gaps[j].skill for j in matched_by[url_key(r.resource.url)] if j != i]})
            for r in picks[i]
        ]
        note = None if resources else (COVERED_ELSEWHERE if ranked[i] else NO_MATCH)
        result.append(GapResources(gap=gaps[i], resources=resources, note=note))
    return ResourceList(gaps=result)


def find_resources(
    gaps: list[Gap], profile: SearchProfile, retriever: Retriever | None = None, per_gap: int = PER_GAP
) -> ResourceList:
    retriever = retriever or get_retriever()
    candidates = [merge_dedupe(c) for c in retrieve(gaps, profile, retriever)]
    ranked = [rank(c, gap, profile) for c, gap in zip(candidates, gaps)]
    return present(gaps, ranked, per_gap)
