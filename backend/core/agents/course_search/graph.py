"""The course search and refinement graph (LangGraph).

    retrieve_kb -> web_search -> merge_dedupe -> verify_urls -> rank -> present -> await_user (pause)
                       ^                                         ^                      |
                       |                                         |                  interpret
                       +---------- new search needed ---------- apply <-----------------+
                                                                                        +-> approve -> await_user

The first run builds the list and pauses. Each chat message resumes the graph: `interpret` turns
the message into operations (RefinementAction), `apply` updates the state in plain Python, the
list is rebuilt (searching the web again only when needed) and explained, and the graph pauses
again. Approval saves the approved list for the scheduler and pauses too, so the user can keep
refining. State is checkpointed per user (thread_id = user id), so the chat survives sign-out.

State holds plain JSON data (model_dump) so any checkpointer can store it.
"""
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from anthropic import transform_schema
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.config import get_stream_writer
from langgraph.graph import START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from core import repository
from core.agents.course_search import search, verify, web
from core.agents.course_search.ranking import rank
from core.agents.course_search.schemas import Preferences, RankedResource, RefinementAction, ResourceList
from core.agents.gap_analysis.schemas import Gap
from core.config import CHECKPOINT_DB
from core.db import SessionLocal
from core.knowledge.retriever import get_retriever
from core.knowledge.schemas import Candidate, SearchProfile
from core.llm import MODEL, friendly_error, get_client
from core.repository import ValidationFailed

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # interpretation attempts, with the problems fed back
MIN_CURATED = 3  # first pass: a gap with this many good knowledge-base candidates is not web-searched
MAX_SEARCHES_PER_TURN = 4  # gaps searched again for one chat message
SEARCH_WORKERS = 4
PER_GAP_STEP, MAX_PER_GAP = 2, 8  # "add more" shows more resources per gap, up to a limit
FAVOUR_BOOST = 0.15  # added to the score of a format the user asked to favour
RECENT_MESSAGES = 6  # chat history given to the interpreter
ACTION_FORMAT = {"type": "json_schema", "schema": transform_schema(RefinementAction)}

WEB_UNAVAILABLE = "Live web search didn't work for every skill, so parts of this list come from the curated library only. "
SKIPPED = "Skipped: you said you already know this."
NOT_UNDERSTOOD = "I couldn't work out how to apply that. Please try rephrasing it."


class InterpretFailed(Exception):
    pass


class SearchState(TypedDict, total=False):
    gaps: list[dict]  # Gap, in gap-analysis order
    profile: dict  # SearchProfile
    kb: list[list[dict]]  # Candidate per gap, from the knowledge base
    web: list[list[dict]]  # Candidate per gap, from every web search so far
    candidates: list[list[dict]]  # merged, de-duplicated and URL-verified
    checked: dict[str, str]  # url key -> "ok" | "blocked" | "fail"
    ranked: list[list[dict]]  # RankedResource per gap, after the user's preferences
    resource_list: dict  # ResourceList as shown to the user
    search_requests: list[dict] | None  # SearchRequest for the next web search; None = every gap
    removed_ids: list[str]
    skipped_gaps: list[str]  # skill names the user already knows
    preferences: dict  # Preferences
    per_gap: int
    messages: list[dict]  # the refinement chat
    request: dict | None  # what the user sent to resume the graph
    action: dict | None  # RefinementAction being applied
    notice: str | None


def _gaps(state: SearchState) -> list[Gap]:
    return [Gap(**g) for g in state["gaps"]]


def _profile(state: SearchState) -> SearchProfile:
    return SearchProfile(**state["profile"])


def _dump(items) -> list[dict]:
    return [i.model_dump(mode="json") for i in items]


def _listed(resource_list: dict | None) -> dict[str, dict]:
    """Resource id -> {title, skill} for a saved list."""
    if not resource_list:
        return {}
    return {
        r["resource"]["id"]: {"title": r["resource"]["title"], "skill": g["gap"]["skill"]}
        for g in resource_list["gaps"]
        for r in g["resources"]
    }


# --- Pure helpers -------------------------------------------------------------------


