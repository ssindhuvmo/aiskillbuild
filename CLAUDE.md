# CLAUDE.md

AI Career Strategist: React (Vite) frontend + FastAPI backend. `SPEC.md` is the source of truth for scope and
milestones; `README.md` has setup steps. Build only the current milestone.

## Layout
- `backend/app/` — FastAPI app. `main.py` wires CORS, the session middleware and routers. `routes/` are thin:
  parse the request, call `core/`, map errors to HTTP. No business logic in routes.
- `backend/core/` — everything else:
  - `config.py` — env config (loads `backend/.env`); injects `truststore` so HTTPS uses the OS cert store.
  - `db.py` — engine, `SessionLocal`, `get_db` dependency. `models.py` — SQLAlchemy tables. `schemas.py` — Pydantic I/O.
  - `repository.py` — all DB access.
  - `auth.py` — `verify_google_token` and the `current_user` dependency.
  - `agents/<name>/` — one module per agent with its own `prompt.md`: `intake/` (streaming chat with a
    `record_profile` tool), `gap_analysis/` (one structured-output call), `course_search/` (the LangGraph
    graph: web search, refinement chat, approval) and `scheduler/` (one structured-output call plus the
    Python hour budget). `llm.py` — Anthropic client and `friendly_error`.
  - `knowledge/` — the knowledge base (`store.py`) and the retrieval layer (`retriever.py`).
- `backend/config/domains.json` — supported domains (edit here, not in code).
- `backend/data/knowledge_base.json` — curated resources + skill-tag vocabulary (edit here, not in code).
- `backend/scripts/check_kb_links.py` — live check of every knowledge-base URL (network; not in pytest).
- `frontend/src/` — `App.jsx` (auth gate, shell, routes), `api.js` (all fetch calls), `pages/`, `components/`,
  `styles/tokens.css` + `styles.css` (see "Design system and app shell").
- `docs/` — the BRD and PRD that `SPEC.md` is derived from, and `docs/mockups/` (the visual reference).

## Milestones
Numbered in `SPEC.md`: 1 intake, 2 Google sign-in, 3 skill gaps, 4 knowledge base + ranking, 5 resource approval +
scheduler + roadmap, 6 live web search + refinement (LangGraph), 7 design system and app shell; 8–14 are listed
there. Build one at a time and stop for testing after each.

## Orchestration decision: LangGraph for course search only
- The course search agent and conversational refinement (flow steps 4–5) are one LangGraph graph in
  `core/agents/course_search/`. Nodes: knowledge-base retrieval, live web search, merge + de-duplicate, URL
  verification, ranking, present. After presenting, the graph pauses (interrupt / human-in-the-loop) for the
  user's request, updates the list (re-searching only when needed), explains the changes and pauses again until
  the user approves.
- Graph state is persisted per signed-in user (LangGraph SQLite checkpointer or the existing DB, keyed by the
  session user) so refinement resumes after sign-out and sign-in.
- LLM calls inside nodes go through `core/llm.py` (model from `ANTHROPIC_MODEL`). FastAPI routes only invoke the
  graph; no graph logic in routes.
- Intake and gap analysis stay plain Python modules; don't port them to LangGraph.
- Retrieval and ranking stay plain, reusable functions (no LangGraph dependency); the graph only wraps them
  as nodes.
- When the user approves in the graph, it calls `repository.save_approved_list(..., via="refinement")`. That is
  the graph's only hand-off to the scheduler; don't change the scheduler for it.
- Tests run the graph end to end with the fake LLM client and a fake search tool (no network), covering the
  pause/resume refinement loop and approval.

## Auth rules (Milestone 2)
- Google Identity Services on the frontend sends the ID token to `POST /api/auth/google`; the backend verifies it
  against `GOOGLE_CLIENT_ID`, upserts the `User` (primary key `user_id` = Google `sub`) and stores only that sub in
  a signed httpOnly session cookie (Starlette `SessionMiddleware`, `SESSION_SECRET`, SameSite=Lax, Secure).
- Every data endpoint takes `user: User = Depends(current_user)` and uses `user.user_id`. Never put a user ID in an
  API path, query or body. Only `/api/health` and `/api/auth/google|logout` are public.
- "Start over" (header) calls `DELETE /api/account/data` → `repository.delete_user_data`, which deletes the user's
  rows from every table except `users` (the session stays). A new table with a `user_id` must be added to that
  function; `tests/test_account.py` fails if one is missed.
- Frontend never stores identity itself; it calls `/api/auth/me` on load, and any 401 returns to the sign-in screen.

