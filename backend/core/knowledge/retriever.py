"""Retrieval layer: turns one skill gap into candidate resources.

Everything downstream (ranking, API, UI) depends only on the Retriever protocol and the
Candidate it returns, so a vector retriever (local embeddings + sqlite-vec) can replace
TagRetriever by changing get_retriever() alone.
"""
import re
from functools import lru_cache
from typing import Protocol

from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, KnowledgeBase, SearchProfile
from core.knowledge.store import load_knowledge_base

DOMAIN_BOOST = 0.2  # added for resources in the user's domain when the gap is domain-specific
BROAD_WEIGHT = 0.5  # weight of a broad tag ("machine-learning") relative to a specific one


class Retriever(Protocol):
    def search(self, gap: Gap, profile: SearchProfile, limit: int = 10) -> list[Candidate]:
        """Return up to `limit` candidates for the gap, best match first."""
        ...


def normalize(text: str) -> str:
    """Lowercase, turn punctuation into spaces and pad, so phrases match on word boundaries."""
    return f" {' '.join(re.sub(r'[^a-z0-9+#]+', ' ', text.lower()).split())} "


def extract_tags(text: str, vocabulary: dict[str, list[str]]) -> set[str]:
    """Tags whose name or any alias appears in the text as whole words ("ml" does not match "html")."""
    haystack = normalize(text)
    return {
        tag
        for tag, aliases in vocabulary.items()
        if any(normalize(phrase) in haystack for phrase in [tag, *aliases])
    }


def gap_tags(gap: Gap, vocabulary: dict[str, list[str]]) -> set[str]:
    # The skill name is the precise signal; the explanation is a fallback for unusual names.
    return extract_tags(gap.skill, vocabulary) or extract_tags(gap.why_needed, vocabulary)


class TagRetriever:
    """Matches the gap's skill name against the tag vocabulary, then scores each resource by
    the (weighted) share of the gap's tags it covers."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.broad = set(kb.broad_tags)

    def gap_tags(self, gap: Gap) -> set[str]:
        return gap_tags(gap, self.kb.tags)

    def _weight(self, tag: str) -> float:
        return BROAD_WEIGHT if tag in self.broad else 1.0

    def search(self, gap: Gap, profile: SearchProfile, limit: int = 10) -> list[Candidate]:
        tags = self.gap_tags(gap)
        if not tags:
            return []
        # At least 1, so a gap matching only broad tags ("ML fundamentals") never gives a full match
        # and a resource fitting a more specific gap scores higher there.
        total = max(sum(self._weight(t) for t in tags), 1.0)
        candidates = []
        for resource in self.kb.resources:
            overlap = tags & set(resource.skills)
            if not overlap:
                continue
            score = sum(self._weight(t) for t in overlap) / total
            if gap.domain_specific and profile.domain in resource.domains:
                score += DOMAIN_BOOST
            candidates.append(
                Candidate(resource=resource, match_score=round(min(score, 1.0), 3), matched_on=sorted(overlap))
            )
        candidates.sort(key=lambda c: (-c.match_score, c.resource.id))
        return candidates[:limit]


@lru_cache
def get_retriever() -> Retriever:
    """The one place that picks the retrieval implementation."""
    return TagRetriever(load_knowledge_base())
