"""Where job postings come from. Everything downstream depends only on the JobSource protocol and the
JobFindings it returns; get_job_source() is the one swap point (a jobs API can be added later without
changing the page).

The first source is live web search limited to the JOB_SITES allowlist. Links are never invented: the model
records its findings with the `record_jobs` tool, and a finding is kept only if its URL is in the search
results of the same reply and on an allowed site. No logged-in browsing and no scraping: the app keeps the
search tool's results and links to the postings.
"""
import logging
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError

from core.agents.course_search.search import url_key
from core.agents.job_search.schemas import JobFinding, JobQuery
from core.config import JOB_SITES
from core.llm import MODEL, get_client

log = logging.getLogger(__name__)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
MAX_JOBS = 10  # postings kept per search
MAX_SEARCHES = 3  # web searches the model may run per job search (each is billed)
MAX_CONTINUATIONS = 3  # re-sends after stop_reason "pause_turn"

RECORD_TOOL = {
    "name": "record_jobs",
    "description": "Record the job postings you found. Call this once, after searching.",
    "input_schema": {
        "type": "object",
        "properties": {"jobs": {"type": "array", "items": JobFinding.model_json_schema()}},
        "required": ["jobs"],
    },
}


class Seeker:
    """What the search is about: the user's roles and background (no personal data)."""

    def __init__(self, current_role: str, target_role: str, years_experience: int | None, domain: str,
                 skills: list[str]):
        self.current_role, self.target_role = current_role, target_role
        self.years_experience, self.domain, self.skills = years_experience, domain, skills


class JobSource(Protocol):
    def search(self, query: JobQuery, seeker: Seeker) -> list[JobFinding]:
        ...


def section(name: str) -> str:
    """One "# name" section of prompt.md."""
    return PROMPT.split(f"# {name}\n", 1)[1].split("\n# ", 1)[0].strip()


def on_allowed_site(url: str, sites: list[str]) -> bool:
    """The URL's host is an allowed site or a subdomain of one (a site may carry a path, e.g. wellfound.com/jobs)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    for site in sites:
        domain, _, path = site.lower().partition("/")
        if host == domain or host.endswith("." + domain):
            if not path or parts.path.lower().lstrip("/").startswith(path):
                return True
    return False


def to_findings(raw: list, allowed_urls: set[str], sites: list[str]) -> list[JobFinding]:
    """Validate what the model recorded; drop anything whose URL was not in the search results or is not on an
    allowed site, and repeated postings."""
    found, seen = [], set()
    for item in raw:
        try:
            f = JobFinding.model_validate(item)
        except ValidationError:
            continue
        key = url_key(f.url)
        if key not in allowed_urls:
            log.warning("Job dropped, URL not in the search results: %s", f.url)
            continue
        if not on_allowed_site(f.url, sites):
            log.warning("Job dropped, not on an allowed site: %s", f.url)
            continue
        if key in seen:
            continue
        seen.add(key)
        found.append(f)
    return found[:MAX_JOBS]


def _request(query: JobQuery, seeker: Seeker) -> str:
    modes = [m for m, on in (("remote", query.remote), ("hybrid", query.hybrid)) if on]
    return (
        f"Target role: {seeker.target_role}\n"
        f"Current role: {seeker.current_role}"
        f"{f', {seeker.years_experience} years of experience' if seeker.years_experience is not None else ''}\n"
        f"Industry: {seeker.domain}\n"
        f"Main skills: {', '.join(seeker.skills[:12]) or 'not known'}\n"
        f"Location: {query.location or 'any'}\n"
        f"Work mode: {' or '.join(modes) if modes else 'any'}"
    )


class AnthropicJobSource:
    """One model call (with up to MAX_SEARCHES searches) using the web search tool limited to JOB_SITES."""

    def __init__(self, sites: list[str] | None = None):
        self.sites = sites or JOB_SITES

    def search(self, query: JobQuery, seeker: Seeker) -> list[JobFinding]:
        client = get_client()
        tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES,
                "allowed_domains": self.sites}
        messages: list[dict] = [{"role": "user", "content": _request(query, seeker)}]
        allowed: set[str] = set()
        for _ in range(MAX_CONTINUATIONS + 1):
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=section("search").replace("{limit}", str(MAX_JOBS)),
                messages=messages,
                tools=[tool, RECORD_TOOL],
            )
            for block in response.content:
                # A failed search has an error object here instead of a list of results.
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    allowed |= {url_key(r.url) for r in block.content}
            recorded = next((b for b in response.content if b.type == "tool_use" and b.name == RECORD_TOOL["name"]), None)
            if recorded is not None:
                raw = recorded.input.get("jobs", []) if isinstance(recorded.input, dict) else []
                return to_findings(raw if isinstance(raw, list) else [], allowed, self.sites)
            if response.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        return []


def get_job_source() -> JobSource:
    """The one place that picks the job source (tests replace it)."""
    return AnthropicJobSource()
