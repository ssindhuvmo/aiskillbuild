I'm building "AI Career Strategist" — a web app that helps software engineers, data
analysts and other tech professionals move into AI roles. It understands the user's
background, goals and constraints, then produces a realistic, personalized 6-month
upskilling roadmap.

This is VERSION 1. Build only the scope below. Before writing any code, give me a
short plan (architecture, folder structure, data model, API endpoints, agent design,
React page and component layout) and wait for my approval.

## V1 user flow
1. INTAKE (conversational): The user chats with the app, which collects exactly
   these five inputs:
   1) Current role (e.g. Backend Engineer, Data Analyst, QA Engineer)
   2) Target role (e.g. ML Engineer, AI Engineer, Data Scientist, MLOps Engineer)
   3) Current AI knowledge: a level (None / Beginner / Intermediate / Advanced)
      plus a free-text description of what they already know (e.g. "did Andrew
      Ng's ML course, used the OpenAI API in a side project")
   4) Current domain: the industry the user works in today (e.g. FinTech, EdTech,
      Healthcare, Retail, Real Estate, or "Other" with free text)
   5) Hours per week they can devote to learning (a number, validated as 1–40)
   The assistant asks a follow-up question only when an answer is missing, vague
   or invalid, then shows a summary of all five for the user to confirm or edit.
   No resume upload in V1.
2. PERSIST PROFILE: Save the confirmed profile to a database (user identifier plus
   the five inputs, and the skills inferred in step 3).
3. SKILL-GAP ANALYSIS: Use the LLM to infer the user's likely current skills from
   their current role, current domain and stated AI knowledge, and compare them to
   what the target role needs. Treat the user's domain experience as a strength to
   build on: identify the most relevant AI use cases in that industry (e.g. fraud
   detection and credit risk in FinTech, personalized learning in EdTech, clinical
   NLP and medical imaging in Healthcare, demand forecasting and recommendations
   in Retail, property valuation in Real Estate) and include domain-specific gaps
   such as relevant data types, regulations and compliance (e.g. HIPAA, PCI-DSS).
   Output structured JSON: inferred strengths (including domain knowledge), gaps
   (each with priority and estimated effort in hours), relevant domain AI use
   cases, and a short rationale. Clearly label inferred skills as assumptions and
   let the user correct them ("I already know SQL well", "I've never used Python")
   before moving on.
4. COURSE SEARCH AGENT: For each gap, find learning resources from two sources:
   a) a small curated knowledge base (seed JSON file of ~30–50 high-quality courses,
      papers and projects, tagged by skill, level, industry domain, format, cost,
      hours; include general AI resources plus some for each listed domain)
   b) live web search via the Anthropic web search tool
   Rank results by relevance to the gap, fit with the user's AI knowledge level,
   applicability to the user's industry domain, and time cost. Default to a mix of
   free and paid resources and of courses, papers and hands-on projects. Every
   resource must have a real URL — never invent links.
5. CONVERSATIONAL REFINEMENT: Show the ranked list and let the user chat to change it
   ("remove this", "I prefer free ones", "add more hands-on projects", "I already know
   PyTorch"). The agent updates the list and explains its changes.
6. SCHEDULER AGENT: Turn the approved resource list into a 6-month roadmap that respects
   the weekly hours: monthly themes, week-by-week tasks, milestones and a portfolio
   project per phase. Portfolio projects should solve a realistic problem from the
   user's industry domain using public datasets where possible, so the user can
   show domain + AI expertise together. Total planned hours must not exceed
   hours-per-week × weeks.
7. ROADMAP VIEW: Show the roadmap in React as a clear timeline (collapsible months,
   week-by-week tasks with links, milestones highlighted) and save it to the user's
   profile. Allow export to Markdown as a file download.

## Out of scope for V1 (design so these can be added later, but do NOT build them)
- Resume upload and parsing (V2: will enrich the profile and skill-gap analysis, so
  keep the profile model and gap-analysis input easy to extend with resume data)
- Job Match Agent, Resume Update Agent
- Returning-user progress tracking and re-evaluation
- Authentication beyond a simple user identifier, payments, scheduling reminders

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
- LLM: Anthropic API via the official Python SDK (model: claude-sonnet-5), with
  structured JSON outputs validated by Pydantic
- Database: SQLite with SQLAlchemy (easy to move to Postgres later)
- Knowledge base: seed JSON + a simple retrieval layer behind an interface, so I can
  swap in a vector store / RAG later
- Config via .env (ANTHROPIC_API_KEY on the backend only; the API key must never
  reach the frontend); never hard-code secrets

## Engineering requirements
- Project layout with separate frontend/ and backend/ folders
- Each agent (intake, gap analysis, course search, scheduler) is its own module with
  its own prompt file, clear inputs/outputs as Pydantic models
- Keep the list of supported domains in one config file so new industries can be
  added without code changes
- Store conversation state and every agent output in the DB so sessions can resume
- Handle LLM/JSON errors with retries on the backend, return clear error responses,
  and show friendly error messages and loading states in the React UI
- Unit tests (pytest) for the intake input validation, the scheduler's hour-budget
  logic and the ranking function
- A README with setup and run steps for both backend and frontend, and a CLAUDE.md
  describing the architecture and conventions for future sessions
- requirements.txt for the backend, package.json for the frontend, and a short demo
  walkthrough with two sample user profiles (e.g. "Backend Engineer in FinTech →
  AI Engineer, Beginner, 8 hrs/week" and "Data Analyst in Healthcare → Data
  Scientist, None, 5 hrs/week")

## Definition of done
I can start the backend (uvicorn) and the frontend (npm run dev), open the app in
my browser, enter my current role, target role, AI knowledge, current domain and
weekly hours through the chat, confirm the summary, review and correct the
inferred skill gaps, edit the suggested resources by chatting, and get a saved
6-month roadmap with working links, domain-relevant portfolio projects, and a plan
that fits my weekly hours. Restarting the app and entering the same user identifier
reloads my saved profile and roadmap.