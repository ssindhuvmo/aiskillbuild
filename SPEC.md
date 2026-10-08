I'm building "AI Career Strategist" — a web app that helps software engineers, data
analysts and other tech professionals move into AI roles. It understands the user's
background, goals and constraints, then produces a realistic, personalized 6-month
upskilling roadmap.

This is VERSION 1. Build only the scope below. Before writing any code, give me a
short plan (architecture, folder structure, data model, API endpoints, agent design,
React page and component layout) and wait for my approval.

## V1 user flow
0. SIGN IN WITH GOOGLE: The user signs in with their Google account before using
   the app. The header shows their name and picture with a "Sign out" option.
   Returning users who sign in again see their saved profile and progress. Each
   user can only see and change their own data.
1. INTAKE (conversational): The user chats with the app, which collects exactly
   these five inputs:
   1) Current role (e.g. Backend Engineer, Data Analyst, QA Engineer)
   2) Target role (e.g. ML Engineer, AI Engineer, Data Scientist, MLOps Engineer)
   3) AI experience (ai_experience), exactly one of: None (haven't worked with AI
      yet), Beginner (taken a course or tried some tools), Intermediate (built a
      small AI/ML project), Experienced (used AI/ML in real work). Asked simply
      ("Do you have any experience with AI?") with the four options as clickable
      buttons in the chat; a typed answer is mapped to one option and confirmed
   4) Current domain: the industry the user works in today (e.g. FinTech, EdTech,
      Healthcare, Retail, Real Estate, or "Other" with free text)
   5) Hours per week they can devote to learning (a number, validated as 1–40)
   A typed answer showing no prior AI knowledge ("nothing yet", "no") maps to None.
   The assistant asks a follow-up question only when an answer is missing, vague
   or invalid, then shows a summary of all five for the user to confirm or edit.
   LLM output never bypasses deterministic validation: invalid or missing values
   lead to a follow-up question, not a saved record. The chat renders assistant
   messages as Markdown (lightweight and safe, no raw HTML).
   No resume upload in V1.
2. PERSIST PROFILE: Save the confirmed profile to a database, linked to the signed-in
   Google user (the five inputs, and the skills inferred in step 3).
3. SKILL-GAP ANALYSIS: Use the LLM to infer the user's likely current skills from
   their current role, current domain and AI experience, and compare them to
   what the target role needs. Treat the user's domain experience as a strength to
   build on: identify the most relevant AI use cases in that industry (e.g. fraud
   detection and credit risk in FinTech, personalized learning in EdTech, clinical
   NLP and medical imaging in Healthcare, demand forecasting and recommendations
   in Retail, property valuation in Real Estate) and include domain-specific gaps
   such as relevant data types, regulations and compliance (e.g. HIPAA, PCI-DSS).
   Output structured JSON: inferred strengths (including domain knowledge), gaps
   (each with priority and estimated effort in hours), relevant domain AI use
   cases, and a short rationale. The plan covers at most 8 gaps, chosen by
   importance for the target role and domain, whose total effort roughly fits
   hours-per-week × 26; further gaps are kept and shown separately as "Later /
   optional". Clearly label inferred skills as assumptions and
   let the user correct them ("I already know SQL well", "I've never used Python")
   before moving on.
4. COURSE SEARCH AGENT: For each gap, find learning resources from two sources:
   a) a small curated knowledge base (seed JSON file of ~30–50 high-quality courses,
      papers and projects, tagged by skill, level, industry domain, format, cost,
      hours; include general AI resources plus some for each listed domain)
   b) live web search via the Anthropic web search tool
   Rank results by relevance to the gap, fit with the user's AI experience,
   applicability to the user's industry domain, and time cost. Default to a mix of
   free and paid resources and of courses, papers and hands-on projects. Every
   resource must have a real URL — never invent links.
   Built as a LangGraph graph with nodes for: retrieving from the knowledge base,
   live web search, merging and de-duplicating candidates, verifying URLs,
   ranking, and presenting the list.
