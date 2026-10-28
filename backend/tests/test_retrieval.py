"""Tag extraction, the TagRetriever, and the validity of the seed knowledge base."""
from collections import Counter

from core.agents.gap_analysis.schemas import Gap
from core.config import load_domains
from core.knowledge.retriever import DOMAIN_BOOST, TagRetriever, extract_tags, get_retriever
from core.knowledge.schemas import KnowledgeBase, SearchProfile
from core.knowledge.store import load_knowledge_base

VOCAB = {
    "machine-learning": ["machine learning", "ml"],
    "pci-dss": ["pci dss", "payment card"],
    "rag": ["rag", "vector databases"],
    "sql": ["sql", "relational databases"],
    "fraud-detection": ["fraud"],
}
PROFILE = SearchProfile(ai_level="Beginner", domain="FinTech", hours_per_week=8)


def gap(skill, why="Needed for the role.", domain_specific=False):
    return Gap(skill=skill, category="technical", why_needed=why, priority="high", effort_hours=20,
               domain_specific=domain_specific)


def resource(id, skills, domains=()):
    return {"id": id, "title": id, "provider": "p", "url": f"https://example.com/{id}", "format": "course",
            "level": "beginner", "cost": "free", "hours": 5, "skills": list(skills), "domains": list(domains),
            "description": "d"}


KB = KnowledgeBase.model_validate({
    "tags": VOCAB,
    "broad_tags": ["machine-learning"],
    "resources": [
        resource("ml-course", ["machine-learning"]),
        resource("pci-guide", ["pci-dss"]),
        resource("pci-ml", ["pci-dss", "machine-learning"]),
        resource("fraud-general", ["fraud-detection"]),
        resource("fraud-fintech", ["fraud-detection"], ["FinTech"]),
    ],
})


def test_extract_tags_matches_whole_words_and_aliases():
    assert extract_tags("ML fundamentals", VOCAB) == {"machine-learning"}
    assert extract_tags("HTML and CSS", VOCAB) == set()  # "ml" is not a word here
    assert extract_tags("PCI-DSS for payments", VOCAB) == {"pci-dss"}  # punctuation normalized
    assert extract_tags("Vector databases for RAG", VOCAB) == {"rag"}  # not "sql"


def test_retriever_scores_by_weighted_tag_overlap():
    results = TagRetriever(KB).search(gap("PCI-DSS for ML"), PROFILE)
    scores = {c.resource.id: c.match_score for c in results}
    # Tags: pci-dss (1) + machine-learning (broad, 0.5) = 1.5
    assert scores == {"pci-ml": 1.0, "pci-guide": round(1 / 1.5, 3), "ml-course": round(0.5 / 1.5, 3)}
    assert [c.resource.id for c in results][0] == "pci-ml"
    assert results[0].matched_on == ["machine-learning", "pci-dss"]


def test_broad_only_gap_is_not_a_full_match():
    [c] = TagRetriever(KB).search(gap("Machine learning basics"), PROFILE, limit=1)
    assert c.match_score == 0.5


def test_domain_boost_only_for_domain_specific_gaps():
    plain = {c.resource.id: c.match_score for c in TagRetriever(KB).search(gap("Fraud models"), PROFILE)}
    assert plain == {"fraud-general": 1.0, "fraud-fintech": 1.0}
    boosted = TagRetriever(KB).search(gap("Fraud models", domain_specific=True), PROFILE)
    assert boosted[0].resource.id == "fraud-fintech" and boosted[0].match_score == 1.0  # capped
    other = SearchProfile(ai_level="Beginner", domain="Retail", hours_per_week=8)
    assert all(c.match_score == 1.0 for c in TagRetriever(KB).search(gap("Fraud", domain_specific=True), other))
    assert DOMAIN_BOOST > 0


def test_falls_back_to_why_needed_and_handles_no_match():
    r = TagRetriever(KB)
    assert r.search(gap("Payments security", why="Handling payment card data safely."), PROFILE)[0].resource.id == "pci-guide"
    assert r.search(gap("Juggling", why="Circus skills."), PROFILE) == []


def test_limit():
    assert len(TagRetriever(KB).search(gap("PCI-DSS for ML"), PROFILE, limit=2)) == 2


# --- seed knowledge base ------------------------------------------------------------


def test_seed_knowledge_base_is_valid():
    kb = load_knowledge_base()  # Pydantic validates every field
    resources = kb.resources
    assert 30 <= len(resources) <= 50
    assert len({r.id for r in resources}) == len(resources)
    assert len({str(r.url) for r in resources}) == len(resources)
    assert all(r.url.scheme == "https" for r in resources)
    assert set(kb.broad_tags) <= set(kb.tags)
    for r in resources:
        assert set(r.skills) <= set(kb.tags), r.id
        assert set(r.domains) <= set(load_domains()), r.id


def test_seed_knowledge_base_has_a_mix():
    resources = load_knowledge_base().resources
    per_domain = Counter(d for r in resources for d in r.domains)
    for domain in load_domains():
        if domain != "Other":
            assert per_domain[domain] >= 2, domain
    assert sum(not r.domains for r in resources) >= 15  # general resources
    assert {r.cost for r in resources} == {"free", "paid"}
    assert {"course", "paper", "project"} <= {r.format for r in resources}
    assert {r.level for r in resources} == {"beginner", "intermediate", "advanced"}


def test_seed_vocabulary_matches_typical_gap_names():
    retriever = get_retriever()
    for name in ["Python for ML", "Deep learning with PyTorch", "RAG pipelines", "MLOps and model deployment",
                 "Statistics and probability", "Fraud detection modeling", "HIPAA-compliant data handling",
                 "Demand forecasting", "Recommender systems", "Prompt engineering"]:
        assert retriever.search(gap(name), PROFILE), name
