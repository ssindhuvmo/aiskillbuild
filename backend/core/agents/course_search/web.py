"""Live web search for one skill gap. Like the Retriever, everything downstream depends only on
the WebSearcher protocol and the Candidate it returns; get_searcher() is the one swap point.

Links are never invented: the model records its findings with the `record_resources` tool, and a
finding is kept only if its URL appears in the search results of the same reply.
"""
import hashlib
import logging
import threading
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from core.agents.course_search.ranking import EXPERIENCE_LEVEL
from core.agents.course_search.schemas import WebFinding
from core.agents.course_search.search import url_key
from core.agents.gap_analysis.schemas import Gap
from core.knowledge.retriever import extract_tags, gap_tags
from core.knowledge.schemas import Candidate, Resource, SearchProfile
from core.knowledge.store import load_knowledge_base
from core.llm import MODEL, get_client

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_RESULTS = 5  # findings kept per search
MAX_SEARCHES = 1  # web searches the model may run per gap (each is billed)
MAX_CONTINUATIONS = 3  # re-sends after stop_reason "pause_turn"
MAX_RELEVANCE = 0.9  # cap, so a curated resource wins a tie with a web result
CACHE_DAYS = 14  # first-pass results are reused (across users) for this long before searching again

# The basic web search tool: its results come back as web_search_tool_result blocks, which is
# what the URL check below reads.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}
RECORD_TOOL = {
    "name": "record_resources",
    "description": "Record the learning resources you found. Call this once, after searching.",
    "input_schema": {
        "type": "object",
        "properties": {"resources": {"type": "array", "items": WebFinding.model_json_schema()}},
        "required": ["resources"],
    },
}


class WebSearcher(Protocol):
    def search(self, gap: Gap, profile: SearchProfile, hint: str | None = None) -> list[Candidate]:
        """Return web candidates for the gap. `hint` carries what the user asked for in the chat."""
        ...


def section(name: str) -> str:
    """One "# name" section of prompt.md."""
    return PROMPT.split(f"# {name}\n", 1)[1].split("\n# ", 1)[0].strip()


def web_id(url) -> str:
    return "web-" + hashlib.sha1(url_key(url).encode()).hexdigest()[:10]


def cache_key(gap: Gap, profile: SearchProfile) -> tuple[str, str, str]:
    """(skill, level, domain) under which a first-pass search is cached and shared across users. The
    level is the resource level the user is ready for; the domain counts only for a domain-specific
    gap, because only then do the results depend on it."""
    return (
        " ".join(gap.skill.lower().split()),
        EXPERIENCE_LEVEL.get(profile.ai_level, "beginner"),
        profile.domain if gap.domain_specific else "",
    )


def to_candidates(findings: list, allowed_urls: set[str], gap: Gap, profile: SearchProfile) -> list[Candidate]:
    """Validate what the model recorded and drop anything whose URL was not in the search results.
    A result is tagged from its title and description with the knowledge-base vocabulary, so the
    relevance gate and "why" use the same tags as curated resources."""
    vocabulary = load_knowledge_base().tags
    wanted = gap_tags(gap, vocabulary)
    candidates = []
    for raw in findings:
        try:
            f = WebFinding.model_validate(raw)
        except ValidationError:
            continue
        if url_key(f.url) not in allowed_urls:
            log.warning("Web result dropped, URL not in the search results: %s", f.url)
            continue
        tags = extract_tags(f"{f.title} {f.description}", vocabulary)
        resource = Resource(
            id=web_id(f.url), title=f.title, provider=f.provider, url=f.url, format=f.format, level=f.level,
            cost=f.cost, hours=f.hours, skills=sorted(tags) or [gap.skill],
            domains=[profile.domain] if f.domain_specific else [], description=f.description,
        )
        candidates.append(Candidate(
            resource=resource, match_score=min(f.relevance, MAX_RELEVANCE),
            matched_on=sorted(tags & wanted) if wanted else [gap.skill], source="web",
        ))
    return candidates[:MAX_RESULTS]


def _request(gap: Gap, profile: SearchProfile, hint: str | None) -> str:
    text = (
        f"Skill gap: {gap.skill}\nWhy it is needed: {gap.why_needed}\n"
        f"Estimated effort: about {gap.effort_hours} hours\n"
        f"Learner: AI level {profile.ai_level}; works in {profile.domain}; "
        f"{profile.hours_per_week} hours a week.\n"
        f"Domain-specific gap: {'yes' if gap.domain_specific else 'no'}"
    )
    return f"{text}\n\nExtra instructions: {hint}" if hint else text


class AnthropicWebSearcher:
    """One model call per gap with the Anthropic web search tool. `searches`, `input_tokens` and
    `output_tokens` count what this instance was billed for, for the per-run log line."""

    def __init__(self):
        self.searches = self.input_tokens = self.output_tokens = 0
        self._lock = threading.Lock()  # search() runs in a thread pool

    def search(self, gap: Gap, profile: SearchProfile, hint: str | None = None) -> list[Candidate]:
        client = get_client()
        messages: list[dict] = [{"role": "user", "content": _request(gap, profile, hint)}]
        allowed: set[str] = set()
        for _ in range(MAX_CONTINUATIONS + 1):
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=section("web_search").replace("{limit}", str(MAX_RESULTS)),
                messages=messages,
                tools=[WEB_SEARCH_TOOL, RECORD_TOOL],
            )
            usage = getattr(response, "usage", None)
            used = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0)
            with self._lock:
                self.searches += used or 0
                # Search results are billed as input tokens.
                self.input_tokens += sum(
                    getattr(usage, f, 0) or 0
                    for f in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
                )
                self.output_tokens += getattr(usage, "output_tokens", 0) or 0
            for block in response.content:
                # A failed search has an error object here instead of a list of results.
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    allowed |= {url_key(r.url) for r in block.content}
            recorded = next((b for b in response.content if b.type == "tool_use" and b.name == RECORD_TOOL["name"]), None)
            if recorded is not None:
                findings = recorded.input.get("resources", []) if isinstance(recorded.input, dict) else []
                return to_candidates(findings if isinstance(findings, list) else [], allowed, gap, profile)
            if response.stop_reason != "pause_turn":
                break
            # The server paused a long turn: send it back to continue.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        return []


def get_searcher() -> WebSearcher:
    """The one place that picks the web search implementation (tests replace it)."""
    return AnthropicWebSearcher()