5. CONVERSATIONAL REFINEMENT: Show the ranked list and let the user chat to change it
   ("remove this", "I prefer free ones", "add more hands-on projects", "I already know
   PyTorch"). The agent updates the list and explains its changes.
   Refinement is part of the same LangGraph graph as step 4: after presenting, the
   graph pauses for user input (LangGraph interrupt / human-in-the-loop),
   interprets the request, updates the list (re-searching only when needed),
   explains the changes and pauses again until the user approves the list. Graph
   state is persisted per signed-in user (LangGraph SQLite checkpointer or the
   existing database) so refinement resumes after sign-out and sign-in.
   Until the refinement chat is built (milestone 6), the Resources page has a simple
   approval step instead: the user unticks resources they don't want and clicks
   "Approve list". Both produce the same saved approved list per user, which is the
   scheduler's only input, so the scheduler does not change when refinement arrives.
6. SCHEDULER AGENT: Turn the approved resource list into a 6-month roadmap that respects
   the weekly hours: monthly themes, week-by-week tasks, milestones and a portfolio
   project per phase. Portfolio projects should solve a realistic problem from the
   user's industry domain using public datasets where possible, so the user can
   show domain + AI expertise together. Total planned hours must not exceed
   hours-per-week × weeks (26 weeks), and no week may exceed the weekly hours. The
   budget is enforced in plain Python on every LLM reply, not only in the prompt.
   Links in the roadmap always come from the approved list, never from the LLM.
7. ROADMAP VIEW: Show the roadmap in React as a clear timeline (collapsible months,
   week-by-week tasks with links, milestones highlighted) and save it to the user's
   profile. Allow export to Markdown as a file download.

## Out of scope for V1 (design so these can be added later, but do NOT build them)
- Resume upload and parsing (V2: will enrich the profile and skill-gap analysis, so
  keep the profile model and gap-analysis input easy to extend with resume data)
- Job Match Agent, Resume Update Agent
- Returning-user progress tracking and re-evaluation
- Sign-in methods other than Google, roles/admin accounts, payments, scheduling
  reminders

## Tech stack
- Frontend: React (JavaScript) with Vite, React Router for pages (Intake chat,
  Skill Gaps, Resources, Roadmap), a simple clean chat UI, and a step indicator
  showing where the user is in the flow. Use plain CSS or Tailwind; keep
  dependencies minimal
- Backend: Python, FastAPI, exposing a REST API the React app calls. Enable CORS
  for the Vite dev server. Stream chat responses (Server-Sent Events) for the
  intake and refinement chats so replies appear as they are generated
- Core logic: a separate Python package (e.g. core/) holding the agents, DB access
  and models. FastAPI routes only call into this package and contain no business
  logic
- LLM: Anthropic API via the official Python SDK, with structured JSON outputs
  validated by Pydantic. The model is configurable through ANTHROPIC_MODEL in
  backend/.env (default claude-sonnet-5; use claude-haiku-4-5-20251001 for
  cheaper development testing). All agents read the model from this one setting
- Orchestration: LangGraph for the Course Search Agent and conversational
  refinement (V1 user flow steps 4 and 5). The intake and gap agents stay as
  plain Python modules. LLM calls inside graph nodes go through core/llm.py so the
  model stays configurable via ANTHROPIC_MODEL. The graph lives in
  core/agents/course_search/ and FastAPI routes only invoke it
- Authentication: Google Sign-In using Google Identity Services on the frontend.
  The backend verifies the Google ID token with the google-auth library against
  GOOGLE_CLIENT_ID, creates or finds the user (Google "sub" as the stable user ID,
  plus email, name and picture), and starts a session with a secure httpOnly
  cookie signed with SESSION_SECRET. The user ID always comes from the session,
  never from the URL or request body
- Database: SQLite with SQLAlchemy (easy to move to Postgres later)
- Knowledge base: seed JSON + a simple retrieval layer behind an interface, so I can
  swap in a vector store / RAG later
- Config via backend/.env (ANTHROPIC_API_KEY, ANTHROPIC_MODEL, DATABASE_URL,
  FRONTEND_ORIGIN, GOOGLE_CLIENT_ID, SESSION_SECRET) and frontend/.env
  (VITE_GOOGLE_CLIENT_ID), each with a .env.example; the API key and session
  secret stay on the backend only and must never reach the frontend; never
  hard-code secrets

## Engineering requirements
- Project layout with separate frontend/ and backend/ folders
- Each agent (intake, gap analysis, course search, scheduler) is its own module with
  its own prompt file, clear inputs/outputs as Pydantic models
- Every API endpoint requires a signed-in user and only returns or changes that
  user's own data; user_id is not part of API paths
- Keep the list of supported domains in one config file so new industries can be
  added without code changes
- Store conversation state and every agent output in the DB so sessions can resume
- Handle LLM/JSON errors with retries on the backend, return clear error responses,
  and show friendly error messages and loading states in the React UI
- Unit tests (pytest) for the intake input validation, the scheduler's hour-budget
  logic and the ranking function, plus an intake flow test and auth tests
  (signed-out requests are rejected; users cannot access each other's data).
  Tests use a fake LLM client, mocked Google token verification and an in-memory
  SQLite database, so they need no API key or network
- Tests run the course search / refinement graph end to end with the fake LLM
  client and a fake search tool (no network), covering the pause/resume
  refinement loop and approval
- Python virtual environment at backend/.venv. The README documents creating it
  and running the app on Windows and macOS/Linux, including the pip truststore
  workaround for machines with SSL certificate errors
  (pip install --use-feature=truststore -r requirements.txt). If backend HTTPS
  calls (e.g. to Google) hit the same SSL errors, use the Windows certificate
  store via truststore; never disable certificate verification
- Git at the project root with a .gitignore excluding .env files (backend and
  frontend), *.db / *.sqlite*,
  node_modules/, .venv/, __pycache__/ and dist/. Commit after each working
  milestone
- A README with setup and run steps for both backend and frontend, and a CLAUDE.md
  describing the architecture and conventions for future sessions
- requirements.txt for the backend, package.json for the frontend, and a short demo
  walkthrough with two sample user profiles (e.g. "Backend Engineer in FinTech →
  AI Engineer, Beginner, 8 hrs/week" and "Data Analyst in Healthcare → Data
  Scientist, None, 5 hrs/week")

## Milestones
Build one milestone at a time and stop after each so it can be tested.
1. React + FastAPI skeleton and conversational intake (flow steps 1–2) — done
2. Google sign-in: sessions, per-user data, sign-in/sign-out UI (flow step 0) — done
3. Skill-gap analysis: gap agent with validated JSON and retries, Skill Gaps page,
   user corrections, saved results (flow step 3) — done
4. Knowledge base + ranking: seed JSON knowledge base, retrieval layer and ranking
   function, Resources page with the ranked list (flow step 4a). Retrieval and
   ranking stay plain, reusable Python functions so milestone 6 can wrap them as
   graph nodes — done
5. Scheduler agent, roadmap view, saving and Markdown export (flow steps 6–7),
   with a simple approval step on the Resources page that saves the approved list — done
6. Live web search + conversational refinement (flow steps 4b–5). Introduces
   LangGraph: the course search / refinement graph with URL verification,
   pause/resume refinement and approval. Approval writes the same approved list
   the scheduler already reads — built, in testing

## Definition of done
I can start the backend (uvicorn) and the frontend (npm run dev), open the app in
my browser, sign in with Google, enter my current role, target role, AI
experience, current domain and weekly hours through the chat, confirm the summary, review and correct the
inferred skill gaps, edit the suggested resources by chatting, and get a saved
6-month roadmap with working links, domain-relevant portfolio projects, and a plan
that fits my weekly hours. Restarting the app and signing in with the same Google
account reloads my saved profile and roadmap, and a different Google account
cannot see them.