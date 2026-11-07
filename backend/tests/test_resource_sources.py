"""Milestone 9: the YouTube source, preference- and budget-aware ranking, the filter chips and
Save / Start / Complete. No network: YouTube is the conftest fake, or the real client over httpx.MockTransport."""
import httpx
import pytest

from core.agents.course_search import graph, youtube
from core.agents.course_search.ranking import NEUTRAL, NO_PREFERENCE_MATCH, preference_fit, quality_fit, rank
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.schemas import Candidate, Quality, Resource, SearchProfile
from core.models import ResourceProgress
from core import db as dbmod
from tests.conftest import login
from tests.test_course_graph import CURATED, QUANTUM, chat, found, llm, quantum  # noqa: F401  (fixture)
from tests.test_gap_analysis import PROFILE, analysis, gap
from tests.test_resources import fake_gaps, ids_of  # noqa: F401  (fixture)


def res(id="r", format="course", cost="free", quality=None):
    return Resource(id=id, title=id, provider="p", url=f"https://example.com/{id}", format=format, level="beginner",
                    cost=cost, hours=5, skills=["machine-learning"], description="d", quality=quality)


def video(name, views=500_000, likes=20_000, trusted=False, **overrides):
    """A YouTube candidate as the source would return it (for QUANTUM, which has no vocabulary tags)."""
    fields = dict(id=f"yt-{name}", title=f"Video {name}", provider="Some channel", url=f"https://www.youtube.com/watch?v={name}",
                  format="video", level="beginner", cost="free", hours=4, skills=[QUANTUM], description="A video course.",
                  quality=Quality(views=views, likes=likes, trusted=trusted))
    return Candidate(resource=Resource(**{**fields, **overrides}), match_score=0.85, matched_on=[QUANTUM], source="youtube")


def user(client, sub, fake_gaps, searcher, web=(), videos=(), **profile):  # noqa: F811
    """Signed in with the given profile extras (learning_preferences, constraints), confirmed gaps and a list.
    `videos` is what YouTube finds for QUANTUM (or an exception it raises)."""
    login(client, sub)
    assert client.put("/api/profile", json={**PROFILE, **profile}).status_code == 200
    assert client.post("/api/profile/confirm").status_code == 200
    fake_gaps(analysis(gaps=((CURATED, 40), (QUANTUM, 10))))
    assert client.post("/api/gaps/analyze", json={}).status_code == 200
    assert client.post("/api/gaps/confirm").status_code == 200
    searcher.results[QUANTUM] = list(web)
    searcher.youtube.results[QUANTUM] = videos if isinstance(videos, Exception) else list(videos)
    r = client.post("/api/resources/search")
    assert r.status_code == 200, r.text
    return r.json()


def listed(state):
    return [r for g in state["resources"]["gaps"] for r in g["resources"]]


# --- ranking: preferences and quality ------------------------------------------------


def test_preference_fit_maps_intake_answers_to_formats():
    assert preference_fit(res(format="video"), ["video"]) == 1.0
    assert preference_fit(res(format="paper"), ["articles"]) == 1.0  # papers and tutorials count as articles
    assert preference_fit(res(format="repository"), ["projects"]) == 1.0
    assert preference_fit(res(format="course", cost="paid"), ["free_courses"]) == NO_PREFERENCE_MATCH
    assert preference_fit(res(format="course", cost="paid"), ["paid_courses"]) == 1.0
    assert preference_fit(res(format="book"), []) == NEUTRAL  # not asked
    assert preference_fit(res(format="book"), ["certifications"]) == NEUTRAL  # nothing reports certificates


def test_quality_comes_only_from_the_source():
    assert quality_fit(res(), "knowledge_base") == 0.8 and quality_fit(res(), "web") == 0.5
    assert quality_fit(res(quality=Quality(views=1_000_000, likes=30_000)), "youtube") == 1.0
    assert quality_fit(res(quality=Quality(views=10_000)), "youtube") == pytest.approx(0.667, abs=1e-3)
    assert quality_fit(res(quality=Quality(views=100, likes=0)), "youtube") < 0.2
    assert quality_fit(res(quality=Quality(views=100, likes=0, trusted=True)), "youtube") == 0.9


