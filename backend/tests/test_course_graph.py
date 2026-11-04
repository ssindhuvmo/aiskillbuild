"""The course search / refinement graph end to end through the API, with a fake LLM, a fake web
searcher and a fake link checker (no network): build, pause, refine by chat, resume, approve."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core import db as dbmod
from core.agents.course_search import agent, graph
from core.agents.course_search.web import web_id
from core.agents.gap_analysis.schemas import Gap
from core.agents.scheduler import narrative as scheduler
from core.knowledge.retriever import get_retriever
from core.knowledge.schemas import Candidate, Resource, SearchProfile
from core.models import ApprovedListRecord, WebResourceCandidate, WebSearchCache
from tests.conftest import login
from tests.test_gap_analysis import analysis, confirmed_user, gap
from tests.test_resources import fake_gaps, ids_of  # noqa: F401  (fixture)
from tests.test_roadmap import generate, phase_reply
from tests.test_scheduler_budget import FakeClient as FakeScheduler

# The knowledge base has plenty for the first gap, none passing the relevance gate for the second
# (pci-dss is only 1 of its 1.5 tag weight) and nothing at all for the third.
CURATED, PCI, QUANTUM = "Deep learning", "PCI-DSS for ML", "Quantum widgets"
GAPS = ((CURATED, 40), (QUANTUM, 10))  # so only QUANTUM is web-searched when the list is built


def found(name, **overrides):
    """A web candidate as the searcher would return it."""
    url = f"https://example.com/{name}"
    fields = dict(title=f"Web {name}", provider="Example U", url=url, format="course", level="beginner",
                  cost="free", hours=5, skills=[QUANTUM], description="Found on the web.")
    return Candidate(resource=Resource(id=web_id(url), **{**fields, **overrides}), match_score=0.9, matched_on=[QUANTUM], source="web")


class FakeStream:
    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeLLM:
    """messages.create returns each scripted action as JSON text (the interpreter); messages.stream
    writes a fixed explanation and records the changes it was asked to explain."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.requests, self.explained = [], []
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def _create(self, **kw):
        self.requests.append(kw["messages"][0]["content"])
        text = json.dumps(self.actions.pop(0))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    def _stream(self, **kw):
        self.explained.append(json.loads(kw["messages"][0]["content"]))
        return FakeStream(["Updated ", "your list."])


@pytest.fixture()
def llm(monkeypatch):
    def install(*actions):
        client = FakeLLM(actions)
        monkeypatch.setattr(graph, "get_client", lambda: client)
        return client

    return install


def ready_user(client, sub, fake_gaps, searcher, web=(), gaps=GAPS):  # noqa: F811
    """Signed in with confirmed gaps and a built list; `web` is what the search finds for QUANTUM."""
    confirmed_user(client, sub)
    fake_gaps(analysis(gaps=gaps))
    assert client.post("/api/gaps/analyze", json={}).status_code == 200
    assert client.post("/api/gaps/confirm").status_code == 200
    searcher.results[QUANTUM] = list(web)
    r = client.post("/api/resources/search")
    assert r.status_code == 200, r.text
    return r.json()


def chat(client, message):
    """Send a chat message; returns (events, reply text, final state or None)."""
    r = client.post("/api/resources/chat", json={"message": message})
    assert r.status_code == 200, r.text
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    reply = "".join(e["text"] for e in events if e["type"] == "token")
    state = next((e["resources"] for e in events if e["type"] == "state"), None)
    return events, reply, state


def quantum(state):
    return next(g for g in state["resources"]["gaps"] if g["gap"]["skill"] == QUANTUM)


