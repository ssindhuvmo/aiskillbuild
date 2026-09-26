# AI Career Strategist

Helps tech professionals move into AI roles with a personalized 6-month roadmap. See `SPEC.md` for the full V1.

**Current status: Milestone 1** — React + FastAPI skeleton and the conversational intake that collects the five
inputs and saves the profile to SQLite. Later steps (skill gaps, resources, roadmap) are placeholder pages.

## Backend (Python venv)

Requires Python 3.11+. From the project root:

```powershell
cd backend
python -m venv .venv                 # create the virtual environment (once)
.\.venv\Scripts\Activate.ps1         # activate  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env               # macOS/Linux: cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

Run tests (venv active): `pytest`

The SQLite file `backend/career_strategist.db` is created on first start. The API key is read only by the backend.

> If `pip install` fails with `CERTIFICATE_VERIFY_FAILED` (corporate proxy / custom CA), install
> [`truststore`](https://pypi.org/project/truststore/) and use `pip install --use-feature=truststore -r requirements.txt`.

## Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to http://127.0.0.1:8000)
```

## Try it

1. Start both servers, open http://localhost:5173, enter a user identifier.
2. Chat through the five inputs (try an invalid answer like "50 hours/week" to see follow-ups).
3. Review the profile card, edit if needed, click **Confirm**.
4. Restart the servers and enter the same identifier — the chat and profile reload.