## Skill-gap analysis (Milestone 3)
- `gap_analysis/schemas.py`: `GapInput` (profile + `Correction`s; room for resume data) → `GapAnalysis`.
- `agent.analyze` calls `client.messages.parse(output_format=GapAnalysis)`. A reply is rejected if Pydantic
  validation fails (the API schema can't express min/max limits, so Pydantic enforces them) or `check_rules`
  finds problems (duplicate skills, a "knows" skill left as a gap, a "lacks" skill kept as a strength, total
  effort over the hour budget). Up to `MAX_ATTEMPTS` tries, feeding the problems back; then `GapAnalysisFailed`
  → HTTP 502. LLM errors → 503.
- `GapAnalysis.gaps` is what the 6-month plan covers: at most `MAX_GAPS` (8), with total `effort_hours` within
  `budget(hours_per_week)` × `EFFORT_TOLERANCE` (1.1). Further gaps go in `later_gaps` ("Later / optional" on the
  page): the same rules apply to them, but course search and the scheduler read only `gaps`. A saved analysis
  that no longer validates (e.g. more than 8 gaps) is treated as missing, so the page analyzes again.
- `gap_analyses` table (one row per user): current analysis, corrections, `profile_snapshot`, `confirmed`. Every
  run is also logged to `agent_outputs`. `stale` = snapshot differs from the current profile; any profile edit
  un-confirms the analysis and clears `Profile.inferred_skills` (set to the strengths on confirm).
- Analysis requires a confirmed profile (409 otherwise). It's a blocking request (20–40 s); the page shows
  rotating progress messages.

## Knowledge base + ranking (Milestone 4)
- `Retriever` protocol (`core/knowledge/retriever.py`): `search(gap, profile, limit) -> list[Candidate]`, where
  `Candidate.match_score` (0–1) is the only relevance signal ranking uses. `TagRetriever` maps the gap's skill
  name (fallback: `why_needed`) to vocabulary tags by whole-word alias match and scores the weighted share of
  those tags a resource covers (`broad_tags` count half; the denominator is at least 1; +0.2 for the user's domain
  on domain-specific gaps). `get_retriever()` is the only swap point for a future vector retriever (local
  embeddings + sqlite-vec); ranking, API and UI must not change for that.
- `course_search/ranking.py` (pure): score = 0.45 relevance + 0.20 level fit + 0.20 domain fit + 0.15 time fit
  (`WEIGHTS`); `diversify` penalizes repeated formats/costs to mix courses/papers/projects and free/paid.
- `course_search/search.py`: `retrieve` → `merge_dedupe` (by URL) → `rank` → `present` (gaps by priority, ≤ 4
  each, drops score < `MIN_SCORE` or relevance < `MIN_RELEVANCE`, a resource shown once under its best gap with
  `also_covers`). `find_resources` chains them (tests only); the graph wraps the same functions as nodes
  (web search before `merge_dedupe`, URL verification before `rank`). `merge_dedupe` keeps the curated entry
  when the web finds the same URL.
- `resource_lists` table (one row per user) with a `snapshot` of the gap analysis + search profile; `stale` =
  snapshot differs or gaps no longer confirmed. Search needs confirmed, current gaps (409 otherwise). Every run
  is logged to `agent_outputs` as `course_search`.
- Knowledge-base URLs must be real: run `scripts/check_kb_links.py` after editing the file.

## Approval + scheduler + roadmap (Milestone 5)
- Approved list = the contract between course search and the scheduler. `ApprovedList` (`course_search/schemas.py`)
  holds full `Resource` objects; `approved_lists` table (one row per user) with the same snapshot as the resource
  list and `approved_via`. `repository.save_approved_list` is the only write path and `get_approved_list` (None
  when missing or stale) the only read path. Approval always covers the whole current list
  (`repository.build_approved_list`) and is written by the graph's `approve` node (see Milestone 6).
- `scheduler/schemas.py`: `SchedulerInput` → `RoadmapDraft` (what the LLM returns: 3 phases with a portfolio
  project each, then 6 months of weeks and tasks; tasks reference `resource_id`, never URLs) → `Roadmap` (saved:
  links copied from the approved list, hour totals, `unscheduled` resources).
- `scheduler/budget.py` (pure) owns the calendar and the budget: `WEEKS` = 26, `MONTH_WEEKS` = 4/4/5/4/4/5,
  `budget()` = hours per week × 26. `check_budget` rejects a draft with a wrong calendar, a week over the weekly
  hours, a total over budget, an unknown `resource_id`, a `learn` task without a `resource_id`, more `learn` hours for a resource than it takes, or a
  phase without `project` tasks. Whole-plan problems are listed first. `finalize` builds the `Roadmap`.
- `agent.build` calls `client.messages.create(output_config=...)` (not `messages.parse`) so it can check
  `stop_reason` before parsing: `max_tokens` logs an error and raises `SchedulerTruncated` at once (no retry).
  Otherwise Pydantic + `check_budget`, up to `MAX_ATTEMPTS` with the problems fed back, then `SchedulerFailed`.
  Both → HTTP 502; LLM errors → 503; no approved list → 409. An over-budget roadmap is never saved.
- `roadmaps` table (one row per user) with a snapshot of the approved list + profile; `stale` = snapshot differs
  or no current approved list. Every run is logged to `agent_outputs` as `scheduler`, every approval as
  `resource_approval`. `GET /api/roadmap/export.md` returns `scheduler/export.py::to_markdown` as a download.
- Generation is a blocking request (about 30–90 s) with rotating progress messages (`components/Progress.jsx`).

## Web search + refinement graph (Milestone 6)
- `course_search/graph.py`: `retrieve_kb → web_search → merge_dedupe → verify_urls → rank → present →
  await_user` (pause) `→ interpret →` `apply` (→ `web_search` only when a new search is needed, else `rank`) or
  `approve` (→ `await_user`). The graph never ends: approval pauses again so the user can keep refining. State
  is plain JSON (`model_dump`); `await_user` contains only `interrupt()` because a node restarts on resume.
- `course_search/agent.py` is all the routes call: `run_for_user` (deletes the user's thread, runs to the first
  pause), `chat_turn` (SSE events from `graph.stream(Command(resume=...), stream_mode="custom")`),
  `approve_for_user`, `state_for_user`, `check_ready`, `reset_for_user`. One run per user at a time (lock).
  Nodes that touch the DB open their own `SessionLocal()`; callers `db.expire_all()` afterwards.
- Checkpoints: `SqliteSaver` on its own file (`CHECKPOINT_DB`, default `backend/graph_checkpoints.db`),
  `thread_id` = user id. The refinement chat lives only in graph state. "Start over" also calls
  `reset_for_user`. A saved list without a paused thread is reported `stale` so the page rebuilds it.
- Web search (`web.py`): `WebSearcher` protocol, `get_searcher()` is the swap point. `AnthropicWebSearcher`
  uses the basic `web_search_20250305` tool (its results arrive as `web_search_tool_result` blocks) plus a
  `record_resources` client tool, `tool_choice` auto, and continues on `pause_turn`. A finding is kept only if
  Pydantic accepts it (`WebFinding`) and its URL is in that reply's search results. Relevance is the model's
  0–1 rating capped at 0.9; ids are `web-<sha1 of url>`. A failed search never fails the list: knowledge-base
  results plus `notice`.
- URL verification (`verify.py`): `check` (http(s) and public hosts only) is shared with
  `scripts/check_kb_links.py`; `get_checker()` is the swap point. Web results with status `fail` are dropped,
  `blocked` (401/403/429) are kept. Knowledge-base links are not re-checked at runtime.
- Refinement: `interpret` makes one structured-output call → `RefinementAction` (operations only, never list
  content or URLs), validated by Pydantic + `check_action`, up to `MAX_ATTEMPTS` with problems fed back.
  `interpret` never raises: on failure it emits an `error` event and the graph pauses unchanged. `apply` is pure
  Python (removed ids, skipped gaps, `Preferences`, search requests); `apply_preferences` runs after
  `ranking.rank` (cost is a filter, favoured formats get `FAVOUR_BOOST`), so `ranking.py` stays untouched.
  `present` saves via `save_resource_list` and streams the explanation (plain `summary` if the LLM fails).
  "I already know X" hides the gap's resources; it never changes the gap analysis.
- Web search cost: the first pass searches only gaps with fewer than `MIN_CURATED` (3) good knowledge-base
  candidates (`good()` = passes `present`'s thresholds), `max_uses` 2 per gap; later passes search only what
  `apply` requests. Every run logs `Web search run: N of M gaps searched (...), K web searches` at INFO
  (`app/main.py` adds a handler for the `core` logger; K comes from the API's usage).
- Buttons resume the graph with their operation directly, no LLM call and no chat message: Approve
  (`{"type": "approve"}`) and a card's Remove (`{"type": "remove", "resource_id"}` → the same `remove_ids`
  operation the chat produces; `present` skips the explanation unless the request was a chat message).
- Endpoints: `POST /api/resources/search` (blocking), `POST /api/resources/chat` (SSE: `token`, `state` with
  the `ResourceState`, `done`, `error`; 409 without a current list), `POST /api/resources/remove`
  (`resource_id`; 409 missing/stale, 422 not on the list), `POST /api/resources/approve` (no body; 409
  missing/stale, 422 empty list). `ResourceState` carries `messages` and `notice`; `approval_stale` is also
  true when the list no longer matches the approved ids.
- One prompt file with `# web_search`, `# interpret` and `# explain` sections (`web.section(name)`).

## Design system and app shell (Milestone 7)
- Match the look of `docs/mockups/` but never copy their inline styles or sample data. Mockup features that
  belong to a later milestone are built in that milestone, not earlier.
- `styles/tokens.css` is a copy of `docs/mockups/design-tokens.css` (plus `--color-danger` and
  `--color-overlay`) and the only place with hex values; `styles.css` and components use the variables.
  Inline `style` is only for computed widths (`ProgressBar`).
- Layout is wrapping flex rows (`.split`, `.card-row`), so pages fit 390 px without sideways scrolling; wide
  tables go in `.table-scroll`. Under 800 px the sidebar becomes a top bar with a Menu button.
- Accessibility rules from the mockups: real buttons, links and labels, 44 px controls
  (`--control-min-height`), dark text on primary buttons, `aria-current` on the active nav item (from
  `NavLink`), `aria-pressed` on chips, `role="alert"` on error text, visible `:focus-visible` outlines.
- Components: `Sidebar`, `PageHeader`, `Card`, `Button` (`variant`; `to` makes it a link), `SkillBadge`,
  `FilterChip`, `MetricCard`, `ProgressBar`, `Chat` (used by Intake and Resources; the page owns messages
  and input), `Timeline` (`Phase`, `Month`, `Week`, `TaskRow`, `Milestone`), `Notice`, `ConfirmDialog`,
  `Icon` / `Logo`, plus `ProfileSummary` (the Profile Card), `ResourceCard` and `Progress`. Reuse these
  before adding markup to a page.
- `App.jsx`: signed out, every path shows `pages/Home.jsx`; signing in on `/` goes to `/intake`. Signed in,
  `/` is Home and every other route renders inside `Shell` (sidebar + `<main>`), so pages return fragments,
  not `<main>`. Sidebar pages that are not built yet use `pages/ComingSoon.jsx`.
- `profileContext.js` holds the profile for the sidebar card: `App` loads it with `getIntake()` and `Intake`
  updates it on every profile change. No endpoint exists just for the shell.
- There are no frontend tests; check with `npm run build` and in the browser at desktop and 390 px widths.

## Conventions
- Secrets live only in `backend/.env`; `frontend/.env` holds only `VITE_GOOGLE_CLIENT_ID`. Both are gitignored;
  keep the `.env.example` files in sync when adding variables.
- Chat endpoints stream Server-Sent Events; the stream opens its own DB session.
- No migrations yet: schema changes mean deleting `backend/career_strategist.db` in dev. A full reset deletes
  `backend/graph_checkpoints.db` as well.
- Never disable SSL verification. Use truststore (already injected in `core/config.py`; for pip use
  `--use-feature=truststore`).

## Tests
- `cd backend && pytest`. `tests/conftest.py` sets test env vars, uses in-memory SQLite and replaces
  `core.auth.verify_google_token` with a fake (tokens `good:<sub>`), so tests need no network.
  Use the `anon` fixture (HTTPS TestClient so the Secure cookie is sent) and `login(client, sub)`.
- The LLM is faked in tests by monkeypatching the agent module's `get_client`. The gap-analysis fake validates
  replies with `GapAnalysis.model_validate`, so bad data raises `ValidationError` like the SDK does. The
  scheduler fake (`tests/test_scheduler_budget.py`) returns raw JSON text with a `stop_reason`; its `draft()`
  helper builds a valid plan to mutate.
- The graph runs in every test with a real `SqliteSaver` on `:memory:`. `conftest.py`'s autouse `searcher`
  fixture replaces `web.get_searcher` and `verify.get_checker`: fill `searcher.results[skill]` (candidates or an
  exception) and `searcher.link_status[url]`; `searcher.calls` records searches. `tests/test_course_graph.py`
  fakes the refinement LLM (`graph.get_client`): `messages.create` returns scripted actions, `messages.stream`
  the explanation. Test user ids must be unique across files (one shared in-memory DB).
- New endpoints need a 401-without-login case in `tests/test_auth.py`.