def test_build_merges_curated_and_verified_web_results(anon, fake_gaps, searcher, caplog):  # noqa: F811
    caplog.set_level("INFO", logger="core")
    profile = SearchProfile(ai_level="Beginner", domain="FinTech", hours_per_week=8)
    curated = get_retriever().search(Gap(**gap(PCI, 10)), profile)[0].resource
    searcher.results[PCI] = [found("dup", url=str(curated.url), title="Same page, found on the web")]
    searcher.results[CURATED] = [found("unwanted")]
    searcher.link_status = {"https://example.com/dead": "fail", "https://example.com/blocked": "blocked"}
    state = ready_user(
        anon, "cg1", fake_gaps, searcher, web=[found("a"), found("dead"), found("blocked")],
        gaps=((CURATED, 40), (PCI, 10), (QUANTUM, 10)),
    )

    assert state["status"] == "ready" and not state["stale"] and state["messages"] == [] and state["notice"] is None
    # Only gaps the knowledge base covers thinly are searched: deep learning has plenty of curated resources.
    assert sorted(s for s, _ in searcher.calls) == [PCI, QUANTUM]
    assert "Web search run: 2 of 3 gaps searched" in caplog.text  # the cost of the run is logged
    assert "Web unwanted" not in [r["resource"]["title"] for g in state["resources"]["gaps"] for r in g["resources"]]
    web_items = quantum(state)["resources"]
    assert {r["resource"]["title"] for r in web_items} == {"Web a", "Web blocked"}  # the dead link is dropped
    assert all(r["source"] == "web" and r["resource"]["id"].startswith("web-") for r in web_items)
    # The URL found both in the knowledge base and on the web is listed once, as the curated entry.
    same = [r for g in state["resources"]["gaps"] for r in g["resources"] if r["resource"]["url"] == str(curated.url)]
    assert [r["resource"]["id"] for r in same] == [curated.id] and same[0]["source"] == "knowledge_base"


def test_remove_by_chat_updates_the_list_without_a_new_search(anon, fake_gaps, searcher, llm):  # noqa: F811
    before = ready_user(anon, "cg2", fake_gaps, searcher, web=[found("a"), found("b")])
    a = web_id("https://example.com/a")
    client = llm({"remove_ids": [a]})
    events, reply, state = chat(anon, "remove Web a")

    assert reply == "Updated your list." and events[-1]["type"] == "done"
    assert ids_of(state) == [i for i in ids_of(before) if i != a]
    assert state["messages"] == [{"role": "user", "content": "remove Web a"}, {"role": "assistant", "content": reply}]
    assert len(searcher.calls) == 1  # only the first build searched
    assert a in client.requests[0] and "remove Web a" in client.requests[0]
    assert client.explained[0]["removed"] == ["Web a"] and client.explained[0]["added"] == []
    assert anon.get("/api/resources").json() == state  # saved, and the graph is paused again


def test_remove_button_needs_no_llm_call(anon, fake_gaps, searcher, llm):  # noqa: F811
    assert anon.post("/api/resources/remove", json={"resource_id": "x"}).status_code == 401
    confirmed_user(anon, "cg17")
    assert anon.post("/api/resources/remove", json={"resource_id": "x"}).status_code == 409  # no list yet
    before = ready_user(anon, "cg17", fake_gaps, searcher, web=[found("a"), found("b")])
    a = web_id("https://example.com/a")
    client = llm()  # any model call would fail: nothing is scripted

    assert anon.post("/api/resources/remove", json={"resource_id": "not-on-my-list"}).status_code == 422
    state = anon.post("/api/resources/remove", json={"resource_id": a}).json()
    assert ids_of(state) == [i for i in ids_of(before) if i != a]
    assert state["messages"] == [] and client.requests == [] and client.explained == []
    assert len(searcher.calls) == 1 and anon.get("/api/resources").json() == state

    # It is the same operation the chat uses, so the chat can undo it.
    llm({"restore_ids": [a]})
    assert a in ids_of(chat(anon, "put Web a back")[2])


