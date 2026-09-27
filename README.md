# AI Career Strategist

Helps tech professionals move into AI roles with a personalized 6-month roadmap. See `SPEC.md` for the full V1.

**Current status: Milestone 2** — React + FastAPI skeleton, Google sign-in with per-user sessions, and the
conversational intake that collects the five inputs and saves the profile to SQLite. Later steps (skill gaps,
resources, roadmap) are placeholder pages.

## Google sign-in setup (once)

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), create an
   **OAuth client ID** of type **Web application** (configure the OAuth consent screen first if asked).
2. Under **Authorized JavaScript origins** add `http://localhost:5173` and `http://localhost`.
   No redirect URI is needed.
3. Copy the client ID. It goes in both `backend/.env` (`GOOGLE_CLIENT_ID`) and `frontend/.env`
   (`VITE_GOOGLE_CLIENT_ID`).

## Backend (Python venv)

Requires Python 3.11+. From the project root:

```powershell
cd backend
python -m venv .venv                 # create the virtual environment (once)
.\.venv\Scripts\Activate.ps1         # activate  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env               # macOS/Linux: cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID and SESSION_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"   # prints a SESSION_SECRET value
uvicorn app.main:app --reload --port 8000
```

The backend refuses to start without `GOOGLE_CLIENT_ID` and `SESSION_SECRET`.

Run tests (venv active): `pytest`. Google token verification is mocked, so tests need no network.

The SQLite file `backend/career_strategist.db` is created on first start. Secrets are read only by the backend.
Milestone 2 changed the users table; if you have an older database, delete `career_strategist.db` and
restart (there are no migrations yet).

> **SSL certificate errors.** On machines behind a proxy with a custom CA, Python may fail with
> `CERTIFICATE_VERIFY_FAILED`. The backend uses [`truststore`](https://pypi.org/project/truststore/) to verify
> HTTPS against the operating-system certificate store (verification stays on). For pip itself use
> `pip install --use-feature=truststore -r requirements.txt`.

## Frontend

```powershell
cd frontend
copy .env.example .env   # set VITE_GOOGLE_CLIENT_ID (macOS/Linux: cp)
npm install
npm run dev              # http://localhost:5173 (proxies /api to http://127.0.0.1:8000)
```

Open the app at `http://localhost:5173` (not `127.0.0.1`) so it matches the authorized origin.

## Try it

1. Start both servers, open http://localhost:5173 and click **Sign in with Google**.
2. Chat through the five inputs (try an invalid answer like "50 hours/week" to see follow-ups).
3. Review the profile card, edit if needed, click **Confirm**.
4. Restart the servers and sign in with the same Google account — the chat and profile reload.
   A different Google account starts with an empty profile.