def apply_preferences(
    ranked: list[list[RankedResource]], gaps: list[Gap], removed: set[str], skipped: set[str], prefs: Preferences
) -> list[list[RankedResource]]:
    """What the user asked for in the chat, applied on top of the ranking: removed resources and
    skipped gaps are dropped, a cost preference is a filter and favoured formats get a boost."""
    result = []
    for gap, items in zip(gaps, ranked):
        if gap.skill in skipped:
            result.append([])
            continue
        kept = [
            r for r in items
            if r.resource.id not in removed and (prefs.cost == "any" or r.resource.cost == prefs.cost)
        ]
        kept = [
            r.model_copy(update={"score": round(min(r.score + FAVOUR_BOOST, 1.0), 3)}) if r.resource.format in prefs.formats else r
            for r in kept
        ]
        kept.sort(key=lambda r: (-r.score, r.resource.id))
        result.append(kept)
    return result


def good(items: list[RankedResource]) -> int:
    """How many of these pass present()'s thresholds."""
    return sum(r.score >= search.MIN_SCORE and r.breakdown.relevance >= search.MIN_RELEVANCE for r in items)


def check_action(action: RefinementAction, state: SearchState) -> list[str]:
    """Checks the schema cannot express. Returns problems; empty means OK."""
    if action.question:
        return []
    problems = []
    listed, skills = set(_listed(state.get("resource_list"))), {g["skill"] for g in state["gaps"]}
    removed, skipped = set(state.get("removed_ids", [])), set(state.get("skipped_gaps", []))
    for rid in action.remove_ids:
        if rid not in listed:
            problems.append(f'remove_ids: "{rid}" is not an id on the current list.')
    for rid in action.restore_ids:
        if rid not in removed:
            problems.append(f'restore_ids: "{rid}" is not in "Removed earlier".')
    for skill in [*action.known_skills, *(r.skill for r in action.add_more)]:
        if skill not in skills:
            problems.append(f'"{skill}" is not one of the skill gaps; use a skill name exactly as listed.')
    for skill in action.restore_skills:
        if skill not in skipped:
            problems.append(f'restore_skills: "{skill}" is not in "Skipped skills".')
    if len(action.add_more) > MAX_SEARCHES_PER_TURN:
        problems.append(f"add_more: at most {MAX_SEARCHES_PER_TURN} skills per message.")
    changes = action.model_dump(exclude={"approve", "question"}, exclude_defaults=True)
    if action.approve and changes:
        problems.append("approve must not be combined with other operations.")
    if not action.approve and not changes:
        problems.append("Return at least one operation, or a question.")
    return problems


def summary(changes: dict) -> str:
    """Plain explanation of a change, used when the explanation model is unavailable."""
    parts = []
    if changes["added"]:
        parts.append("added " + ", ".join(f'"{a["title"]}"' for a in changes["added"]))
    if changes["removed"]:
        parts.append("removed " + ", ".join(f'"{t}"' for t in changes["removed"]))
    text = f"I updated your list: {'; '.join(parts)}." if parts else "Nothing changed in your list."
    return f"{text} You can keep refining or approve the list."


# --- Nodes --------------------------------------------------------------------------


def retrieve_kb(state: SearchState) -> dict:
    found = search.retrieve(_gaps(state), _profile(state), get_retriever())
    return {"kb": [_dump(cs) for cs in found]}


def _hint(request: dict, prefs: Preferences, titles: list[str]) -> str | None:
    parts = []
    if prefs.cost != "any":
        parts.append(f"{prefs.cost.capitalize()} resources only.")
    formats = [request["format"]] if request.get("format") else prefs.formats
    if formats:
        parts.append(f"Look for these formats: {', '.join(formats)}.")
    if request.get("hint"):
        parts.append(f"The user asked for: {request['hint']}")
    if titles:
        parts.append("Already listed, so find different ones: " + "; ".join(titles[:8]))
    return " ".join(parts) or None


