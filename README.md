# AI Career Strategist

Helps tech professionals move into AI roles with a personalized 6-month roadmap. See `SPEC.md` for the full
specification (v2).

**Current status: Milestone 9 of 14** (see Milestones in `SPEC.md`):
1. React + FastAPI skeleton and conversational intake — done
2. Google sign-in with per-user sessions — done
3. Skill-gap analysis with user corrections — done
4. Knowledge base + ranked resources — done
5. Resource approval, scheduler agent and roadmap with Markdown export — done
6. Live web search + refinement chat (LangGraph) — done
7. Design system and app shell (dark theme, sidebar, Home page, restyled pages) — done
8. Expanded intake, resume upload and Career Profile (capability assessment, preferences, constraints,
   evidence-based skill analysis with a gap chart, Alembic migrations) — built, in testing
9. Resource sources and preferences (YouTube source, preference- and budget-aware ranking, filters,
   Save / Start / Complete) — built, in testing

The look follows `docs/mockups/`; parts of the mockups that belong to later milestones (task checkboxes and
dates, PDF export, View Demo) are not built yet. Dashboard,
Progress Review, Job Match and Resume Optimizer are placeholders in the sidebar.

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
# edit .env: set ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID and SESSION_SECRET (YOUTUBE_API_KEY is optional)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # prints a SESSION_SECRET value
uvicorn app.main:app --reload --port 8000
```

The backend refuses to start without `GOOGLE_CLIENT_ID` and `SESSION_SECRET`.

Run tests (venv active): `pytest`. Google token verification is mocked, so tests need no network.

The SQLite file `backend/career_strategist.db` is created on first start. Secrets are read only by the backend.

**Migrations (Alembic, from milestone 8).** The backend runs `alembic upgrade head` itself on start, so an
existing database is upgraded in place and keeps its data. A database made before milestone 8 (tables but no
`alembic_version`) is first stamped at the baseline, then upgraded: the old AI-experience answer becomes the
Machine Learning and AI / LLMs ratings, and profiles that now miss required answers are un-confirmed. To run
migrations by hand (venv active, in `backend/`): `alembic upgrade head`. For a schema change, edit
`core/models.py`, then `alembic revision --autogenerate -m "what changed"`, review the generated file in
`migrations/versions/` and restart.

**Backup and rollback.** Before applying a pending migration to the SQLite file, the backend copies it to
`backend/career_strategist.backup.db` (the log says so). An existing backup is never overwritten, so it
keeps the copy made before the first migration. To roll back: stop the backend, copy
`career_strategist.backup.db` over `career_strategist.db`, and start the previous code version. Delete the
backup when you no longer need it, so the next migration makes a fresh one.

**Uploads.** Resumes are stored under `backend/uploads/<user id>/` (`UPLOAD_DIR` in `.env`; gitignored) and
are never served back to the browser. **Start over** deletes the user's folder.

The course search graph keeps each user's paused refinement chat in a second SQLite file,
`backend/graph_checkpoints.db` (`CHECKPOINT_DB` in `.env`), also created on first use. A resource list built
before milestone 6 has no chat yet, so the Resources page asks you to rebuild it once.

**Full dev reset:** stop the backend and delete `backend/career_strategist.db`,
`backend/graph_checkpoints.db` and the `backend/uploads/` folder, then restart. Deleting only one leaves them out of step: lists without a chat
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

**YouTube (optional).** Resources include full courses and playlists from YouTube when `YOUTUBE_API_KEY` is set
in `backend/.env`: in Google Cloud Console enable **YouTube Data API v3** and create an API key (restrict it to
that API). Without a key the list is built without YouTube and the Resources page says so. Each skill gap costs
about 100–110 units of the free 10,000-unit daily quota, and results are shared across users for 14 days, so a
rebuilt list usually costs nothing. The log line `YouTube search run: N of M gaps searched, C from cache,
U quota units` shows what a run used. Trusted channels (they skip the minimum-views check and rank higher)
are in `backend/data/youtube_channels.json`; after editing it, check the ids against the API (1 unit):

```powershell
python scripts/check_youtube_channels.py     # from backend/, venv active; uses the real YouTube API
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
2. Chat through the eight questions ("Question N of 8" above the chat): career goal (or **Help me choose**
   for 2–3 suggested roles after your background), resume, current role / experience / industry, weekly
   hours, the capability assessment, learning preferences, budget and constraints, anything else. The steps
   with options show buttons under the chat; you can also type. Try an invalid answer like "50 hours/week".
   - **With a resume:** upload a PDF or DOCX (up to 5 MB). Parsing takes 10–20 seconds, then a review screen
     shows the skills, roles, education, certifications and achievements it read. Anything the AI listed
     that isn't in your resume's text is left out and named at the top. Fix, add or remove items and click
     **Save**: your current role, years of experience (calculated from the role dates) and industry are
     filled in and marked *· from resume*, and the chat asks you to confirm them.
   - **Without a resume:** click **Skip**; the chat asks for the same details.
