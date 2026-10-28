# AI Career Strategist

Helps tech professionals move into AI roles with a personalized 6-month roadmap. See `SPEC.md` for the full
specification (v2).

**Current status: Milestone 7 of 14** (see Milestones in `SPEC.md`):
1. React + FastAPI skeleton and conversational intake — done
2. Google sign-in with per-user sessions — done
3. Skill-gap analysis with user corrections — done
4. Knowledge base + ranked resources — done
5. Resource approval, scheduler agent and roadmap with Markdown export — done
6. Live web search + refinement chat (LangGraph) — done
7. Design system and app shell (dark theme, sidebar, Home page, restyled pages) — built, in testing

Milestone 7 is frontend only. The look follows `docs/mockups/`; parts of the mockups that belong to later
milestones (resume upload, filters, Save / Start / Complete, task checkboxes and dates, PDF export, View Demo)
are not built yet. Dashboard, Progress Review, Job Match and Resume Optimizer are placeholders in the sidebar.

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
There are no migrations yet: new tables are created on start, but if a milestone changes an existing table,
delete `career_strategist.db` and restart. (Milestones 4 and 5 only add tables — `resource_lists`,
`approved_lists`, `roadmaps` — so an existing milestone 3 database keeps working. Milestone 6 changes no
tables.)

The course search graph keeps each user's paused refinement chat in a second SQLite file,
`backend/graph_checkpoints.db` (`CHECKPOINT_DB` in `.env`), also created on first use. A resource list built
before milestone 6 has no chat yet, so the Resources page asks you to rebuild it once.

**Full dev reset:** stop the backend and delete both `backend/career_strategist.db` and
`backend/graph_checkpoints.db`, then restart. Deleting only one leaves them out of step: lists without a chat
(the page asks you to rebuild), or chats for users who no longer have a list.

### Live web search

The Resources step searches the web with the Anthropic web search tool. Enable web search for your organization
in the [Claude Console](https://platform.claude.com) (organization settings) before testing. Each search is billed
on top of tokens. To keep the cost down, the first build only searches the web for gaps where the curated
library has fewer than three good matches, with at most two searches per gap; later searches happen only when
you ask for more in the chat. The backend log shows the cost of every run, e.g.
`INFO: core.agents.course_search.graph: Web search run: 2 of 6 gaps searched (...), 4 web searches`. If web
search is unavailable the list is still built from the curated library, with a notice at the top of the page.
Every web result's URL must appear in the search results it came from and is then checked over HTTP; links that
fail are dropped (sites that merely block automated checks are kept).

> **SSL certificate errors.** On machines behind a proxy with a custom CA, Python may fail with
> `CERTIFICATE_VERIFY_FAILED`. The backend uses [`truststore`](https://pypi.org/project/truststore/) to verify
> HTTPS against the operating-system certificate store (verification stays on). For pip itself use
> `pip install --use-feature=truststore -r requirements.txt`.

### Knowledge base

The curated resources live in `backend/data/knowledge_base.json` (resources plus the skill-tag vocabulary used to
match gaps). Restart the backend after editing it. To check that every link still works (needs the network):

```powershell
python scripts/check_kb_links.py     # from backend/, venv active
```

Sites that refuse automated requests (e.g. hhs.gov) are reported as "blocked"; open those in a browser.

Web resources that users approve are kept as candidates for the knowledge base. To list the ones not in it yet,
most approved first (add `--json` for entries ready to paste into `resources`, then review them and check links):

```powershell
python scripts/list_web_candidates.py     # from backend/, venv active
```

## Frontend

```powershell
cd frontend
copy .env.example .env   # set VITE_GOOGLE_CLIENT_ID (macOS/Linux: cp)
npm install
npm run dev              # http://localhost:5173 (proxies /api to http://127.0.0.1:8000)
```

Open the app at `http://localhost:5173` (not `127.0.0.1`) so it matches the authorized origin.

## Try it

1. Start both servers and open http://localhost:5173. On the Home page click **Start Assessment**, then
   **Sign in with Google**; you land on **Intake**. The sidebar (a **Menu** button on a phone) moves between
   pages and shows your profile, **Start over** and **Sign out**.
2. Chat through the five inputs (try an invalid answer like "50 hours/week" to see follow-ups).
3. Review the profile summary, edit if needed, click **Confirm**.
4. Click **Continue to Skill Analysis**. The analysis starts automatically and takes 20–40 seconds.
5. Review existing skills (grouped *You said* and *Assumed*; **Why these skills** shows the reasoning),
   missing skills, the gap table and domain AI use cases. Correct anything with the **×** on a skill
   ("I don't have this"), **I already know this** on a gap or a free-text note, then click
   **Update analysis**. The plan covers at most 8 gaps that fit your hours (weekly hours × 26); the rest are
   listed under **Later / optional**, where **Add to my plan** swaps one in on the next update.
6. Click **Confirm skills**. You go to **Resources**, where the list is built right away (about 30–90 seconds:
   curated library, live web search, link checks, ranking).
7. Review the resources for each gap, highest priority first: up to four each, mixing courses, papers and
   projects and free and paid, with a "Why this" line. Results found on the web carry a **web** tag.
8. Click **Remove** on a card to drop a single resource at once (no AI call). For anything else use the
   **Refine your list** chat: "I prefer free ones", "add more hands-on projects", "I already know PyTorch",
   "put the Coursera one back". The list updates and the reply explains what changed. Sign out
   and back in: the list and the chat are still there. When you're happy, click **Approve list** (or say so in
   the chat). You go to **Roadmap**, which is built right away (about 30–90 seconds).
9. Review the roadmap: three phases, six collapsible months with a theme and a highlighted milestone, weekly
   tasks with links to your approved resources, and a portfolio project per phase from your industry. The
   summary shows planned hours against your budget (weekly hours × 26 weeks); no week goes over your weekly
   hours. Approved resources that did not fit are listed at the bottom. Click **Download Plan** to export it
   as Markdown.
10. Restart the servers and sign in with the same Google account — the chat, profile, skill analysis,
    resources, approval and roadmap reload. A different Google account starts empty. Editing the profile marks
    everything after it out of date: re-confirm the skills, **Rebuild the list**, approve it again, then
    **Regenerate Roadmap**. Refining the list after approval asks you to approve again, and the new approval
    marks the roadmap out of date. **Start over** also clears the refinement chat.

If roadmap generation fails, the backend log says why: each rejected attempt is logged with the rule it broke,
and a reply cut off by the output limit is logged as `stop_reason=max_tokens` (see `MAX_TOKENS` in
`backend/core/agents/scheduler/agent.py`).

Sample profiles: "Backend Engineer in FinTech → AI Engineer, Beginner, 8 hrs/week" and
"Data Analyst in Healthcare → Data Scientist, None, 5 hrs/week".
