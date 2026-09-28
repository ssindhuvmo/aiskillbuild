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
    `record_profile` tool) and `gap_analysis/` (one structured-output call). `llm.py` — Anthropic client and
    `friendly_error`.
- `backend/config/domains.json` — supported domains (edit here, not in code).
- `frontend/src/` — `App.jsx` (auth gate, header, routes), `api.js` (all fetch calls), `pages/`, `components/`.

## Milestones
Numbered in `SPEC.md`: 1 intake, 2 Google sign-in, 3 skill gaps, 4 knowledge base + ranking, 5 live web search +
refinement (LangGraph), 6 scheduler + roadmap. Build one at a time and stop for testing after each.

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
- LangGraph arrives in milestone 5. In milestone 4 keep retrieval and ranking as plain, reusable functions (no
  LangGraph dependency) so milestone 5 can wrap them as nodes.
- Tests run the graph end to end with the fake LLM client and a fake search tool (no network), covering the
  pause/resume refinement loop and approval.

## Auth rules (Milestone 2)
- Google Identity Services on the frontend sends the ID token to `POST /api/auth/google`; the backend verifies it
  against `GOOGLE_CLIENT_ID`, upserts the `User` (primary key `user_id` = Google `sub`) and stores only that sub in
  a signed httpOnly session cookie (Starlette `SessionMiddleware`, `SESSION_SECRET`, SameSite=Lax, Secure).
- Every data endpoint takes `user: User = Depends(current_user)` and uses `user.user_id`. Never put a user ID in an
  API path, query or body. Only `/api/health` and `/api/auth/google|logout` are public.
- Frontend never stores identity itself; it calls `/api/auth/me` on load, and any 401 returns to the sign-in screen.

## Skill-gap analysis (Milestone 3)
- `gap_analysis/schemas.py`: `GapInput` (profile + `Correction`s; room for resume data) → `GapAnalysis`.
- `agent.analyze` calls `client.messages.parse(output_format=GapAnalysis)`. A reply is rejected if Pydantic
  validation fails (the API schema can't express min/max limits, so Pydantic enforces them) or `check_rules`
  finds problems (duplicate skills, a "knows" skill left as a gap, a "lacks" skill kept as a strength). Up to
  `MAX_ATTEMPTS` tries, feeding the problems back; then `GapAnalysisFailed` → HTTP 502. LLM errors → 503.
- `gap_analyses` table (one row per user): current analysis, corrections, `profile_snapshot`, `confirmed`. Every
  run is also logged to `agent_outputs`. `stale` = snapshot differs from the current profile; any profile edit
  un-confirms the analysis and clears `Profile.inferred_skills` (set to the strengths on confirm).
- Analysis requires a confirmed profile (409 otherwise). It's a blocking request (20–40 s); the page shows
  rotating progress messages.

## Conventions
- Secrets live only in `backend/.env`; `frontend/.env` holds only `VITE_GOOGLE_CLIENT_ID`. Both are gitignored;
  keep the `.env.example` files in sync when adding variables.
- Chat endpoints stream Server-Sent Events; the stream opens its own DB session.
- No migrations yet: schema changes mean deleting `backend/career_strategist.db` in dev.
- Never disable SSL verification. Use truststore (already injected in `core/config.py`; for pip use
  `--use-feature=truststore`).

## Tests
- `cd backend && pytest`. `tests/conftest.py` sets test env vars, uses in-memory SQLite and replaces
  `core.auth.verify_google_token` with a fake (tokens `good:<sub>`), so tests need no network.
  Use the `anon` fixture (HTTPS TestClient so the Secure cookie is sent) and `login(client, sub)`.
- The LLM is faked in tests by monkeypatching the agent module's `get_client`. The gap-analysis fake validates
  replies with `GapAnalysis.model_validate`, so bad data raises `ValidationError` like the SDK does.
- New endpoints need a 401-without-login case in `tests/test_auth.py`.