def test_prefer_free_filters_and_searches_again_only_for_an_emptied_gap(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg3", fake_gaps, searcher, web=[found("free"), found("paid", cost="paid")])
    llm({"cost": "free"}, {"cost": "any"}, {"cost": "paid"})
    _, _, state = chat(anon, "I prefer free ones")
    assert all(r["resource"]["cost"] == "free" for g in state["resources"]["gaps"] for r in g["resources"])
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web free"]
    assert len(searcher.calls) == 1  # the gap still has a free resource: no new search

    chat(anon, "paid ones are fine too")
    # Paid only: nothing curated or found for the gap is paid... except "Web paid", so still no search.
    _, _, state = chat(anon, "actually only paid ones")
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web paid"]
    assert len(searcher.calls) == 1


def test_cost_filter_that_empties_a_gap_triggers_a_search(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg4", fake_gaps, searcher, web=[found("paid", cost="paid")])
    searcher.results[QUANTUM] = [found("free")]
    client = llm({"cost": "free"})
    _, _, state = chat(anon, "free only please")
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web free"]
    skill, hint = searcher.calls[-1]
    assert len(searcher.calls) == 2 and skill == QUANTUM and "Free resources only." in hint
    # (A free curated resource may also move up to replace a paid one under the other gap.)
    assert "Web free" in [a["title"] for a in client.explained[0]["added"]]


def test_add_more_projects_searches_the_web_again(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg5", fake_gaps, searcher, web=[found("a")])
    searcher.results[QUANTUM] = [found("lab", format="project")]
    llm({"favour_formats": ["project"], "add_more": [{"skill": QUANTUM, "format": "project", "hint": "hands-on"}]})
    _, _, state = chat(anon, "add more hands-on projects")
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web lab", "Web a"]  # favoured format first
    skill, hint = searcher.calls[-1]
    assert len(searcher.calls) == 2 and skill == QUANTUM
    assert "project" in hint and "hands-on" in hint and "Web a" in hint  # told what is already listed


def test_known_skill_hides_the_gap_and_can_be_restored(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg6", fake_gaps, searcher, web=[found("a")])
    client = llm({"known_skills": [QUANTUM]}, {"restore_skills": [QUANTUM]})
    _, _, state = chat(anon, "I already know quantum widgets")
    assert quantum(state)["resources"] == [] and quantum(state)["note"] == graph.SKIPPED
    assert client.explained[0]["skipped_skills"] == [QUANTUM]
    _, _, state = chat(anon, "actually, bring it back")
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web a"]


def test_refinement_resumes_after_sign_out_and_sign_in(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg7", fake_gaps, searcher, web=[found("a"), found("b")])
    llm({"remove_ids": [web_id("https://example.com/a")]}, {"restore_ids": [web_id("https://example.com/a")]})
    _, _, state = chat(anon, "remove Web a")

    anon.post("/api/auth/logout")
    assert anon.get("/api/resources").status_code == 401
    login(anon, "cg7")
    assert anon.get("/api/resources").json() == state  # list and chat are back
    _, _, state = chat(anon, "put it back")
    assert {r["resource"]["title"] for r in quantum(state)["resources"]} == {"Web a", "Web b"}
    assert [m["content"] for m in state["messages"] if m["role"] == "user"] == ["remove Web a", "put it back"]


def test_unclear_message_gets_a_question_and_changes_nothing(anon, fake_gaps, searcher, llm):  # noqa: F811
    before = ready_user(anon, "cg8", fake_gaps, searcher, web=[found("a")])
    client = llm({"question": "Which resource do you mean?"})
    events, reply, state = chat(anon, "remove that one")
    assert reply == "Which resource do you mean?" and events[-1]["type"] == "done"
    assert state["resources"] == before["resources"] and client.explained == []
    assert [m["role"] for m in state["messages"]] == ["user", "assistant"]


def test_invalid_operations_are_retried_then_reported(anon, fake_gaps, searcher, llm):  # noqa: F811
    before = ready_user(anon, "cg9", fake_gaps, searcher, web=[found("a")])
    a = web_id("https://example.com/a")
    client = llm({"remove_ids": ["no-such-id"]}, {"remove_ids": [a]})
    _, _, state = chat(anon, "remove Web a")
    assert a not in ids_of(state)
    assert "rejected" not in client.requests[0] and "not an id on the current list" in client.requests[1]

    # Every attempt invalid: an error, and the list and chat stay as they were.
    llm(*[{"approve": True, "cost": "free"}] * graph.MAX_ATTEMPTS)
    events, _, after = chat(anon, "approve and make it free")
    assert [e["type"] for e in events] == ["error", "state", "done"] and events[0]["message"] == graph.NOT_UNDERSTOOD
    assert after == state and anon.get("/api/resources").json()["approved_ids"] is None
    assert before["status"] == "ready"

    # The graph is paused again, so the next message works.
    llm({"restore_ids": [a]})
    assert a in ids_of(chat(anon, "put Web a back")[2])


def test_llm_failure_in_chat_gives_a_friendly_error(anon, fake_gaps, searcher, llm, monkeypatch):  # noqa: F811
    state = ready_user(anon, "cg10", fake_gaps, searcher, web=[found("a")])
    monkeypatch.setattr("core.llm.ANTHROPIC_API_KEY", "")
    events, _, after = chat(anon, "remove Web a")
    assert events[0]["type"] == "error" and "ANTHROPIC_API_KEY" in events[0]["message"]
    assert after == state

    # The interpreter works but the explanation fails: the change is applied with a plain summary.
    client = llm({"remove_ids": [web_id("https://example.com/a")]})
    client.messages.stream = lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))
    _, reply, after = chat(anon, "remove Web a")
    assert reply.startswith('I updated your list: removed "Web a".') and quantum(after)["resources"] == []


def test_web_search_failure_falls_back_to_the_curated_library(anon, fake_gaps, searcher):  # noqa: F811
    confirmed_user(anon, "cg11")
    fake_gaps(analysis(gaps=GAPS))
    anon.post("/api/gaps/analyze", json={})
    anon.post("/api/gaps/confirm")
    searcher.results = {CURATED: RuntimeError("boom"), QUANTUM: RuntimeError("boom")}
    state = anon.post("/api/resources/search").json()
    assert state["status"] == "ready" and "curated library" in state["notice"]
    assert quantum(state)["resources"] == [] and len(ids_of(state)) >= 1
    assert all(r["source"] == "knowledge_base" for g in state["resources"]["gaps"] for r in g["resources"])


def test_approval_by_button_and_by_chat_feeds_the_scheduler(anon, fake_gaps, searcher, llm, monkeypatch):  # noqa: F811
    state = ready_user(anon, "cg12", fake_gaps, searcher, web=[found("a"), found("b")])
    a, ids = web_id("https://example.com/a"), ids_of(state)

    state = anon.post("/api/resources/approve").json()
    assert state["approved_ids"] == ids and state["approval_stale"] is False
    assert "approved" in state["messages"][-1]["content"]
    with dbmod.SessionLocal() as db:
        record = db.get(ApprovedListRecord, "cg12")
        assert record.approved_via == "refinement"
        assert a in [r["resource"]["id"] for r in record.items["resources"]]  # web results are approved in full

    # The scheduler reads that list unchanged; links come from it.
    monkeypatch.setattr(scheduler, "get_client", lambda: FakeScheduler([phase_reply] * 6))
    roadmap = generate(anon)[1]
    assert roadmap["stale"] is False
    links = {t["resource"]["id"]: t["resource"]["url"] for m in roadmap["roadmap"]["months"] for w in m["weeks"]
             for t in w["tasks"] if t["resource"]}
    assert links[a] == "https://example.com/a"  # placed by Python, linked from the approved web result

    # Refining after approval: the approval is out of date until the user approves again (here by chat).
    b = web_id("https://example.com/b")
    llm({"remove_ids": [b]}, {"approve": True})
    _, _, state = chat(anon, "remove Web b")
    assert state["approval_stale"] is True and anon.get("/api/roadmap").json()["stale"] is False
    _, reply, state = chat(anon, "looks good, approve it")
    assert "approved" in reply and state["approval_stale"] is False and b not in state["approved_ids"]
    assert anon.get("/api/roadmap").json()["stale"] is True  # built from the earlier approval
    assert generate(anon)[1]["stale"] is False


def test_chat_needs_a_current_list(anon, fake_gaps, searcher, llm):  # noqa: F811
    confirmed_user(anon, "cg13")
    assert anon.post("/api/resources/chat", json={"message": "hi"}).status_code == 409  # no list yet
    ready_user(anon, "cg13", fake_gaps, searcher, web=[found("a")])
    assert anon.post("/api/resources/chat", json={"message": "  "}).status_code == 400

    # New gaps make the list stale: no chat or approval until it is rebuilt, and the rebuild starts a new chat.
    llm({"question": "Sure, what would you like to change?"})
    chat(anon, "hello")
    fake_gaps(analysis(gaps=((QUANTUM, 10),)))
    anon.post("/api/gaps/analyze", json={})
    anon.post("/api/gaps/confirm")
    assert anon.post("/api/resources/chat", json={"message": "remove Web a"}).status_code == 409
    assert anon.post("/api/resources/approve").status_code == 409
    state = anon.post("/api/resources/search").json()
    assert not state["stale"] and state["messages"] == []


def test_a_list_without_a_paused_graph_must_be_rebuilt(anon, fake_gaps, searcher):  # noqa: F811
    ready_user(anon, "cg14", fake_gaps, searcher)
    agent.reset_for_user("cg14")  # e.g. a list saved before the chat existed, or a deleted checkpoint file
    assert anon.get("/api/resources").json()["stale"] is True
    assert anon.post("/api/resources/chat", json={"message": "hi"}).status_code == 409
    assert anon.post("/api/resources/search").json()["stale"] is False


def test_first_pass_results_are_cached_across_users_for_14_days(anon, fake_gaps, searcher, caplog):  # noqa: F811
    caplog.set_level("INFO", logger="core")
    ready_user(anon, "cg18", fake_gaps, searcher, web=[found("a")])
    assert [s for s, _ in searcher.calls] == [QUANTUM]

    # Another user with the same gap and level: the cached result is used, nothing is searched.
    with TestClient(app, base_url="https://testserver") as other:
        theirs = ready_user(other, "cg19", fake_gaps, searcher, web=[found("other")])
    assert len(searcher.calls) == 1 and "1 from cache (Quantum widgets)" in caplog.text
    assert [r["resource"]["title"] for r in quantum(theirs)["resources"]] == ["Web a"]

    # Older than CACHE_DAYS: searched again, and the cache is refreshed.
    with dbmod.SessionLocal() as db:
        db.query(WebSearchCache).update({"created_at": datetime.now(timezone.utc) - timedelta(days=15)})
        db.commit()
    state = anon.post("/api/resources/search").json()
    assert len(searcher.calls) == 2 and [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web other"]


def test_first_pass_searches_at_most_four_gaps_by_priority(anon, fake_gaps, searcher):  # noqa: F811
    confirmed_user(anon, "cg20")
    data = analysis(gaps=[(f"Quantum widgets {n}", 5) for n in "abcdef"])
    for g, priority in zip(data["gaps"], ["low", "medium", "high", "low", "high", "medium"]):
        g["priority"] = priority
    fake_gaps(data)
    anon.post("/api/gaps/analyze", json={})
    anon.post("/api/gaps/confirm")
    assert anon.post("/api/resources/search").status_code == 200
    assert [s for s, _ in searcher.calls] == [f"Quantum widgets {n}" for n in "cebf"]  # high, high, medium, medium


def test_approved_web_resources_become_knowledge_base_candidates(anon, fake_gaps, searcher, llm):  # noqa: F811
    a, b = web_id("https://example.com/a"), web_id("https://example.com/b")
    ready_user(anon, "cg21", fake_gaps, searcher, web=[found("a"), found("b")])
    anon.post("/api/resources/approve")
    anon.post("/api/resources/approve")  # approving the same list again counts nothing new
    with TestClient(app, base_url="https://testserver") as other:
        ready_user(other, "cg22", fake_gaps, searcher)  # served from the cache
        llm({"remove_ids": [b]})
        chat(other, "remove Web b")
        other.post("/api/resources/approve")
    with dbmod.SessionLocal() as db:
        rows = {r.resource_id: r for r in db.query(WebResourceCandidate).all()}
    assert rows[a].approvals == 2 and rows[b].approvals == 1
    assert rows[a].gaps == [QUANTUM] and rows[a].resource["url"] == "https://example.com/a"
    assert all(r.startswith("web-") for r in rows)  # curated resources are not candidates


def test_users_have_separate_lists_and_chats(anon, fake_gaps, searcher, llm):  # noqa: F811
    ready_user(anon, "cg15", fake_gaps, searcher, web=[found("a")])
    with TestClient(app, base_url="https://testserver") as other:
        theirs = ready_user(other, "cg16", fake_gaps, searcher, web=[found("a")])
        llm({"remove_ids": [web_id("https://example.com/a")]})
        _, _, mine = chat(anon, "remove Web a")
        assert quantum(mine)["resources"] == [] and len(mine["messages"]) == 2
        assert other.get("/api/resources").json() == theirs  # untouched: list and (empty) chat