def web_search(state: SearchState) -> dict:
    """Search the web: on the first pass for the gaps the knowledge base covers thinly (fewer than
    MIN_CURATED good candidates), later only for the gaps `apply` asked for. Each search is billed."""
    gaps, profile = _gaps(state), _profile(state)
    index = {g.skill: i for i, g in enumerate(gaps)}
    requests = state.get("search_requests")
    if requests is None:
        requests = [
            {"skill": gap.skill}
            for gap, kb in zip(gaps, state["kb"])
            if good(rank([Candidate(**c) for c in kb], gap, profile)) < MIN_CURATED
        ]
    prefs = Preferences(**state.get("preferences", {}))
    known = state.get("candidates") or [[] for _ in gaps]
    found = [list(cs) for cs in state.get("web") or [[] for _ in gaps]]
    searcher = web.get_searcher()

    def run(request: dict) -> tuple[int, list[Candidate]]:
        i = index[request["skill"]]
        titles = [c["resource"]["title"] for c in known[i]]
        return i, searcher.search(gaps[i], profile, _hint(request, prefs, titles))

    notice = None
    with ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as pool:
        for future in [pool.submit(run, r) for r in requests if r["skill"] in index]:
            try:
                i, candidates = future.result()
            except Exception as exc:  # the list still works without web results
                log.warning("Web search failed: %r", exc)
                notice = WEB_UNAVAILABLE + friendly_error(exc)
                continue
            found[i] += _dump(candidates)
    # The cost of this run: gaps searched, and the billed searches when the searcher counts them.
    log.info(
        "Web search run: %d of %d gaps searched (%s), %s web searches",
        len(requests), len(gaps), ", ".join(r["skill"] for r in requests) or "none", getattr(searcher, "searches", "n/a"),
    )
    return {"web": found, "search_requests": [], "notice": notice}


def merge_dedupe(state: SearchState) -> dict:
    merged = [
        search.merge_dedupe([Candidate(**c) for c in kb + found]) for kb, found in zip(state["kb"], state["web"])
    ]
    return {"candidates": [_dump(cs) for cs in merged]}


def verify_urls(state: SearchState) -> dict:
    """Check every web URL once and drop the ones that fail. Knowledge-base links are checked
    offline (scripts/check_kb_links.py)."""
    checked = dict(state.get("checked", {}))
    urls = {
        search.url_key(c["resource"]["url"]): c["resource"]["url"]
        for cs in state["candidates"]
        for c in cs
        if c["source"] == "web" and search.url_key(c["resource"]["url"]) not in checked
    }
    if urls:
        checker = verify.get_checker()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for key, (status, detail) in zip(urls, pool.map(checker, urls.values())):
                checked[key] = status
                if status == "fail":
                    log.info("Web result dropped, link check failed (%s): %s", detail, urls[key])
    kept = [
        [c for c in cs if c["source"] != "web" or checked[search.url_key(c["resource"]["url"])] != "fail"]
        for cs in state["candidates"]
    ]
    return {"candidates": kept, "checked": checked}


def _ranked(state: SearchState, removed: set[str], skipped: set[str], prefs: Preferences) -> list[list[RankedResource]]:
    gaps, profile = _gaps(state), _profile(state)
    ranked = [rank([Candidate(**c) for c in cs], gap, profile) for cs, gap in zip(state["candidates"], gaps)]
    return apply_preferences(ranked, gaps, removed, skipped, prefs)


def rank_node(state: SearchState) -> dict:
    ranked = _ranked(
        state, set(state.get("removed_ids", [])), set(state.get("skipped_gaps", [])),
        Preferences(**state.get("preferences", {})),
    )
    return {"ranked": [_dump(rs) for rs in ranked]}


def _changes(state: SearchState, result: dict) -> dict:
    """What a refinement turn changed, for the explanation."""
    before, after = _listed(state.get("resource_list")), _listed(result)
    details = {r["resource"]["id"]: r for g in result["gaps"] for r in g["resources"]}
    return {
        "user_request": state["messages"][-1]["content"],
        "added": [
            {**after[i], "format": details[i]["resource"]["format"], "cost": details[i]["resource"]["cost"], "source": details[i]["source"]}
            for i in after
            if i not in before
        ],
        "removed": [before[i]["title"] for i in before if i not in after],
        "preferences": state.get("preferences", {}),
        "skipped_skills": state.get("skipped_gaps", []),
        "skills_without_resources": [g["gap"]["skill"] for g in result["gaps"] if not g["resources"]],
        "resources_on_list": len(after),
        "notice": state.get("notice"),
    }


def _explain(changes: dict) -> str:
    """Stream the explanation of a change to the chat and return it."""
    writer = get_stream_writer()
    parts: list[str] = []
    try:
        with get_client().messages.stream(
            model=MODEL,
            max_tokens=1500,
            system=web.section("explain"),
            messages=[{"role": "user", "content": json.dumps(changes, indent=2)}],
        ) as stream:
            for text in stream.text_stream:
                parts.append(text)
                writer({"type": "token", "text": text})
    except Exception as exc:  # the list is already updated; fall back to a plain summary
        log.warning("Explanation failed: %r", exc)
    reply = "".join(parts).strip()
    if not reply:
        reply = summary(changes)
        writer({"type": "token", "text": reply})
    return reply


