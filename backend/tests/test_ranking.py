"""Ranking factors, diversity, de-duplication and the assembled per-gap list (pure functions)."""
import pytest

from core.agents.course_search import ranking, search
from core.agents.course_search.ranking import diversify, domain_fit, level_fit, rank, score, time_fit
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, Resource, SearchProfile

BEGINNER = SearchProfile(ai_level="None", domain="FinTech", hours_per_week=5)


def res(id, level="beginner", domains=(), hours=10, format="course", cost="free", url=None):
    return Resource(id=id, title=id, provider="p", url=url or f"https://example.com/{id}", format=format,
                    level=level, cost=cost, hours=hours, skills=["machine-learning"], domains=list(domains),
                    description="d")


def cand(resource, match=1.0, matched_on=("machine-learning",)):
    return Candidate(resource=resource, match_score=match, matched_on=list(matched_on))


def gap(skill="ML basics", effort=20, priority="high"):
    return Gap(skill=skill, category="technical", why_needed="w", priority=priority, effort_hours=effort,
               domain_specific=False, current_level="Beginner", target_level="Intermediate")


def test_weights_sum_to_one():
    assert sum(ranking.WEIGHTS.values()) == pytest.approx(1.0)


def test_level_fit():
    assert level_fit("beginner", "None") == 1.0
    assert level_fit("beginner", "Beginner") == 1.0
    assert level_fit("intermediate", "Beginner") == 0.5
    assert level_fit("advanced", "None") == 0.0
    assert level_fit("advanced", "Experienced") == 1.0
    assert level_fit("beginner", "Experienced") == 0.0


def test_domain_fit():
    assert domain_fit(["FinTech"], "FinTech") == 1.0
    assert domain_fit([], "FinTech") == 0.6
    assert domain_fit(["Healthcare"], "FinTech") == 0.1


def test_time_fit():
    assert time_fit(10, 20) == 1.0
    assert time_fit(20, 20) == 1.0
    assert time_fit(40, 20) == 0.5
    assert time_fit(200, 20) == pytest.approx(0.1)


def test_score_is_weighted_sum_with_breakdown():
    total, b = score(cand(res("x", level="intermediate", hours=40), match=0.8), gap(effort=20), BEGINNER)
    assert (b.relevance, b.level, b.domain, b.time) == (0.8, 0.5, 0.6, 0.5)
    assert total == pytest.approx(0.45 * 0.8 + 0.2 * 0.5 + 0.2 * 0.6 + 0.15 * 0.5, abs=1e-3)


def test_beginner_resource_outranks_advanced_for_new_user():
    ranked = rank([cand(res("adv", level="advanced")), cand(res("beg"))], gap(), BEGINNER)
    assert [r.resource.id for r in ranked] == ["beg", "adv"]


def test_domain_resource_outranks_general_and_other_domain():
    cands = [cand(res("health", domains=["Healthcare"])), cand(res("general")), cand(res("fin", domains=["FinTech"]))]
    assert [r.resource.id for r in rank(cands, gap(), BEGINNER)] == ["fin", "general", "health"]


def test_shorter_resource_outranks_one_far_over_the_gap_effort():
    ranked = rank([cand(res("long", hours=120)), cand(res("short", hours=10))], gap(effort=20), BEGINNER)
    assert ranked[0].resource.id == "short"


def test_relevance_dominates():
    ranked = rank([cand(res("fits-but-off-topic", domains=["FinTech"]), match=0.3), cand(res("on-topic"), match=1.0)],
                  gap(), BEGINNER)
    assert ranked[0].resource.id == "on-topic"


def test_diversify_mixes_formats_and_costs():
    ranked = rank(
        [cand(res("c1")), cand(res("c2")), cand(res("c3")),
         cand(res("proj", format="project"), match=0.9), cand(res("paid", cost="paid"), match=0.9)],
        gap(), BEGINNER,
    )
    picked = [r.resource.id for r in diversify(ranked, 3)]
    assert picked[0] == "c1"
    assert "proj" in picked and "paid" in picked  # beat the slightly higher-scoring duplicate courses
    assert len(diversify(ranked, 10)) == 5


