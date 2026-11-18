# CLAUDE.md

AI Career Strategist: React (Vite) frontend + FastAPI backend. `SPEC.md` is the source of truth for scope and
milestones; `README.md` has setup steps. Build only the current milestone.

## Layout
- `backend/app/` — FastAPI app. `main.py` wires CORS, the session middleware and routers. `routes/` are thin:
  parse the request, call `core/`, map errors to HTTP. No business logic in routes.
- `backend/core/` — everything else:
  - `config.py` — env config (loads `backend/.env`); injects `truststore` so HTTPS uses the OS cert store.
  - `db.py` — engine, `SessionLocal`, `get_db`, `init_db` (Alembic upgrade with a pre-migration backup).
    `models.py` — SQLAlchemy tables (incl. `Resume`). `schemas.py` — Pydantic I/O.
  - `repository.py` — all DB access.
  - `auth.py` — `verify_google_token` and the `current_user` dependency.
  - `agents/<name>/` — one module per agent with its own `prompt.md`: `intake/` (streaming chat with
    `record_profile` and `suggest_roles` tools; `validation.py` defines the steps, levels and options),
    `resume_parser/` (file checks + text extraction, one structured-output call, plain-Python rules, file
    storage), `gap_analysis/` (one structured-output call), `job_search/` (Job Match: `JobSource` + skill mapping),
    `course_search/` (the LangGraph graph: web and
    YouTube search, refinement chat, filters, approval), `scheduler/` (Python placement and hour budget; one structured-output
    call per phase, for the text only; `tracking.py` for dates and status) and `report/` (the Transition Report:
    one structured-output call for two sections, the rest assembled in Python).
    `llm.py` — Anthropic client and `friendly_error`. `pdf.py` — the fpdf2 `Document` writer for every PDF
    export, with DejaVu Sans bundled in `core/fonts/` (fpdf2's built-in fonts are Latin-1 only).
  - `knowledge/` — the knowledge base (`store.py`) and the retrieval layer (`retriever.py`).
  - `progress/` — Dashboard and Progress Review (milestone 11, no LLM): `readiness.py` (the formula),
    `assemble.py` (dashboard and review from `ProgressData`), `schemas.py`, `service.py` (what the routes call).
- `backend/config/domains.json` — supported domains (edit here, not in code).
- `backend/data/knowledge_base.json` — curated resources + skill-tag vocabulary (edit here, not in code).
- `backend/data/youtube_channels.json` — trusted YouTube channels by channel id (edit here, not in code).
- `backend/scripts/check_kb_links.py` — live check of every knowledge-base URL (network; not in pytest).
  `scripts/list_feedback.py` prints the feedback form's messages.
  `scripts/check_youtube_channels.py` checks the trusted channel ids against the real YouTube API.
- `backend/alembic.ini`, `backend/migrations/` — Alembic (`versions/0001_baseline` = the milestone-7 schema).
- `backend/uploads/<user id>/` — uploaded resumes (`UPLOAD_DIR`; gitignored, never served).
- `frontend/src/` — `App.jsx` (auth gate, shell, routes), `api.js` (all fetch calls), `pages/`, `components/`,
  `styles/tokens.css` + `styles.css` (see "Design system and app shell").
- `docs/` — the BRD and PRD that `SPEC.md` is derived from, and `docs/mockups/` (the visual reference).

## Milestones
Numbered in `SPEC.md`: 1 intake, 2 Google sign-in, 3 skill gaps, 4 knowledge base + ranking, 5 resource approval +
scheduler + roadmap, 6 live web search + refinement (LangGraph), 7 design system and app shell, 8 expanded
intake + resume + Career Profile, 9 resource sources and preferences, 10 roadmap tracking + Transition Report,
11 Dashboard + Progress Review, 12 Job Match; 13–14 are listed there. Build one at a time and stop for testing after each.

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
- `gap_analysis/schemas.py`: `GapInput` (profile, capabilities, `ai_level`, reviewed resume, `Correction`s) →
  `GapAnalysis` (see Milestone 8 for sources and levels).
- `agent.analyze` calls `client.messages.parse(output_format=GapAnalysis)`, then `repair` fixes in Python what the
  prompt asks for (an unmatched `resume` strength → `assumed`; a target not above the current level → next level;
  last gaps moved to the front of `later_gaps` until the budget fits, keeping one). A reply is rejected if Pydantic
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
- `course_search/ranking.py` (pure): score = weighted relevance, level fit, domain fit and time fit, plus
  preference and quality fit since milestone 9 (`WEIGHTS`, see Milestone 9); `diversify` penalizes repeated formats/costs to mix courses/papers/projects and free/paid.
- `course_search/search.py`: `retrieve` → `merge_dedupe` (by URL) → `rank` → `present` (gaps by priority, ≤ 4
  each, only resources passing the relevance gate `passes()`, a resource shown once under its best gap with
  `also_covers`). The gate: relevance ≥ `MIN_RELEVANCE` (0.7) and at least one of the gap's specific (non-broad)
  tags in `matched_on`; a gap with no specific tags is gated on relevance alone. Level, domain and time only rank
  what passes; there is no minimum total score. `find_resources` chains them (tests only); the graph wraps the
  same functions as nodes (web search before `merge_dedupe`, URL verification before `rank`). `merge_dedupe` keeps the curated entry
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
- Python builds the plan, the LLM only writes the text. `scheduler/schemas.py`: `SchedulerInput` → `Roadmap`
  (saved: weeks, tasks with ids `w<week>-<n>`, links copied from the approved list, hour totals, `unscheduled`
  resources, 3 `phases` with `gaps` and `narrative` = pending | ai | default). `PhaseNarrative` is all the LLM
  returns: phase name, `first_month` / `second_month` (theme + milestone), practice task titles by id, and the
  portfolio `project` (title, problem, named public dataset, deliverables). No hours, weeks, resources or URLs.
- `scheduler/budget.py` (pure) owns the calendar and constants: `WEEKS` = 26, `MONTH_WEEKS` = 4/4/5/4/4/5,
  `PHASE_MONTHS`, `budget()` = hours per week × 26, `PRACTICE_SHARE` (0.35), `PROJECT_SHARE` (0.25 of each
  phase reserved at its end), `PROJECT_MIN_HOURS`. `check_budget(roadmap, data)` is a safety assertion
  (calendar, weekly and total hours, totals add up, links match the approved list, learn hours ≤ a resource's
  hours, 3 phases each with project work); a plan that fails it is never saved (`PlacementFailed`).
- `scheduler/placement.py` (pure) `place(data)`: resources ordered by gap priority, the gap's order, then level
  (beginner first); weeks filled in order up to the weekly hours, long resources split (exactly their hours of
  learn time), practice on the same resource after each; the phase's project right after its last study hour,
  proportionate and within the reserve. No padding: what doesn't fit goes to `unscheduled`, empty weeks stay
  empty. It returns a complete roadmap with plain default text and every phase `pending`.
- `scheduler/narrative.py`: `write` = one `messages.parse(output_format=PhaseNarrative)` call per phase;
  `check` rejects unknown practice ids and links; `MAX_ATTEMPTS` = 2 (one retry with the problems fed back),
  then `NarrativeFailed`. `apply` copies the text in (only text changes); `use_default` keeps the plain text.
- `scheduler/agent.py` `generate(user_id)` (SSE, own DB session, one run per user via a lock): place + check +
  `save_roadmap(log=False)` → `state` event at once; the 3 phases run in parallel (`ThreadPoolExecutor`), each
  applied, saved (`update_roadmap`) and sent as a `state` event with `phase` and `notice` (set when the default
  text was kept: LLM error, missing key or failed checks) → `done`. A roadmap is always produced; the finished
  one is logged once to `agent_outputs` as `scheduler`. A phase left `pending` by an interrupted run reads as
  `default` (`state_for_user`).
- `roadmaps` table (one row per user) with a snapshot of the approved list + profile; `stale` = snapshot differs
  or no current approved list. Every approval is logged as `resource_approval`. Endpoints: `GET /api/roadmap`,
  `POST /api/roadmap/generate` (SSE; 409 without a current approved list or while a run is in progress),
  `GET /api/roadmap/export.md` (`scheduler/export.py::to_markdown`).
- The Roadmap page shows the placed plan within a second or two; each phase says it is being written until its
  text arrives, and says when it shows plain text.

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
- Web search cost: the first pass (`_first_pass`) looks at gaps with fewer than `MIN_CURATED` (2) knowledge-base
  candidates passing the gate (`good()`), highest priority first. Each uses the shared cache when it has a hit,
  else is searched, at most `MAX_FIRST_PASS` (4) searched gaps per run. `max_uses` 1 per gap, ≤ `MAX_RESULTS` (5)
  results. Later passes search only what `apply` requests and never read or write the cache (they carry the
  user's request). Every run logs `Web search run: N of M gaps searched (...), C from cache (...), K web searches,
  I input / O output tokens` at INFO (`app/main.py` adds a handler for the `core` logger; the counts come from the
  API's usage).
- Web results are tagged from their title and description with the knowledge-base vocabulary (`skills`;
  `matched_on` = the gap's tags among them, or the gap name when the gap has no tags), so the gate treats
  them like curated resources.
- `web_search_cache` (shared across users, no user data): first-pass results per `web.cache_key` = (normalized
  skill, resource level for the user's AI level, domain only for domain-specific gaps), reused for `CACHE_DAYS`
  (14), via `repository.get_cached_search` / `save_cached_search`. A failed search is not cached.
- `web_resource_candidates` (no user data): every approved web resource, with how many approvals newly included
  it (`save_approved_list` → `_record_web_candidates`). `scripts/list_web_candidates.py` lists the ones not in
  the knowledge base (`--json` for paste-ready entries) so good ones can be promoted into `knowledge_base.json`.
  Neither shared table is touched by "Start over"; tests clear both in the `anon` fixture.
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

## Expanded intake, resume and Career Profile (Milestone 8)
- Profile fields (`Profile`): `current_role`, `target_role`, `years_experience`, `domain`, `hours_per_week`,
  `capabilities` ({area: level} for the 5 `CAPABILITY_AREAS`), `learning_preferences` (None = not asked),
  `constraints` (None = not asked, {} = none), `additional_context` (None = not asked, "" = skipped),
  `resume_skipped`, `field_sources` ({field: "resume" | "user"}, shown as "· from resume").
- `intake/validation.py` is the single definition of the 8 steps (`STEPS`: goal → resume → background → hours →
  capabilities → preferences → constraints → context), the validators, `REQUIRED` and `ai_level()` (mean of the
  ML and AI / LLMs ratings, rounded down; the only AI level ranking and the scheduler use). "Help me choose" moves
  the goal step after background. `frontend/src/capabilities.js` mirrors the option lists.
- **One level scale everywhere:** `LEVELS` = None, Beginner, Intermediate, Experienced (capability ratings and a
  gap's `current_level`); `TARGET_LEVELS` adds Expert for a gap's `target_level` only. Both live in
  `validation.py` and are mirrored in `capabilities.js`; never introduce other level names.
- Resume parser (`agents/resume_parser/`):
  - `extract.read` checks size (≤ 5 MB → 413), extension + magic bytes (`%PDF-`, or a ZIP with
    `word/document.xml`; else 415), extracts text with pypdf / python-docx (no text → 422), truncates to
    `MAX_CHARS`.
  - `agent.parse`: one `messages.parse(output_format=ResumeData)` call with the text inside `<resume>` (resume
    tags in the text are stripped; the prompt says it is untrusted). `rules.check_rules` requires every skill,
    title, employer and certification name to appear in the normalized text, and valid dates (start ≤ end ≤
    today). Up to `MAX_ATTEMPTS` with problems fed back. **Partial results:** if the last Pydantic-valid reply
    still fails, `rules.filter_unverified` keeps what passes and returns `dropped` labels; `ResumeParseFailed`
    (502) only when no reply validated or nothing usable is left. LLM errors → 503.
  - `rules.years_of_experience` merges overlapping role intervals up to today (the LLM never supplies it);
    `rules.prefill` → current role (latest), years, industry.
  - `storage`: `<UPLOAD_DIR>/<user id, or its sha256 if not [A-Za-z0-9_-]>/resume.<ext>`; a new upload
    replaces the old file; files are never served.
- `resumes` table (one row per user): file info, extracted `text`, `draft` ({data, dropped}) while `status` is
  `review`, `data` (the reviewed `ResumeData`) once `reviewed`. Only `repository.reviewed_resume` is used
  downstream; the intake model gets a summary of it, never the text. Confirm is refused while in review.
- Endpoints (`routes/resume.py`): `GET /api/resume` (`ResumeState`), `POST` (multipart upload, blocking
  10–20 s; nothing is stored if parsing fails), `PUT` (the reviewed `ResumeData`; dates checked, not the text;
  fills profile fields that are empty or still "resume"-sourced, marked "resume"; un-confirms profile and
  gaps), `DELETE` (row + file; values stay but lose the "resume" label). "Start over" deletes the folder.
- Gap analysis: `Strength.source` is `resume` (must match a resume skill, title or certification, whole-word),
  `user` (ratings, context, corrections) or `assumed`; each `Gap` has `current_level` / `target_level` with the
  target above the current level. The snapshot is `repository.gap_inputs` (analysis fields + reviewed resume),
  so a resume change makes the analysis stale. Analyses saved before this milestone fail validation and are
  redone.
- Frontend: Intake shows "Question N of 8" and a widget per step under the chat (`IntakeStep`: `ResumeUpload`,
  capability / preference / constraint pickers from `ProfileInputs`, role suggestion chips); widgets save via
  the API, then send a short chat message so the agent moves on. A draft opens `ResumeReview` in the main
  column (Save / Discard). `ProfileSummary` is the Career Profile card (Name from Google via
  `ProfileContext.user`, every field, the resume with "Review again"). Skill Analysis groups strengths by source
  and draws `GapChart` (bar = current, marker = target; their widths are the only inline style).
- Gap buttons (`gap_analysis/adjust.py`, `POST /api/gaps/adjust` with `action` knows | not_needed | later |
  plan | restore, `skill`, `make_room`): plain-Python edits to the saved analysis, no LLM call. Each one is saved
  as a `Correction` (at most one button correction per skill; a `not_needed` one keeps the `gap` and `in_plan`
  for Restore) through `repository.update_gap_analysis`, which keeps the snapshot and un-confirms. `check_rules`
  enforces them on re-analysis; `repair` never moves a `plan` gap to later. A `plan` that doesn't fit
  (budget × `EFFORT_TOLERANCE` or `MAX_GAPS`) changes nothing and returns `GapState.suggestion`
  (`BudgetSuggestion`); resending with `make_room` = its `move` does the swap. Limits that can't be met (an empty
  plan, a full later list) → 422; no current analysis → 409.

## Resource sources and preferences (Milestone 9)
- Formats (`knowledge/schemas.py` `Format`): course, video, article, paper, tutorial, repository, book, project.
  The page's Type filter groups them with `course_search/schemas.py` `TYPE_OF` (paper and tutorial → article);
  `ResourceFilters.jsx` and `ResourceCard.jsx` mirror the groups and labels. `Source` = knowledge_base | web |
  youtube. `Resource.quality` (`Quality`: views, likes, trusted) is set only from a source's own data.
- `SearchProfile` adds `preferences` (intake `learning_preferences`, [] when not asked) and `free_only`
  (`constraints.budget == "free_only"`), so changing either makes the list stale.
- Ranking (`ranking.py`): `WEIGHTS` relevance 0.40, level 0.15, domain 0.15, time 0.10, preference 0.15,
  quality 0.05. `preference_fit` uses `PREFERENCE_MATCH` (intake key → format/cost test; 1, else
  `NO_PREFERENCE_MATCH`; `NEUTRAL` when nothing usable). `quality_fit`: YouTube views (log scale) and like
  rate, trusted channels at least `TRUSTED_QUALITY`; curated `CURATED_QUALITY`; web `NEUTRAL`.
  `ScoreBreakdown.preference` / `quality` default to 0.5 so older saved lists still load.
- YouTube (`course_search/youtube.py`): `YouTubeSource` protocol, `get_youtube()` is the swap point (None without
  `YOUTUBE_API_KEY`). `YouTubeDataAPI` (httpx, truststore via config): one `search` (100 quota units, videos +
  playlists for "<skill> full course") then `videos` / `playlistItems` (1 unit each); `units` counts quota.
  `to_candidates` (pure) vets: ≥ `MIN_MINUTES`, tag match with the gap (weighted like `TagRetriever`, capped
  at `MAX_RELEVANCE`; title match for tagless gaps), trusted channel or ≥ `MIN_VIEWS`; level from title
  keywords; hours from the API durations. Errors raise `YouTubeError`, whose message never contains the key.
- The graph's first pass (`web_search` → `_youtube_first_pass`) searches YouTube for every gap unless the
  user's preferences leave out video, reusing `web_search_cache` (key prefixed `youtube: `, `CACHE_DAYS`).
  A failure or a missing key never fails the list: `YOUTUBE_UNAVAILABLE` / `YOUTUBE_OFF` notice. Later passes
  search only the web. YouTube links are built from API ids and not re-checked. Approved YouTube resources
  are knowledge-base candidates too (`_record_web_candidates`).
- Filters: `Preferences.levels` / `types` (and `cost`) are filters in `apply_preferences` via `keeps()`; a
  "free only" budget always drops paid. The chips resume the graph with `{"type": "filter", cost, levels,
  types}` (no LLM, no search, no explanation); the chat can set them too (`RefinementAction.levels` /
  `types`), and only a chat change that empties a gap triggers a web search. A gap emptied by filters gets the
  `FILTERED` note. `ResourceState` carries `preferences` and `free_only`.
- Save / Start / Complete (`resource_progress` table, one row per user and resource, with the `Resource` so it
  survives rebuilds; a row with nothing set is deleted): `repository.set_progress` / `get_progress`,
  `agent.progress_for_user` (only resources on the list or already in the user's progress; else 422).
  `ResourceState.progress` lists every row. Progress never changes the list or the approval.
- Endpoints: `POST /api/resources/filter` (`FilterIn`; 409 without a current list),
  `PUT /api/resources/progress` (`ProgressIn`: `resource_id` plus `saved` and/or `status`).

## Roadmap tracking and Transition Report (Milestone 10)
- `scheduler/tracking.py` (pure) works out due dates (`due_date` = start + 7·week − 1), status (items:
  done | overdue | this_week | not_started; weeks and phases: done | overdue | in_progress | not_started | empty),
  priority (a task's resource priority in the approved list the roadmap was built from, `repository.built_from`;
  project tasks and milestones take the phase's highest gap priority) and `next_steps` (3 tasks not done,
  overdue first) on every read: `track` → `RoadmapState.tracking`. Nothing but the start date and the checks
  is stored, and the LLM never supplies a date or status.
- `roadmaps.start_date` is set on the first build (`repository.today()`, patched in tests), kept on regenerate,
  changed via `PUT /api/roadmap/start-date`. Migration 0005 backfilled existing roadmaps from `updated_at`.
- Checks: `roadmap_item_progress` (one row per checked task id `w<week>-<n>` or milestone `m<month>`, with a
  `fingerprint` = kind | resource id | week). `done_items` ignores rows whose fingerprint no longer matches, so
  a check carries over a regenerate only to the same task. `PUT /api/roadmap/items` (`item_id`, `done`; 404
  without a roadmap, 422 for an id not in it). Checks never change the plan or the resource progress.
- Exports: `scheduler/export.py` `to_markdown` / `to_pdf` (dates, ticks, next steps); `GET /api/roadmap/export.pdf`.
- Report (`agents/report/`): `ReportNarrative` (`career_fit`, `strategy`) is all the LLM writes; `agent.write`
  makes one `messages.parse` call, `check` rejects links and percentages/scores, `MAX_ATTEMPTS` = 2, then
  `assemble.default_narrative` (plain text from the rationale and phases) with a `notice`; a report is always
  produced. `assemble.build` makes the 11 sections (SPEC order) from `repository.report_data` when the report
  is read, so facts, dates and links always match the saved data. `reports` table (one row per user):
  `narrative`, `source` (ai | default), `snapshot` (gap inputs, analysis, roadmap); `stale` when it differs.
  Checks don't make it stale. Logged to `agent_outputs` as `report`.
- Endpoints: `GET /api/report` (`ReportState`: status, `can_generate`, stale, report, notice),
  `POST /api/report/generate` (blocking, 409 without a current roadmap), `GET /api/report/export.md|pdf`
  (404 before one exists).
- Frontend: `Timeline` rows have real checkboxes (44 px `check-target`, label = task text), `Week` shows
  status and due date, `Phase` status and priority pills; labels in `src/tracking.js`. Roadmap page: start
  date, Immediate next steps, Export PDF, View Transition Report. `pages/Report.jsx` at `/report` (sidebar
  "Transition Report").

## Dashboard and Progress Review (Milestone 11)
- Every number is Python (`core/progress/readiness.py`, formula in its docstring, README and SPEC §4): per plan
  gap, `base` = current / target level index on `TARGET_LEVELS`; `progress` = 1 if marked completed, else the
  share of its approved resources' learn + practice hours done (checked tasks, or the whole resource when
  `resource_progress` says completed), averaged with `(confidence − 1) / 4` when rated; `credit` = base +
  (1 − base) × progress. Readiness = (strengths + Σ `WEIGHTS`·credit) / (strengths + Σ weights), weights 3/2/1
  by priority. Coverage = strengths + gaps at full credit, of strengths + plan gaps. Completion =
  `tracking.done_hours / planned_hours`. `planned_series` = the same per week over the scheduled hours. A gap's
  hours come from the approved list the roadmap was built from (`built_from`), so a replan doesn't move them.
- Tables (migration 0006): `skill_progress` (user, normalized skill: `completed`, `confidence` 1–5),
  `progress_notes`, `readiness_history` (one row per user and day, last write wins). All in
  `delete_user_data`. Marks for skills no longer in the plan are ignored, not deleted.
- `repository.progress_data` gathers `assemble.ProgressData` (None without a gap analysis);
  `assemble.dashboard` / `assemble.review` build the pages on every read. `record_readiness` upserts today's
  point; it is called by Update Progress, Recalculate, refresh, `set_item_done` and `set_progress` (status
  change) and never fails the request.
- Refresh my plan (BR-24/25) is plain Python, no gap re-analysis, so the approved list and snapshots stay valid:
  `placement.replan(data, roadmap, done, from_week, completed_resources, completed_gaps)` keeps every done task
  (same week, id, hours, so fingerprints match), closes weeks before `from_week` (`assemble.from_week`: this
  week clamped to 1–26), places each resource's remaining learn/practice hours from there, drops completed
  resources and gaps, puts undone project hours of phases that are over first ("Phase N portfolio project",
  which `narrative.apply` doesn't rename), and keeps those phases' text (`closed_phases`); other phases are
  `pending`. New ids continue each week's numbering. `check_budget(..., from_week)` exempts closed phases from
  the project rule. `agent.refresh` shares `_run` with `generate` (lock, SSE, only pending phases written,
  start date and snapshot kept, logged with `mode: "refresh"`).
- Endpoints: `GET /api/dashboard` (`DashboardState`), `POST /api/dashboard/readiness`, `GET|PUT /api/progress`
  (`ProgressState`, `ProgressReviewIn`; 409 without an analysis, 422 for a skill not in the plan or confidence
  outside 1–5), `POST /api/roadmap/refresh` (SSE; first `state` event has `from_week`; 409 without a current
  roadmap or while running).
- Frontend: `pages/Dashboard.jsx` (lazy-loaded in `App.jsx`, so Recharts stays out of the main bundle),
  `pages/ProgressReview.jsx`, `components/Charts.jsx` (`SkillRadar`, `ReadinessTrend`; Recharts can't use CSS
  variables, so `tokens()` reads them at render), `components/NextSteps.jsx` (shared with Roadmap). The radar
  axes are the plan gaps (fewer than 3 → a plain list); Jobs Applied is a placeholder until milestone 12.

## Job Match (Milestone 12)
- `job_search/source.py`: `JobSource` protocol, `get_job_source()` is the swap point (a jobs API later).
  `AnthropicJobSource`: one call with the basic `web_search_20250305` tool, `allowed_domains` = `JOB_SITES`
  (`core/config.py`, env `JOB_SITES`; subdomains included, an optional path narrows a site), `max_uses`
  `MAX_SEARCHES` (3), and a `record_jobs` client tool. `to_findings` keeps a `JobFinding` only if Pydantic
  accepts it, its URL is in that reply's search results and `on_allowed_site`; at most `MAX_JOBS` (10).
  LinkedIn is deliberately not in the default list (SPEC §10).
- `agent.run_for_user` (blocking, one run per user via a lock): search → `verify.get_checker()` per link
  (`fail` dropped, `blocked` kept as `Job.link = "blocked"`) → `assess` → `repository.save_job_search`
  (logged as `job_search`). `assess` = one `messages.parse(output_format=Assessments)` mapping each required
  skill to `have` (one of `matching.user_skills`: strengths, completed plan gaps, capability areas rated
  Intermediate+) or `in_plan` (a plan gap not completed), plus the explanation; `matching.check` accepts only
  names from those lists, each required skill once, no links / percentages; `MAX_ATTEMPTS` 2, then
  `fallback_matches` (name-only) with a notice. A source error → `SearchFailed` (503); no analysis → 409.
- Numbers are Python: `matching.view` computes score = covered / required on every read (a mapping to a
  plan gap counts once that gap is completed on Progress Review), the missing skills with the roadmap phase
  of their gap, and `parse_salary` turns the stated salary into annual `salary_min/max` (hourly → none).
- Tables (migration 0007): `job_searches` (one row per user: `query`, `jobs`, `notice`, `found_at`),
  `job_marks` (user, job id: `saved`, `applied`, `applied_at`, the `Job` so it survives a refresh; a row with
  neither is deleted). Both in `delete_user_data`. `JobState.kept` lists marked jobs not in the current
  results. The Dashboard's `jobs_applied` / `jobs_saved` count `job_marks`.
- Endpoints: `GET /api/jobs` (`JobState`), `POST /api/jobs/search` (`JobQuery`: location, remote, hybrid),
  `PUT /api/jobs/marks` (`JobMarkIn`; 422 for a job neither in the results nor marked).
- Frontend: `pages/JobMatch.jsx` (filters: Remote / Hybrid chips and Location are the search query, Salary
  filters the saved results client-side from `salary_min/max`; table with a match bar; detail panel with
  Apply link, Mark as applied, Save Job, Update Resume → `/resume`).
- Tests: `conftest.py`'s `searcher` fixture also fakes job search (`searcher.jobs.results`: JobFinding dicts
  or an exception) and the assessment LLM (`searcher.job_llm.replies`; default `assess_nothing`, a valid
  mapping that covers nothing). `tests/test_jobs.py` has `finding(n)` and `mapped(have=..., in_plan=...)`.

## Feedback (added with milestone 12)
- `Feedback` table (migrations 0008 + 0009; many rows per user: `rating` 1–5 or None, `areas` = a JSON list of
  `FeedbackArea` ([] = the whole platform; 0009 moved the old single `area` into it), `message`, `created_at`).
  `POST /api/feedback` (`FeedbackIn` in `core/schemas.py`: `areas` de-duplicated in order, message stripped, 1–`MAX_FEEDBACK`
  (2000) characters, else 422) → `repository.save_feedback`. `pages/Feedback.jsx` mirrors the areas and limit.
- "Start over" does not delete feedback: `delete_user_data` sets its `user_id` to None (so `test_account`'s
  "no rows left for the user" still holds). No admin UI: `scripts/list_feedback.py` (`--days N`, `--json`).
- Tests: `tests/test_feedback.py`.

## Conventions
- Secrets live only in `backend/.env`; `frontend/.env` holds only `VITE_GOOGLE_CLIENT_ID`. Both are gitignored;
  keep the `.env.example` files in sync when adding variables.
- Chat endpoints stream Server-Sent Events; the stream opens its own DB session.
- Schema changes go through Alembic: edit `core/models.py`, run `alembic revision --autogenerate -m "..."` in
  `backend/`, review the file (SQLite needs `render_as_batch`, already set; move data by hand where needed) and
  restart: `init_db` upgrades on start after backing up the DB file. `tests/test_migrations.py` fails if the
  migrations and models differ. Never delete the user's DB to change the schema. A full dev reset deletes
  `career_strategist.db`, `graph_checkpoints.db` and `uploads/`.
- Never disable SSL verification. Use truststore (already injected in `core/config.py`; for pip use
  `--use-feature=truststore`).

## Tests
- `cd backend && pytest`. `tests/conftest.py` sets test env vars, uses in-memory SQLite and replaces
  `core.auth.verify_google_token` with a fake (tokens `good:<sub>`), so tests need no network.
  Use the `anon` fixture (HTTPS TestClient so the Secure cookie is sent) and `login(client, sub)`.
- The LLM is faked in tests by monkeypatching the agent module's `get_client`. The gap-analysis fake validates
  replies with `GapAnalysis.model_validate`, so bad data raises `ValidationError` like the SDK does. The
  scheduler's narrative fake (`tests/test_scheduler_budget.py`, patched on `narrative.get_client`) takes dicts,
  exceptions or functions of the request (the phases run in parallel); `tests/test_roadmap.py::phase_reply`
  answers any phase and `generate(client)` returns the SSE events and the final state.
- The graph runs in every test with a real `SqliteSaver` on `:memory:`. `conftest.py`'s autouse `searcher`
  fixture replaces `web.get_searcher`, `youtube.get_youtube` and `verify.get_checker`: fill
  `searcher.results[skill]` / `searcher.youtube.results[skill]` (candidates or an exception) and
  `searcher.link_status[url]`; `searcher.calls` / `searcher.youtube.calls` record searches. The real YouTube
  client is tested over `httpx.MockTransport` (`tests/test_resource_sources.py`). `tests/test_course_graph.py`
  fakes the refinement LLM (`graph.get_client`): `messages.create` returns scripted actions, `messages.stream`
  the explanation. Test user ids must be unique across files (one shared in-memory DB).
- New endpoints need a 401-without-login case in `tests/test_auth.py`.
- Progress: `tests/test_readiness.py` (pure formula), `tests/test_replan.py` (pure `replan` plus the refresh
  endpoint; call `fake()` again before a refresh so the narrative fake has replies), `tests/test_progress.py`
  (endpoints, history per day, isolation; uses `test_roadmap_tracking.today`).
- Tracking: `tests/test_roadmap_tracking.py` (pure `track` plus endpoints; its `today` fixture patches
  `repository.today`). Report: `tests/test_report.py` `report_llm` fixture patches `report.agent.get_client`
  (valid text by default; pass dicts, exceptions or functions to script replies).
- The app's lifespan runs the migrations on the in-memory DB. The autouse `uploads` fixture points
  `resume_parser.storage.UPLOAD_DIR` at a temp folder. `tests/resume_files.py` builds DOCX and text PDFs in
  memory; `tests/test_resume_parser.py` has the parser's fake client (`fake`) and a valid reply (`good()`).