def present(state: SearchState, config: RunnableConfig) -> dict:
    """Build the list, save it as the user's resource list and, on a refinement turn, explain
    what changed."""
    gaps = _gaps(state)
    ranked = [[RankedResource(**r) for r in rs] for rs in state["ranked"]]
    result = search.present(gaps, ranked, state.get("per_gap", search.PER_GAP))
    skipped = set(state.get("skipped_gaps", []))
    for g in result.gaps:
        if g.gap.skill in skipped:
            g.note = SKIPPED
    user_id = config["configurable"]["thread_id"]
    with SessionLocal() as db:
        repository.save_resource_list(db, user_id, result, repository.get_gap_state(db, user_id))
    data = result.model_dump(mode="json")
    update: dict = {"resource_list": data, "action": None}
    if state.get("action") and state["request"]["type"] == "message":  # a button needs no explanation
        reply = _explain(_changes(state, data))
        update["messages"] = [*state["messages"], {"role": "assistant", "content": reply}]
    return update


def await_user(state: SearchState) -> dict:
    # Nothing else in this node: a node restarts from the top when the graph resumes.
    return {"request": interrupt("waiting for the user")}


def _interpret_request(state: SearchState, text: str, problems: list[str]) -> str:
    titles = {c["resource"]["id"]: c["resource"]["title"] for cs in state["candidates"] for c in cs}
    current = [
        {
            "skill": g["gap"]["skill"],
            "priority": g["gap"]["priority"],
            "resources": [
                {"id": r["resource"]["id"], "source": r["source"],
                 **{k: r["resource"][k] for k in ("title", "provider", "format", "level", "cost", "hours")}}
                for r in g["resources"]
            ],
        }
        for g in state["resource_list"]["gaps"]
    ]
    removed = [{"id": i, "title": titles.get(i, i)} for i in state.get("removed_ids", [])]
    request = (
        f"Current list, by skill gap:\n{json.dumps(current, indent=2)}\n\n"
        f"Removed earlier:\n{json.dumps(removed, indent=2) if removed else 'none'}\n\n"
        f"Skipped skills: {json.dumps(state.get('skipped_gaps', [])) if state.get('skipped_gaps') else 'none'}\n\n"
        f"Preferences so far: {json.dumps(Preferences(**state.get('preferences', {})).model_dump())}\n\n"
        f"Recent chat:\n{json.dumps(state.get('messages', [])[-RECENT_MESSAGES:], indent=2)}\n\n"
        f"The user's message:\n{text}"
    )
    if problems:
        request += "\n\nYour previous answer was rejected:\n- " + "\n- ".join(problems)
        request += "\nReturn a complete, corrected answer."
    return request


def read_message(state: SearchState, text: str) -> RefinementAction:
    """Return validated operations for the user's message, or raise InterpretFailed after
    MAX_ATTEMPTS. LLM errors propagate."""
    client = get_client()
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=web.section("interpret").replace("{max_searches}", str(MAX_SEARCHES_PER_TURN)),
            messages=[{"role": "user", "content": _interpret_request(state, text, problems)}],
            output_config={"format": ACTION_FORMAT},
        )
        reply = next((b.text for b in response.content if b.type == "text"), "")
        try:
            action = RefinementAction.model_validate_json(reply)
            problems = check_action(action, state)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
        if not problems:
            return action
    raise InterpretFailed("; ".join(problems))


def interpret(state: SearchState) -> dict:
    """Turn what the user sent into an action. Never raises: after a failure the graph pauses
    again unchanged, so the user can simply retry."""
    request = state["request"]
    # The Approve and Remove buttons send their operation directly: no model call needed.
    if request["type"] == "approve":
        return {"action": RefinementAction(approve=True).model_dump()}
    if request["type"] == "remove":
        return {"action": RefinementAction(remove_ids=[request["resource_id"]]).model_dump()}
    writer = get_stream_writer()
    text = request["text"]
    try:
        action = read_message(state, text)
    except InterpretFailed as exc:
        log.warning("Refinement message not understood: %s", exc)
        writer({"type": "error", "message": NOT_UNDERSTOOD})
        return {"action": None}
    except Exception as exc:
        log.warning("Refinement interpretation failed: %r", exc)
        writer({"type": "error", "message": friendly_error(exc)})
        return {"action": None}
    messages = [*state.get("messages", []), {"role": "user", "content": text}]
    if action.question:
        writer({"type": "token", "text": action.question})
        return {"messages": [*messages, {"role": "assistant", "content": action.question}], "action": None}
    return {"messages": messages, "action": action.model_dump()}


