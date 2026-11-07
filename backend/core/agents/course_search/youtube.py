"""YouTube as a resource source (YouTube Data API v3): full courses and playlists for one skill gap.

Like the WebSearcher, everything downstream depends only on the YouTubeSource protocol and the Candidate
it returns; get_youtube() is the one swap point (None when YOUTUBE_API_KEY is not set).

Two stages, all plain Python (no LLM): the API finds candidates (one search per gap), then to_candidates
vets them: long enough to be a course (MIN_MINUTES), relevant to the gap by the knowledge-base tag
vocabulary, and either from a trusted channel (data/youtube_channels.json) or with at least MIN_VIEWS.
Durations, views and likes come from the API, so every number is the source's own. Links are built from
the API's video and playlist ids, so they are real.

Quota: a search costs 100 units, the detail calls 1 unit each (the free daily quota is 10,000 units).
"""
import html
import json
import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from core.agents.course_search.ranking import EXPERIENCE_LEVEL
from core.agents.gap_analysis.schemas import Gap
from core.config import BACKEND_DIR, YOUTUBE_API_KEY
from core.knowledge.retriever import BROAD_WEIGHT, extract_tags, gap_tags, normalize
from core.knowledge.schemas import Candidate, Level, Quality, Resource, SearchProfile
from core.knowledge.store import load_knowledge_base

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
CHANNELS_PATH = BACKEND_DIR / "data" / "youtube_channels.json"
SEARCH_RESULTS = 15  # candidates asked for per search (one search per gap)
MAX_RESULTS = 5  # kept per gap after vetting
MAX_PLAYLISTS = 5  # playlists whose length is looked up (2 units each)
MIN_MINUTES = 30  # shorter videos are not courses
MIN_VIEWS = 20_000  # vetting for channels that are not on the trusted list
MAX_HOURS = 300  # Resource.hours limit
MAX_RELEVANCE = 0.9  # cap, so a curated resource wins a tie (as for web results)
TITLE_MATCH = 0.75  # relevance when the gap has no vocabulary tags but its name is in the title
DESCRIPTION_CHARS = 300  # of the description used for tagging (the rest is often link lists)
TIMEOUT = 15  # seconds per API call
CACHE_DAYS = 14  # results are reused (across users) for this long, in web_search_cache

ADVANCED = re.compile(r"\b(advanced|expert|deep dive|masterclass)\b", re.IGNORECASE)
BEGINNER = re.compile(r"\b(beginners?|intro|introduction|introductory|basics|crash course|fundamentals|for everyone)\b",
                      re.IGNORECASE)
DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


class YouTubeError(Exception):
    """A failed API call. The message never contains the API key."""


class YouTubeSource(Protocol):
    def search(self, gap: Gap, profile: SearchProfile) -> list[Candidate]:
        ...


@dataclass
class Item:
    """One video or playlist as the API describes it."""

    kind: str  # "video" | "playlist"
    id: str
    title: str
    channel_id: str
    channel: str
    description: str
    seconds: int
    views: int | None = None
    likes: int | None = None


@lru_cache
def trusted_channels() -> dict[str, str]:
    """Channel id -> name, from data/youtube_channels.json (edit there, not in code)."""
    with open(CHANNELS_PATH, encoding="utf-8") as f:
        return {c["id"]: c["name"] for c in json.load(f)["channels"]}


def parse_duration(value: str) -> int:
    """ISO 8601 duration from the API ("PT1H2M3S", "P1DT2H") in seconds; 0 if unreadable (e.g. a live stream)."""
    m = DURATION.match(value or "")
    if not m:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def infer_level(text: str) -> Level:
    if ADVANCED.search(text):
        return "advanced"
    return "beginner" if BEGINNER.search(text) else "intermediate"


def query(gap: Gap, profile: SearchProfile) -> str:
    text = f"{gap.skill} full course"
    return f"{text} {profile.domain}" if gap.domain_specific else text


def cache_key(gap: Gap, profile: SearchProfile) -> tuple[str, str, str]:
    """Shared across users in web_search_cache, next to the web results (hence the prefix). The search does
    not depend on the user's level, but the key keeps the same shape as web.cache_key."""
    return (
        "youtube: " + " ".join(gap.skill.lower().split()),
        EXPERIENCE_LEVEL.get(profile.ai_level, "beginner"),
        profile.domain if gap.domain_specific else "",
    )


def url(item: Item) -> str:
    if item.kind == "playlist":
        return f"https://www.youtube.com/playlist?list={item.id}"
    return f"https://www.youtube.com/watch?v={item.id}"


def _relevance(item: Item, gap: Gap) -> tuple[float, list[str]] | None:
    """Tag overlap with the gap, weighted like TagRetriever; None when the item is not about the gap."""
    kb = load_knowledge_base()
    wanted = gap_tags(gap, kb.tags)
    if not wanted:
        if normalize(gap.skill) in normalize(item.title):
            return TITLE_MATCH, [gap.skill]
        return None
    found = extract_tags(f"{item.title} {item.description[:DESCRIPTION_CHARS]}", kb.tags)
    overlap = wanted & found
    if not overlap:
        return None
    weight = lambda t: BROAD_WEIGHT if t in kb.broad_tags else 1.0  # noqa: E731
    share = sum(weight(t) for t in overlap) / max(sum(weight(t) for t in wanted), 1.0)
    return round(min(share, MAX_RELEVANCE), 3), sorted(overlap)


