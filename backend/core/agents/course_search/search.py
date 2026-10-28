"""Course search pipeline: retrieve -> merge_dedupe -> rank -> present.

Each step is a plain function over plain data. graph.py wraps them as LangGraph nodes, with
live web search before merge_dedupe and URL verification before rank.
"""
from core.agents.course_search.ranking import diversify, rank
from core.agents.course_search.schemas import GapResources, RankedResource, ResourceList
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.retriever import Retriever, gap_tags, get_retriever
from core.knowledge.schemas import Candidate, SearchProfile
from core.knowledge.store import load_knowledge_base

PER_GAP = 4  # resources shown per gap
RETRIEVE_LIMIT = 12  # candidates fetched per gap before ranking
MIN_RELEVANCE = 0.7  # the relevance gate; level, domain and time only rank what passes it
PRIORITY = {"high": 0, "medium": 1, "low": 2}

NO_MATCH = "No resources found for this skill yet. Ask in the chat to search for more."
COVERED_ELSEWHERE = "Covered by resources listed under other skills (see “Also covers”)."


def url_key(url) -> str:
    return str(url).lower().rstrip("/")


def specific_tags(gap: Gap) -> set[str]:
    kb = load_knowledge_base()
    return gap_tags(gap, kb.tags) - set(kb.broad_tags)


def passes(r: RankedResource, gap: Gap) -> bool:
    """The relevance gate: relevance >= MIN_RELEVANCE and at least one of the gap's specific (not
    broad) tags matched, so a resource sharing only "machine-learning" or one tag of several is
    not shown however well it fits otherwise. A gap without specific tags can only be gated on
    relevance (its curated matches are capped below the gate; web results carry the model's rating)."""
    if r.breakdown.relevance < MIN_RELEVANCE:
        return False
    tags = specific_tags(gap)
    return not tags or bool(tags & set(r.matched_on))


def retrieve(gaps: list[Gap], profile: SearchProfile, retriever: Retriever) -> list[list[Candidate]]:
    """Candidates for each gap, in the same order as `gaps`."""
    return [retriever.search(gap, profile, limit=RETRIEVE_LIMIT) for gap in gaps]


def merge_dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse candidates with the same URL (e.g. found in the knowledge base and on the web),
    keeping the best match score and all matched terms. The curated entry wins over a web one,
    so its reviewed details are the ones shown."""
    merged: dict[str, Candidate] = {}
    for c in candidates:
        key = url_key(c.resource.url)
        seen = merged.get(key)
        if seen is None:
            merged[key] = c
            continue
        if seen.source != c.source:
            best = seen if seen.source == "knowledge_base" else c
        else:
            best = c if c.match_score > seen.match_score else seen
        merged[key] = best.model_copy(
            update={
                "match_score": max(seen.match_score, c.match_score),
                "matched_on": sorted(set(seen.matched_on) | set(c.matched_on)),
            }
        )
    return list(merged.values())


def present(gaps: list[Gap], ranked: list[list[RankedResource]], per_gap: int = PER_GAP) -> ResourceList:
    """Build the final list: gaps by priority, up to `per_gap` diverse resources each that pass the
    relevance gate. A resource
    that fits several gaps is shown once, under the gap it scores best for, with "also covers"."""
    order = sorted(range(len(gaps)), key=lambda i: PRIORITY[gaps[i].priority])  # stable: ties keep input order
    ranked = [[r for r in rs if passes(r, gap)] for rs, gap in zip(ranked, gaps)]

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