def after_interpret(state: SearchState) -> str:
    action = state.get("action")
    if not action:
        return "await_user"
    return "approve" if action["approve"] else "apply"


def apply(state: SearchState) -> dict:
    """Apply the operations to the state. Only "add more" and a cost filter that empties a gap
    need a new web search; everything else just re-ranks what is already known."""
    action = RefinementAction(**state["action"])
    old = Preferences(**state.get("preferences", {}))
    prefs = Preferences(
        cost=action.cost or old.cost,
        formats=old.formats if action.favour_formats is None else action.favour_formats,
    )
    removed = [i for i in [*state.get("removed_ids", []), *action.remove_ids] if i not in action.restore_ids]
    skipped = [s for s in [*state.get("skipped_gaps", []), *action.known_skills] if s not in action.restore_skills]
    removed, skipped = list(dict.fromkeys(removed)), list(dict.fromkeys(skipped))

    requests = [r.model_dump() for r in action.add_more[:MAX_SEARCHES_PER_TURN]]
    if prefs.cost != old.cost and prefs.cost != "any":
        asked = {r["skill"] for r in requests}
        had = {g["gap"]["skill"] for g in state["resource_list"]["gaps"] if g["resources"]}
        ranked = _ranked(state, set(removed), set(skipped), prefs)
        requests += [
            {"skill": gap["skill"]}
            for gap, items in zip(state["gaps"], ranked)
            if gap["skill"] in had and gap["skill"] not in asked and gap["skill"] not in skipped and not good(items)
        ][: MAX_SEARCHES_PER_TURN - len(requests)]

    per_gap = state.get("per_gap", search.PER_GAP)
    if action.add_more:
        per_gap = min(per_gap + PER_GAP_STEP, MAX_PER_GAP)
    return {
        "preferences": prefs.model_dump(), "removed_ids": removed, "skipped_gaps": skipped,
        "search_requests": requests, "per_gap": per_gap,
    }


def after_apply(state: SearchState) -> str:
    return "web_search" if state.get("search_requests") else "rank"


def approve(state: SearchState, config: RunnableConfig) -> dict:
    """Save the current list as the approved list: the graph's only hand-off to the scheduler."""
    user_id = config["configurable"]["thread_id"]
    try:
        approved = repository.build_approved_list(ResourceList(**state["resource_list"]))
    except ValidationFailed as e:
        reply = " ".join(e.errors.values())
    else:
        with SessionLocal() as db:
            repository.save_approved_list(db, user_id, approved, repository.get_gap_state(db, user_id), via="refinement")
        reply = (
            f"Your list of {len(approved.resources)} resources is approved. Open the Roadmap step to build your "
            "6-month plan. You can still change the list here and approve it again."
        )
    get_stream_writer()({"type": "token", "text": reply})  # shown live when approval came from the chat
    return {"messages": [*state.get("messages", []), {"role": "assistant", "content": reply}], "action": None}


# --- Graph --------------------------------------------------------------------------


def build_graph(checkpointer):
    g = StateGraph(SearchState)
    for name, node in (
        ("retrieve_kb", retrieve_kb), ("web_search", web_search), ("merge_dedupe", merge_dedupe),
        ("verify_urls", verify_urls), ("rank", rank_node), ("present", present), ("await_user", await_user),
        ("interpret", interpret), ("apply", apply), ("approve", approve),
    ):
        g.add_node(name, node)
    g.add_edge(START, "retrieve_kb")
    for a, b in (
        ("retrieve_kb", "web_search"), ("web_search", "merge_dedupe"), ("merge_dedupe", "verify_urls"),
        ("verify_urls", "rank"), ("rank", "present"), ("present", "await_user"), ("await_user", "interpret"),
        ("approve", "await_user"),
    ):
        g.add_edge(a, b)
    g.add_conditional_edges("interpret", after_interpret, ["apply", "approve", "await_user"])
    g.add_conditional_edges("apply", after_apply, ["web_search", "rank"])
    return g.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    """The compiled graph with its SQLite checkpointer (one connection, shared across threads;
    SqliteSaver serializes access with its own lock)."""
    global _graph
    if _graph is None:
        _graph = build_graph(SqliteSaver(sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)))
    return _graph