def test_a_preferred_format_outranks_an_otherwise_equal_one():
    g = Gap(**gap("ML basics", 20))
    cands = [Candidate(resource=res("course"), match_score=0.9), Candidate(resource=res("vid", format="video"), match_score=0.9)]
    prefers_video = SearchProfile(ai_level="None", domain="FinTech", hours_per_week=5, preferences=["video"])
    assert [r.resource.id for r in rank(cands, g, prefers_video)] == ["vid", "course"]
    prefers_books = prefers_video.model_copy(update={"preferences": ["books"]})
    assert [r.resource.id for r in rank(cands, g, prefers_books)] == ["course", "vid"]  # neither matches: id order


# --- the YouTube source (pure parts and the API client) ------------------------------


def test_duration_and_level_parsing():
    assert youtube.parse_duration("PT1H2M3S") == 3723
    assert youtube.parse_duration("PT45M") == 2700 and youtube.parse_duration("P1DT1H") == 25 * 3600
    assert youtube.parse_duration("P0D") == 0 and youtube.parse_duration("garbage") == 0
    assert youtube.infer_level("PyTorch for Beginners - full course") == "beginner"
    assert youtube.infer_level("Advanced RAG techniques") == "advanced"
    assert youtube.infer_level("Building LLM apps") == "intermediate"


def item(id, title="Deep learning full course", seconds=3 * 3600, views=200_000, channel_id="UCother", **kw):
    return youtube.Item(kind=kw.pop("kind", "video"), id=id, title=title, channel_id=channel_id, channel="Chan",
                        description=kw.pop("description", "Neural networks and deep learning."), seconds=seconds,
                        views=views, likes=kw.pop("likes", 5_000))


def test_vetting_keeps_long_relevant_popular_or_trusted_videos():
    g, profile = Gap(**gap("Deep learning", 40)), SearchProfile(ai_level="Beginner", domain="FinTech", hours_per_week=8)
    trusted = next(iter(youtube.trusted_channels()))
    kept = youtube.to_candidates([
        item("good", seconds=int(2.5 * 3600)),
        item("short", seconds=10 * 60),  # not a course
        item("unknown", views=500),  # unpopular, untrusted channel
        item("trusted", views=500, channel_id=trusted),  # unpopular but trusted
        item("offtopic", title="Cooking pasta at home", description="Recipes."),
        item("list", kind="playlist", seconds=12 * 3600),
    ], g, profile)
    by_id = {c.resource.id: c for c in kept}
    assert set(by_id) == {"yt-good", "yt-trusted", "yt-list"}
    good = by_id["yt-good"]
    assert good.source == "youtube" and good.resource.format == "video" and good.resource.cost == "free"
    assert good.resource.hours == 3 and str(good.resource.url) == "https://www.youtube.com/watch?v=good"
    assert str(by_id["yt-list"].resource.url) == "https://www.youtube.com/playlist?list=list"
    assert good.resource.quality == Quality(views=200_000, likes=5_000, trusted=False)
    assert by_id["yt-trusted"].resource.quality.trusted is True
    assert all(c.match_score <= youtube.MAX_RELEVANCE for c in kept)


