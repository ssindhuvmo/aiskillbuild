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
  - `agents/<name>/` — one module per agent with its own `prompt.md` (intake so far). `llm.py` — Anthropic client.
- `backend/config/domains.json` — supported domains (edit here, not in code).
- `frontend/src/` — `App.jsx` (auth gate, header, routes), `api.js` (all fetch calls), `pages/`, `components/`.

## Auth rules (Milestone 2)
- Google Identity Services on the frontend sends the ID token to `POST /api/auth/google`; the backend verifies it
  against `GOOGLE_CLIENT_ID`, upserts the `User` (primary key `user_id` = Google `sub`) and stores only that sub in
  a signed httpOnly session cookie (Starlette `SessionMiddleware`, `SESSION_SECRET`, SameSite=Lax, Secure).
- Every data endpoint takes `user: User = Depends(current_user)` and uses `user.user_id`. Never put a user ID in an
  API path, query or body. Only `/api/health` and `/api/auth/google|logout` are public.
- Frontend never stores identity itself; it calls `/api/auth/me` on load, and any 401 returns to the sign-in screen.

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
- The LLM is faked in tests by monkeypatching `agent.get_client`.
- New endpoints need a 401-without-login case in `tests/test_auth.py`.