def test_merge_dedupe_collapses_same_url():
    a = cand(res("kb", url="https://example.com/course/"), match=0.6, matched_on=["python"])
    b = cand(res("web", url="https://EXAMPLE.com/course"), match=0.9, matched_on=["pandas"])
    [merged] = search.merge_dedupe([a, b])
    assert merged.resource.id == "web" and merged.match_score == 0.9
    assert merged.matched_on == ["pandas", "python"]


class FakeRetriever:
    """Stands in for any Retriever implementation (e.g. a future vector retriever)."""

    def __init__(self, by_skill):
        self.by_skill = by_skill
        self.calls = []

    def search(self, gap, profile, limit=10):
        self.calls.append((gap.skill, profile.domain, limit))
        return self.by_skill.get(gap.skill, [])[:limit]


def test_find_resources_with_any_retriever():
    shared = res("shared")
    retriever = FakeRetriever({
        "Low gap": [cand(shared, match=1.0)],
        "High gap": [cand(shared, match=0.8), cand(res("own", format="project"))],
        "Covered gap": [cand(res("own", format="project"), match=0.8)],
    })
    gaps = [gap("Low gap", priority="low"), gap("High gap"), gap("Covered gap", priority="medium"), gap("Unknown gap")]
    result = search.find_resources(gaps, BEGINNER, retriever=retriever)

    assert [g.gap.skill for g in result.gaps] == ["High gap", "Unknown gap", "Covered gap", "Low gap"]
    by_skill = {g.gap.skill: g for g in result.gaps}
    # "shared" scores best for Low gap, so it is shown only there, noting the other gap it covers.
    assert [r.resource.id for r in by_skill["Low gap"].resources] == ["shared"]
    assert by_skill["Low gap"].resources[0].also_covers == ["High gap"]
    assert [r.resource.id for r in by_skill["High gap"].resources] == ["own"]
    assert by_skill["Covered gap"].resources == [] and "other skills" in by_skill["Covered gap"].note
    assert by_skill["Unknown gap"].resources == [] and by_skill["Unknown gap"].note == search.NO_MATCH
    assert all(limit == search.RETRIEVE_LIMIT for _, _, limit in retriever.calls)


def test_relevance_gate_decides_what_is_shown_and_fit_only_ranks():
    retriever = FakeRetriever({"ML basics": [
        cand(res("off-topic", domains=["FinTech"]), match=0.6),  # fits perfectly otherwise, but below the gate
        cand(res("poor-fit", level="advanced", domains=["Healthcare"], hours=200, format="book"), match=0.8),
        cand(res("good"), match=1.0),
    ]})
    [g] = search.find_resources([gap()], BEGINNER, retriever=retriever).gaps
    assert [r.resource.id for r in g.resources] == ["good", "poor-fit"]  # poor fit ranks last but is shown


def test_relevance_gate_needs_a_specific_tag():
    # "PCI-DSS for ML" has the specific tag pci-dss and the broad tag machine-learning.
    retriever = FakeRetriever({"PCI-DSS for ML": [
        cand(res("broad-only"), match=1.0, matched_on=["machine-learning"]),
        cand(res("pci-partial"), match=0.667, matched_on=["pci-dss"]),
        cand(res("pci"), match=0.8, matched_on=["pci-dss"]),
    ]})
    [g] = search.find_resources([gap("PCI-DSS for ML")], BEGINNER, retriever=retriever).gaps
    assert [r.resource.id for r in g.resources] == ["pci"]


def test_per_gap_limit():
    retriever = FakeRetriever({"ML basics": [cand(res(f"r{i}")) for i in range(10)]})
    [g] = search.find_resources([gap()], BEGINNER, retriever=retriever, per_gap=4).gaps
    assert len(g.resources) == 4