def api_transport(calls, status=200):
    """Answers the four YouTube endpoints the client uses: two videos and one playlist of two videos."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "Daily limit reached.", "errors": [{"reason": "quotaExceeded"}]}})
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint == "search":
            return httpx.Response(200, json={"items": [
                {"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}},
                {"id": {"playlistId": "p1"}, "snippet": {"title": "Deep learning playlist", "channelId": "UCx",
                                                        "channelTitle": "Chan", "description": "Deep learning."}},
            ]})
        if endpoint == "playlistItems":
            return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": "p1a"}}, {"contentDetails": {"videoId": "p1b"}}]})
        ids = request.url.params["id"].split(",")
        return httpx.Response(200, json={"items": [
            {"id": i, "snippet": {"title": f"Deep learning &amp; {i}", "channelId": "UCx", "channelTitle": "Chan",
                                  "description": "Deep learning course."},
             "contentDetails": {"duration": "PT2H"}, "statistics": {"viewCount": "90000", "likeCount": "3000"}}
            for i in ids
        ]})

    return httpx.MockTransport(handler)


def test_api_client_builds_candidates_and_counts_quota():
    calls = []
    api = youtube.YouTubeDataAPI("secret-key", httpx.Client(transport=api_transport(calls)))
    profile = SearchProfile(ai_level="Beginner", domain="FinTech", hours_per_week=8)
    found = api.search(Gap(**gap("Deep learning", 40)), profile)
    assert {c.resource.id for c in found} == {"yt-v1", "yt-v2", "yt-p1"}
    assert next(c for c in found if c.resource.id == "yt-p1").resource.hours == 4  # two 2-hour videos
    assert next(c for c in found if c.resource.id == "yt-v1").resource.title == "Deep learning & v1"
    assert api.units == 100 + 1 + 1 + 1  # search, videos, playlistItems, the playlist's videos
    assert calls[0].url.params["q"] == "Deep learning full course"


def test_api_errors_never_reveal_the_key():
    api = youtube.YouTubeDataAPI("secret-key", httpx.Client(transport=api_transport([], status=403)))
    with pytest.raises(youtube.YouTubeError) as e:
        api.search(Gap(**gap("Deep learning", 40)), SearchProfile(ai_level="None", domain="FinTech", hours_per_week=5))
    assert str(e.value) == "The YouTube API returned 403 (quotaExceeded: Daily limit reached.)."
    assert "secret-key" not in str(e.value)


# --- YouTube in the graph -------------------------------------------------------------


def test_youtube_results_join_the_list_and_are_cached(anon, fake_gaps, searcher, caplog):  # noqa: F811
    caplog.set_level("INFO", logger="core")
    state = user(anon, "ys1", fake_gaps, searcher, videos=[video("a"), video("b", views=900)])
    assert sorted(searcher.youtube.calls) == [CURATED, QUANTUM]  # every gap, since no preference excludes video
    items = quantum(state)["resources"]
    assert {r["resource"]["id"] for r in items} == {"yt-a", "yt-b"} and all(r["source"] == "youtube" for r in items)
    assert items[0]["resource"]["id"] == "yt-a"  # same relevance; more views and likes rank higher
    assert "YouTube search run: 2 of 2 gaps searched, 0 from cache" in caplog.text and state["notice"] is None

    anon.post("/api/resources/search")  # rebuilding uses the cache
    assert len(searcher.youtube.calls) == 2 and "0 of 2 gaps searched, 2 from cache" in caplog.text


def test_no_youtube_search_when_the_user_does_not_want_video(anon, fake_gaps, searcher):  # noqa: F811
    state = user(anon, "ys2", fake_gaps, searcher, videos=[video("a")], learning_preferences=["books", "articles"])
    assert searcher.youtube.calls == [] and state["notice"] is None


def test_a_youtube_failure_or_missing_key_keeps_the_list(anon, fake_gaps, searcher, monkeypatch):  # noqa: F811
    state = user(anon, "ys3", fake_gaps, searcher, web=[found("a")],
                 videos=youtube.YouTubeError("The YouTube API returned 403 (quotaExceeded)."))
    assert state["notice"].startswith(graph.YOUTUBE_UNAVAILABLE) and "quotaExceeded" in state["notice"]
    assert [r["resource"]["title"] for r in quantum(state)["resources"]] == ["Web a"]

    monkeypatch.setattr(youtube, "get_youtube", lambda: None)
    state = anon.post("/api/resources/search").json()
    assert state["notice"] == graph.YOUTUBE_OFF and listed(state)


# --- budget and filters ---------------------------------------------------------------


def test_a_free_only_budget_never_lists_paid_resources(anon, fake_gaps, searcher, llm):  # noqa: F811
    state = user(anon, "ys4", fake_gaps, searcher, web=[found("paid", cost="paid"), found("free")],
                 constraints={"budget": "free_only"})
    assert state["free_only"] is True
    assert listed(state) and all(r["resource"]["cost"] == "free" for r in listed(state))
    llm({"cost": "paid"})  # even asked for in the chat, the budget wins
    _, _, state = chat(anon, "show me paid ones")
    assert all(r["resource"]["cost"] == "free" for r in listed(state))


def test_filter_chips_change_the_list_without_a_model_call_or_search(anon, fake_gaps, searcher, llm):  # noqa: F811
    assert anon.post("/api/resources/filter", json={}).status_code == 401
    before = user(anon, "ys5", fake_gaps, searcher, web=[found("course"), found("adv", level="advanced")],
                  videos=[video("v")])
    client = llm()  # nothing scripted: any model call would fail
    searched = (len(searcher.calls), len(searcher.youtube.calls))

    state = anon.post("/api/resources/filter", json={"cost": "any", "levels": [], "types": ["video"]}).json()
    assert state["preferences"]["types"] == ["video"]
    assert [r["resource"]["id"] for r in quantum(state)["resources"]] == ["yt-v"]
    curated = next(g for g in state["resources"]["gaps"] if g["gap"]["skill"] == CURATED)
    assert curated["resources"] == [] and curated["note"] == graph.FILTERED
    assert client.requests == [] and state["messages"] == []
    assert (len(searcher.calls), len(searcher.youtube.calls)) == searched

    # Approve covers exactly what is shown.
    approved = anon.post("/api/resources/approve").json()
    assert approved["approved_ids"] == ids_of(state) == ["yt-v"]

    state = anon.post("/api/resources/filter", json={"cost": "any", "levels": ["beginner"], "types": []}).json()
    assert all(r["resource"]["level"] == "beginner" for r in listed(state))
    assert "Web adv" not in [r["resource"]["title"] for r in listed(state)]
    assert state["approval_stale"] is True

    state = anon.post("/api/resources/filter", json={"cost": "any", "levels": [], "types": []}).json()
    assert ids_of(state) == ids_of(before)  # clearing the filters brings the original list back
    assert anon.post("/api/resources/filter", json={"types": ["podcast"]}).status_code == 422


def test_the_chat_can_set_level_and_type_filters(anon, fake_gaps, searcher, llm):  # noqa: F811
    user(anon, "ys6", fake_gaps, searcher, web=[found("course"), found("adv", level="advanced")], videos=[video("v")])
    llm({"types": ["course"], "levels": ["beginner"]})
    _, _, state = chat(anon, "only beginner courses please")
    assert listed(state) and all(r["resource"]["format"] == "course" and r["resource"]["level"] == "beginner"
                                 for r in listed(state))
    assert state["preferences"]["types"] == ["course"] and state["preferences"]["levels"] == ["beginner"]


def test_filter_needs_a_current_list(anon, fake_gaps):  # noqa: F811
    login(anon, "ys7")
    assert anon.post("/api/resources/filter", json={}).status_code == 409


# --- Save / Start / Complete ------------------------------------------------------------


def test_save_start_complete_are_recorded_and_survive_a_rebuild(anon, fake_gaps, searcher):  # noqa: F811
    assert anon.put("/api/resources/progress", json={"resource_id": "x", "saved": True}).status_code == 401
    state = user(anon, "ys8", fake_gaps, searcher, web=[found("a")])
    rid = quantum(state)["resources"][0]["resource"]["id"]
    put = lambda **body: anon.put("/api/resources/progress", json={"resource_id": rid, **body})  # noqa: E731

    state = put(saved=True).json()
    assert [(p["resource"]["id"], p["saved"], p["status"]) for p in state["progress"]] == [(rid, True, "not_started")]
    state = put(status="started").json()
    assert state["progress"][0]["started_at"] and state["progress"][0]["completed_at"] is None
    state = put(status="completed").json()
    p = state["progress"][0]
    assert p["status"] == "completed" and p["saved"] is True and p["started_at"] and p["completed_at"]

    # A rebuilt list without the resource still shows its progress (the resource is kept with it).
    searcher.results[QUANTUM] = []
    with dbmod.SessionLocal() as db:
        db.query(dbmod.Base.metadata.tables["web_search_cache"]).delete()
        db.commit()
    state = anon.post("/api/resources/search").json()
    assert rid not in ids_of(state) and state["progress"][0]["resource"]["id"] == rid
    assert put(status="not_started").status_code == 200  # still allowed: it is in the user's progress

    # Clearing everything removes the row.
    state = put(saved=False).json()
    assert state["progress"] == []
    with dbmod.SessionLocal() as db:
        assert db.query(ResourceProgress).filter_by(user_id="ys8").count() == 0

    r = anon.put("/api/resources/progress", json={"resource_id": "not-mine", "saved": True})
    assert r.status_code == 422
    assert anon.put("/api/resources/progress", json={"resource_id": rid, "status": "done"}).status_code == 422


def test_progress_is_per_user(anon, fake_gaps, searcher):  # noqa: F811
    state = user(anon, "ys9", fake_gaps, searcher, web=[found("a")])
    rid = ids_of(state)[0]
    anon.put("/api/resources/progress", json={"resource_id": rid, "saved": True})
    anon.post("/api/auth/logout")
    login(anon, "ys10")
    assert anon.get("/api/resources").json()["progress"] == []
    assert anon.put("/api/resources/progress", json={"resource_id": rid, "saved": True}).status_code == 422