def to_candidates(items: list[Item], gap: Gap, profile: SearchProfile) -> list[Candidate]:
    """Vet and convert what the API returned (pure: no I/O besides the cached knowledge base)."""
    trusted = trusted_channels()
    kept = []
    for item in items:
        is_trusted = item.channel_id in trusted
        hours = math.ceil(item.seconds / 3600)
        if item.seconds < MIN_MINUTES * 60 or hours > MAX_HOURS:
            continue
        if not is_trusted and (item.views or 0) < MIN_VIEWS:
            continue
        match = _relevance(item, gap)
        if match is None:
            continue
        score, matched_on = match
        description = " ".join(item.description.split())[:400] or item.title[:400]
        resource = Resource(
            id=f"yt-{item.id}"[:80], title=item.title[:200], provider=(item.channel or "YouTube")[:120], url=url(item),
            format="video", level=infer_level(f"{item.title} {item.description[:DESCRIPTION_CHARS]}"), cost="free",
            hours=hours, skills=sorted(set(matched_on) - {gap.skill}) or [gap.skill], description=description,
            quality=Quality(views=item.views, likes=item.likes, trusted=is_trusted),
        )
        kept.append(Candidate(resource=resource, match_score=score, matched_on=matched_on, source="youtube"))
    kept.sort(key=lambda c: (-c.match_score, -(c.resource.quality.views or 0), c.resource.id))
    return kept[:MAX_RESULTS]


def _count(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeDataAPI:
    """The real source. `units` counts the quota this instance used, for the per-run log line."""

    def __init__(self, key: str, client: httpx.Client | None = None):
        self._key = key
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self.units = 0

    def _get(self, endpoint: str, cost: int, **params) -> dict:
        self.units += cost
        try:
            response = self._client.get(f"{API}/{endpoint}", params={**params, "key": self._key})
        except httpx.HTTPError as e:  # the exception text can contain the URL, and so the key
            raise YouTubeError(f"Could not reach the YouTube API ({type(e).__name__}).") from None
        if response.status_code != 200:
            try:
                error = response.json()["error"]
                reason = error["errors"][0]["reason"]
                message = str(error.get("message", ""))[:200].replace(self._key, "[key]")
            except Exception:
                reason, message = "unknown", ""
            detail = f"{reason}: {message}" if message else reason
            raise YouTubeError(f"The YouTube API returned {response.status_code} ({detail}).")
        return response.json()

    def _videos(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        # maxResults is not supported together with id; at most 50 ids per call (search returns 15, playlists 50).
        data = self._get("videos", 1, part="snippet,contentDetails,statistics", id=",".join(ids[:50]))
        return {v["id"]: v for v in data.get("items", [])}

    def _playlist(self, playlist_id: str) -> tuple[int, int | None, int | None]:
        """(total seconds, views, likes of the first video) for a playlist's first 50 videos."""
        data = self._get("playlistItems", 1, part="contentDetails", playlistId=playlist_id, maxResults=50)
        ids = [i["contentDetails"]["videoId"] for i in data.get("items", []) if i.get("contentDetails", {}).get("videoId")]
        videos = self._videos(ids)
        seconds = sum(parse_duration(v.get("contentDetails", {}).get("duration", "")) for v in videos.values())
        first = videos.get(ids[0], {}).get("statistics", {}) if ids else {}
        return seconds, _count(first.get("viewCount")), _count(first.get("likeCount"))

    def search(self, gap: Gap, profile: SearchProfile) -> list[Candidate]:
        found = self._get(
            "search", 100, part="snippet", q=query(gap, profile), type="video,playlist", maxResults=SEARCH_RESULTS,
            relevanceLanguage="en", safeSearch="strict",
        )
        video_ids, playlists = [], []
        for result in found.get("items", []):
            rid = result.get("id", {})
            if rid.get("videoId"):
                video_ids.append(rid["videoId"])
            elif rid.get("playlistId") and len(playlists) < MAX_PLAYLISTS:
                playlists.append((rid["playlistId"], result.get("snippet", {})))

        items = []
        for vid, v in self._videos(video_ids).items():
            snippet, stats = v.get("snippet", {}), v.get("statistics", {})
            items.append(Item(
                kind="video", id=vid, title=html.unescape(snippet.get("title", "")),
                channel_id=snippet.get("channelId", ""), channel=html.unescape(snippet.get("channelTitle", "")),
                description=html.unescape(snippet.get("description", "")),
                seconds=parse_duration(v.get("contentDetails", {}).get("duration", "")),
                views=_count(stats.get("viewCount")), likes=_count(stats.get("likeCount")),
            ))
        for pid, snippet in playlists:
            seconds, views, likes = self._playlist(pid)
            items.append(Item(
                kind="playlist", id=pid, title=html.unescape(snippet.get("title", "")),
                channel_id=snippet.get("channelId", ""), channel=html.unescape(snippet.get("channelTitle", "")),
                description=html.unescape(snippet.get("description", "")), seconds=seconds, views=views, likes=likes,
            ))
        return to_candidates([i for i in items if i.title], gap, profile)


def get_youtube() -> YouTubeSource | None:
    """The one place that picks the YouTube implementation (tests replace it). None without an API key."""
    return YouTubeDataAPI(YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None
