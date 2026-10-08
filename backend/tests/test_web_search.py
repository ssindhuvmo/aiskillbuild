"""Live web search and URL verification without the network: a fake Anthropic client returns
search-result blocks and a record_resources call."""
from types import SimpleNamespace

import pytest

from core.agents.course_search import verify, web
from core.agents.course_search.search import merge_dedupe
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, Resource, SearchProfile

GAP = Gap(skill="Vector databases", category="technical", why_needed="Needed for retrieval.", priority="high",
          effort_hours=20, domain_specific=False)
PROFILE = SearchProfile(ai_experience="Beginner", domain="FinTech", hours_per_week=8)


def finding(url="https://example.com/vectors", **overrides):
    return {"title": "Vector DB course", "provider": "Example U", "url": url, "format": "course", "level": "beginner",
            "cost": "free", "hours": 10, "description": "Learn vector search.", "relevance": 0.8, **overrides}


def results(*urls):
    return SimpleNamespace(type="web_search_tool_result", content=[SimpleNamespace(url=u, title="t") for u in urls])


def record(*findings):
    return SimpleNamespace(type="tool_use", name="record_resources", input={"resources": list(findings)})


def reply(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw)
        return self.replies.pop(0)


@pytest.fixture()
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(web, "get_client", lambda: client)
        return client

    return install


def search(hint=None):
    return web.AnthropicWebSearcher().search(GAP, PROFILE, hint)


def test_findings_become_web_candidates(fake):
    client = fake(reply(results("https://example.com/vectors"), record(finding(domain_specific=True))))
    [c] = search(hint="Free resources only.")
    assert c.source == "web" and c.match_score == 0.8 and c.matched_on == ["Vector databases"]
    assert c.resource.id == web.web_id("https://example.com/vectors") and c.resource.id.startswith("web-")
    assert c.resource.skills == ["Vector databases"] and c.resource.domains == ["FinTech"]
    request = client.requests[0]
    assert "Vector databases" in request["messages"][0]["content"] and "Free resources only." in request["messages"][0]["content"]
    assert {t["name"] for t in request["tools"]} == {"web_search", "record_resources"}


def test_url_not_in_the_search_results_is_discarded(fake):
    fake(reply(
        results("https://example.com/vectors/"),  # trailing slash and case don't matter
        record(finding("https://Example.com/vectors"), finding("https://invented.example.org/course")),
    ))
    assert [str(c.resource.url) for c in search()] == ["https://example.com/vectors"]


def test_relevance_is_capped_and_invalid_findings_are_dropped(fake):
    fake(reply(
        results("https://example.com/a", "https://example.com/b", "https://example.com/c"),
        record(
            finding("https://example.com/a", relevance=1.0),
            finding("https://example.com/b", hours=0),  # out of range
            finding("https://example.com/c", format="podcast"),  # not a known format
            "not an object",
        ),
    ))
    [c] = search()
    assert c.match_score == web.MAX_RELEVANCE == 0.9


def test_failed_search_or_no_record_gives_no_results(fake):
    error = SimpleNamespace(type="web_search_tool_result", content=SimpleNamespace(error_code="max_uses_exceeded"))
    fake(reply(error, record(finding())))
    assert search() == []  # the URL was never in a search result
    fake(reply(SimpleNamespace(type="text", text="Nothing found."), stop_reason="end_turn"))
    assert search() == []


def test_paused_turn_is_continued(fake):
    client = fake(
        reply(results("https://example.com/vectors"), stop_reason="pause_turn"),
        reply(record(finding())),
    )
    assert len(search()) == 1
    assert client.requests[1]["messages"][1]["role"] == "assistant"  # the paused turn is sent back


def test_curated_entry_wins_over_the_same_url_from_the_web():
    def cand(rid, source, score):
        r = Resource(id=rid, title=rid, provider="p", url="https://example.com/x", format="course", level="beginner",
                     cost="free", hours=5, skills=["s"], description="d")
        return Candidate(resource=r, match_score=score, matched_on=[rid], source=source)

    [c] = merge_dedupe([cand("web-1", "web", 0.9), cand("kb-1", "knowledge_base", 0.5)])
    assert c.resource.id == "kb-1" and c.source == "knowledge_base" and c.match_score == 0.9


def test_link_check_refuses_non_http_and_private_addresses():
    assert verify.check("ftp://example.com/file") == ("fail", "not an http(s) URL")
    assert verify.check("http://127.0.0.1:8000/api/health") == ("fail", "not a public address")
    assert verify.check("http://192.168.1.10/") == ("fail", "not a public address")