3. Review the **Career Profile** card, edit any field (including ratings, preferences and constraints) or
   **Review again** for the resume, then click **Confirm**.
4. Click **Continue to Skill Analysis**. The analysis starts automatically and takes 20–40 seconds.
5. Review existing skills (grouped *From your resume*, *You said* and *Assumed*; **Why these skills** shows
   the evidence), missing skills, the gap chart (current level as a bar, target as a marker, on the same
   None → Experienced scale as your ratings, plus Expert for targets) and domain AI use cases. Correct anything with the **×** on a skill
   ("I don't have this"), **I already know this** on a gap or a free-text note, then click
   **Update analysis**. The plan covers at most 8 gaps that fit your hours (weekly hours × 26); the rest are
   listed under **Later / optional**, where **Add to my plan** swaps one in on the next update.
6. Click **Confirm skills**. You go to **Resources**, where the list is built right away (about 30–90 seconds:
   curated library, live web search, link checks, ranking).
7. Review the resources for each gap, highest priority first: up to four each, mixing courses, videos,
   articles and projects and free and paid, with a "Why this" line. They come from the curated library, the
   web (**Web** tag) and YouTube (**YouTube** tag, with views and likes), and rank higher when they match how
   you like to learn (intake preferences). With a "free only" budget, paid resources never appear. Use the
   **Filters** (Cost, Level, Type) to narrow the list: each click rebuilds it at once (no AI call), and what
   you see is what gets approved. **Save**, **Start** and **Complete** on a card record your progress; they
   don't change the list, and saved or started resources that leave the list are shown below it.
   **Search again** (top right) builds a fresh list, e.g. after adding a YouTube key; it replaces the list,
   filters and chat, and keeps your saved and started resources.
8. Click **Remove** on a card to drop a single resource at once (no AI call). For anything else use the
   **Refine your list** chat: "I prefer free ones", "add more hands-on projects", "I already know PyTorch",
   "put the Coursera one back". The list updates and the reply explains what changed. Sign out
   and back in: the list and the chat are still there. When you're happy, click **Approve list** (or say so in
   the chat). You go to **Roadmap**, which is built right away (the plan in seconds, its text shortly after).
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

The weeks, tasks and hours of the roadmap are planned in Python and appear within a second or two; each phase's
name, milestones, practice wording and portfolio project are then written by the AI and fill in as they arrive.
If the AI's text for a phase fails (no API key, an API error, or a reply that fails the checks twice), that
phase keeps plain default text and the page says so; the backend log has the reason
(`Scheduler narrative for phase N ...`). Each run logs its timing at INFO: `Roadmap generated: plan placed in
X s; phase N ai|default T s, ...; total T s`.

Sample profiles: "Backend Engineer in FinTech → AI Engineer, Beginner, 8 hrs/week" and
"Data Analyst in Healthcare → Data Scientist, None, 5 hrs/week".
