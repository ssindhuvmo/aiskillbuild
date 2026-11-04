# AI Career Strategist — Specification (v2)

AI Career Strategist helps technology professionals move into AI roles. It builds a
persistent Career Profile from the user's goal, resume and constraints, finds the
gaps between where they are and where they want to be, recommends resources and
portfolio projects, plans a realistic six-month roadmap, tracks progress, matches
jobs and tailors the resume to a chosen job.

This version replaces the V1 spec. It is derived from two source documents, which
live in the repository:

- `docs/AI_Career_Strategist_BRD_Iteration2.docx` — business requirements (BR-01 to
  BR-27). Requirement IDs below refer to it.
- `docs/Career_Strategist_Product_Requirement_Document.docx` — pages, components and
  visual design.

Build one milestone at a time (see "Milestones"), plan before coding, and stop after
each milestone so it can be tested.

## Decisions that override the source documents

Where this spec and the source documents disagree, this spec wins.

1. **React, not Streamlit.** The PRD describes a Streamlit UI. The app is React +
   FastAPI and stays that way; the PRD's pages, components and visual design are
   applied to React.
2. **Real AI, not mocked data.** The PRD asks for mocked outputs. The app uses real
   agents. Mock JSON is only used in tests and for an optional demo account.
3. **Job matching and resume tailoring are in scope** (BR-26, BR-27, both Must).
   The BRD's statements that defer them are superseded.
4. **Google sign-in stays** (BR-08). LinkedIn login and LinkedIn / GitHub profile
   import are out of scope.
5. **The roadmap is always six months (26 weeks).** The PRD's "Expected Timeline"
   answer is stored as context and does not change the roadmap length.

## What stays from V1

Milestones 1–7 are built. These parts are kept and extended, not rewritten:

- Thin FastAPI routes; all logic in `backend/core/`; all database access in
  `core/repository.py`; all LLM calls through `core/llm.py` with the model set by
  `ANTHROPIC_MODEL`.
- Google sign-in with a signed session cookie. The user ID always comes from the
  session, never from a path, query or body.
- "The AI talks, code decides": every LLM output is validated by Pydantic and plain
  Python rules before it is saved, with retries that feed the problems back.
- The gap-analysis agent, the ranking function, the `Retriever` interface, the
  LangGraph course-search / refinement graph, the approved list as the scheduler's
  only input, the scheduler and its Python hour budget.
- Snapshots and "out of date" detection between steps.
- Tests with a fake LLM, fake search, mocked Google verification and in-memory
  SQLite, needing no network or API key.

## Visual design (PRD section 4)

One design system, defined once as CSS variables and reused by every page.

| Token | Value |
|---|---|
| Background | `#0B1120` |
| Surface / secondary | `#1E293B` |
| Primary | `#00B5FF` |
| Accent | `#38BDF8` |
| Text | White; light gray for secondary text |

- Dark theme, rounded cards, minimal, enterprise-grade, clean typography.
- Responsive: usable on a phone; the sidebar collapses to a menu.
- Accessible: keyboard navigation, readable contrast, labels on every control.
- Initial load under 2 seconds and page navigation under 1 second on a dev machine
  (long AI steps show progress messages instead).

### Navigation

A left sidebar with: Home, Intake, Dashboard, Skill Analysis, Learning Roadmap,
Resources, Progress Review, Job Match, Resume Optimizer. Pages that need an earlier
step show a short note with a link to that step. A persistent profile summary sits
in the sidebar: name, current role, target role.

### Reusable components

Profile Card, Metric Card, Skill Badge (color-coded), Timeline, Resource Card, Job
Card, Resume Comparison Viewer, Chat, Progress (loading messages).

## Pages and requirements

### 1. Home
- Hero: title "AI Career Strategist", subtitle "From 'I want to move into AI' to a
  realistic 6-month roadmap", buttons **Start Assessment** (sign in, then Intake)
  and **View Demo** (a read-only sample profile).
- Four benefit cards: Personalized Career Strategy, Skill Gap Analysis, AI Learning
  Roadmaps, Job Matching.
- Footer: About, Contact, Privacy.

### 2. Intake (BR-01 to BR-07, BR-09)
Chat-style conversation in the main area, profile summary on the right, a progress
bar for question progress. Name and email come from Google sign-in. The chat
collects:

| Field | Requirement | Notes |
|---|---|---|
| Career goal | BR-01, Must | A target AI role, or "help me choose"; then the app suggests 2–3 suitable roles with reasons and the user picks one |
| Resume | BR-02, Must to offer | Upload PDF or DOCX. Optional for the user: if skipped, the chat asks for the same information (BR-09) |
| Current role, years of experience, industry domain | PRD | Pre-filled from the resume when one is uploaded; the user confirms |
| Weekly learning hours | BR-03, Must | Whole number 1–40 |
| Capability assessment | BR-04, Must | Self-rating None / Beginner / Intermediate / Experienced for each of: Python, Data and SQL, Machine Learning, AI / LLMs, Cloud. Shown as clickable options. Replaces the single `ai_experience` field; the overall level used by ranking is derived from the Machine Learning and AI / LLMs ratings |
| Learning preferences | BR-05, Must | Any of: free courses, paid courses, YouTube / video, articles, books, hands-on projects, certifications. Sensible defaults if skipped |
| Constraints | BR-06, Should | Optional: budget (free only, or a monthly amount), weekends only, must stay in current job, remote only, other |
| Additional context | BR-07, Should | Optional free text: why AI, expected timeline, side projects, aspirations |

The existing rules still apply: one question at a time, follow-ups only when an
answer is missing or invalid, deterministic validation before saving, a summary to
confirm or edit.

**Resume handling.** Text is extracted in Python (PDF and DOCX), then one
structured-output LLM call returns skills, roles, education, certifications and
achievements, validated by Pydantic. The user reviews and corrects what was
extracted before it is saved. The original file is stored per user and never sent
to the frontend of another user. Limit: 5 MB, PDF or DOCX only.

### 3. Career Profile (BR-10 to BR-12)
One persistent profile per user combining stated inputs and resume data: career
goal, professional background, skills and transferable skills, capability levels,
learning commitment, learning preferences, constraints, additional context, chosen
career pathway, progress and previous recommendations. It is retrieved on every
visit and editable at any time; edits mark later steps out of date.

### 4. Dashboard
- Metric cards: Readiness Score, Skill Coverage, Roadmap Completion, Jobs Applied
  (jobs the user marked as applied; there is no auto-apply).
- Career summary card: current role, target role, estimated transition time,
  current status.
- Charts: skill distribution (radar), progress trend (line), milestone completion
  (progress bar).
- Readiness Score, Skill Coverage and Roadmap Completion are calculated in plain
  Python from saved data with a documented formula, never by the LLM.

### 5. Skill Analysis (BR-13 to BR-16)
- Existing skills as tags; missing skills as warning tags.
- Skill gap chart: horizontal bars of current level against target level per skill.
- AI summary card: a short explanation of how existing experience and transferable
  skills support the transition (BR-15).
- Gaps are prioritized and sequenced (BR-14, BR-16). At most 8 gaps go in the plan,
  sized to fit weekly hours × 26; the rest are "Later / optional".
- The analysis now uses the resume data and the capability assessment, so skills
  are evidence-based where possible. Each strength is marked "From your resume",
  "You said" or "Assumed". User corrections continue to work.
- Editing the gaps directly. Each button takes effect at once, without a new
  analysis, and un-confirms the skills:
  - A gap in the plan: "I already know this" (it becomes a "You said" strength),
    "Move to later" (it goes to "Later / optional") and "Not needed".
  - A "Later / optional" gap: "Add to my plan" and "Not needed".
  - "Not needed" removes the skill completely: it is neither a strength nor a gap.
    Removed skills sit in a collapsed "Removed" list, each with Restore, which puts
    the gap back where it was.
  - Every button is saved as a correction (`knows`, `not_needed`, `later`, `plan`),
    so a re-analysis keeps the user's choices. In particular it never suggests a
    "not needed" skill again; the rule check rejects and retries an analysis that
    does.
  - Adding a gap (or restoring a plan gap) that would go over the hour budget or the
    8-gap limit does not fail. The plan stays as it is and the page says by how
    much, and suggests which gaps to move to later (lowest priority first, never a
    gap the user added unless nothing else is enough). One click accepts the swap.
    A gap that alone needs more than the whole budget is explained instead (raise
    the weekly hours, or keep it for later).
  - Removing an essential (high-priority) gap shows a one-line note on why it
    matters for the target role, here and in the "Removed" list. The user's choice
    is kept.
- Domain use cases and domain-specific gaps (e.g. fraud detection in FinTech,
  HIPAA in Healthcare) are kept from V1.

### 6. Resources (BR-17, BR-20, BR-21)
Sources, all behind the existing `Retriever` / `WebSearcher` interfaces:

1. The curated knowledge base (`backend/data/knowledge_base.json`).
2. **YouTube**, through the YouTube Data API (`YOUTUBE_API_KEY`): full courses and
   playlists per skill, plus a maintained list of trusted channels.
3. Live web search (Anthropic web search tool), which is also how Udemy, Coursera
   and similar catalogs are reached. They have no open API available to this
   project, so they are never called directly.

Selection is two-stage (BR-20): search broadly for candidates, then vet and rank.
Ranking keeps the existing weights and adds: match to the user's learning
preferences, budget (paid items are dropped when the budget is "free only"), and
quality signals where the source provides them (rating, views or enrolment).
Every link is real and verified; the LLM never writes URLs.

Page:
- Filters: Free / Paid; Beginner / Intermediate / Advanced; type (Course, Video,
  Article, GitHub Repository, Book, Project).
- Resource card: title, provider, duration, rating (when known), difficulty, "why
  this", and buttons **Save**, **Start**, **Complete** (self-reported, BR-21).
- The refinement chat and **Approve list** stay as built in milestone 6.

### 7. Learning Roadmap (BR-18, BR-19)
- Six months, three phases, weekly tasks, a portfolio project per phase from the
  user's industry using a named public dataset (BR-18).
- Each milestone and task has status, priority, due date and a completion checkbox.
  Due dates come from a start date the user sets.
- "Immediate next steps": the first three things to do this week.
- The plan uses the hours the resources need plus proportionate practice and
  project time; it does not pad to fill the budget. The summary shows learn,
  practice, project, planned and free hours.
- Actions: Download Plan (Markdown), Export PDF, Regenerate Roadmap.
- Budget rules stay enforced in Python: no week over the weekly hours, total within
  weekly hours × 26.
- Python places every task (order, weeks, hours, practice and project time); the LLM
  only writes each phase's text (one call per phase, in parallel, streamed to the
  page). If a phase's text fails, it keeps plain default text, so a roadmap is
  always produced.

### 8. AI Career Transition Report (BRD section 8.4)
The primary output: one document assembled from saved data, with these sections in
order: Career Goal; Current Career Profile; Career Fit Assessment; Transferable
Skills; Capability Gap Analysis; Recommended Career Strategy; Prioritized Learning
Plan; Recommended Learning Resources (with links); Six-Month Career Transition
Roadmap; Recommended Portfolio Projects; Immediate Next Steps.

Only Career Fit Assessment and Recommended Career Strategy need new LLM text; the
rest is assembled in Python from what is already saved. Viewable in the app and
downloadable as PDF and Markdown.

### 9. Progress Review (BR-22 to BR-25)
For returning users:
- Checklist of skills completed, table of courses finished, a confidence slider
  per skill, a notes box.
- **Update Progress** saves it to the profile. **Recalculate Readiness Score**
  refreshes the dashboard.
- **Refresh my plan** reassesses the gaps using the progress (BR-24) and offers an
  updated roadmap and next steps (BR-25). Completed work is kept; only the
  remaining weeks are replanned.
- Completion is self-reported; nothing is verified with third parties.

### 10. Job Match (BR-26)
- Sources sit behind a `JobSource` interface. The first source is live web search
  limited to a short allowlist of job sites, set in config; a jobs API can be added
  later without changing the page. No scraping of LinkedIn and no logged-in
  browsing.
- Every job must have a real, verified posting URL, using the same checks as
  resources.
- Match Score is calculated in Python from the overlap between the job's required
  skills and the user's current skills (profile plus completed progress). The LLM
  extracts required skills from the posting and writes the match explanation.
- Filters: Remote, Hybrid, Location, Salary Range.
- Job table: title, company, match score, salary (when stated), experience.
- Job detail drawer: description, required skills, missing skills, match
  explanation.
- Actions: **Save Job**, **Apply** (opens the posting in a new tab and lets the
  user mark it as applied), **Update Resume** (opens the Resume Optimizer for that
  job).
- Results are saved per user with the date found; postings expire, so the page
  shows that date and has a Refresh button.

### 11. Resume Optimizer (BR-27)
- Input: the user's resume (uploaded, or built from the profile if none) and one
  selected job.
- Output: a tailored version, shown side by side with the original in the Resume
  Comparison Viewer, with highlights for added keywords, suggested projects and
  skill improvements.
- **The optimizer never invents experience, employers, dates, degrees or
  certifications.** It may reword, reorder and emphasize what is in the resume and
  profile, and add skills the user has reported as completed. Anything it suggests
  that the user has not done is listed separately as "To add once you have done
  this" and is not placed in the resume. Python checks that every employer, title
  and date in the output exists in the source.
- Actions: Download PDF, Download DOCX, Copy Content.

## Agents

| Agent | Status | Notes |
|---|---|---|
| Intake | Extend | New fields, resume upload step, "help me choose" a role |
| Resume parser | New | Structured extraction, user reviews the result |
| Gap analysis | Extend | Uses resume data and the capability assessment |
| Course search + refinement (LangGraph) | Extend | Adds the YouTube source, preference-aware ranking, vetting signals |
| Scheduler | Extend | No padding, task status and due dates, replanning of remaining weeks |
| Report | New | Writes the two narrative sections; Python assembles the rest |
| Job search + vetting | New | `JobSource` interface, URL verification, Python match score |
| Resume optimizer | New | Tailors to one job under the no-invention rule |

Each agent keeps its own folder and prompt file with Pydantic inputs and outputs.
LangGraph remains limited to flows with a real pause-for-user loop.

## Tech stack

- Frontend: React (JavaScript) with Vite and React Router. Plain CSS with the
  design tokens above. Charts with Recharts. Keep other dependencies minimal.
- Backend: Python, FastAPI, REST plus Server-Sent Events for chats.
- LLM: Anthropic API through the official Python SDK; default `claude-sonnet-5`,
  `claude-haiku-4-5-20251001` for cheap development testing.
- Orchestration: LangGraph for course search and refinement only.
- Database: SQLite with SQLAlchemy. **Add Alembic migrations in milestone 8**, since
  the profile table changes and from then on data must survive schema changes.
- File handling: `pypdf` and `python-docx` to read resumes; generated PDF and DOCX
  for the report, roadmap and tailored resume. Uploads are stored under
  `backend/uploads/<user_id>/`, which is gitignored.
- Config in `backend/.env`: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `DATABASE_URL`,
  `FRONTEND_ORIGIN`, `GOOGLE_CLIENT_ID`, `SESSION_SECRET`, `CHECKPOINT_DB`,
  `YOUTUBE_API_KEY`, `JOB_SITES`. `frontend/.env`: `VITE_GOOGLE_CLIENT_ID`. Keep
  both `.env.example` files in sync. Secrets never reach the frontend.

## Engineering requirements

- Every endpoint requires a signed-in user and touches only that user's data. New
  endpoints get a 401 test and a cross-user isolation test.
- Every external source (YouTube, web search, job sites) sits behind an interface
  with a fake for tests, and a failure degrades to the remaining sources with a
  notice on the page instead of an error.
- Scores, budgets, dates and totals are calculated in Python. The LLM is never the
  source of a number the user relies on, or of a URL.
- Uploaded files are validated by type and size, and treated as untrusted input:
  resume text is passed to the LLM as data, and instructions inside it are ignored.
- "Start over" deletes the user's rows, graph checkpoints and uploaded files.
- Never disable SSL verification; use truststore as in V1.
- README, CLAUDE.md and this file are updated in the same milestone as the code.
- Commit after each working milestone.

## Milestones

1. React + FastAPI skeleton and conversational intake — done
2. Google sign-in — done
3. Skill-gap analysis — done
4. Knowledge base + ranking — done
5. Resource approval, scheduler, roadmap — done
6. Live web search + refinement chat (LangGraph) — done
7. **Design system and app shell.** Dark theme and tokens, sidebar navigation,
   reusable components, Home page, and the existing Intake, Skill Analysis,
   Resources and Roadmap pages restyled to the PRD. Frontend only; no backend
   behavior changes. — done
8. **Expanded intake, resume upload and Career Profile** (BR-01 to BR-07, BR-09 to
   BR-12). New profile fields with Alembic migrations, resume parser, gap analysis
   using resume data and the capability assessment, skill gap chart. — built, in testing
9. **Resource sources and preferences** (BR-17, BR-20, BR-21). YouTube source,
   preference- and budget-aware ranking, filters, Save / Start / Complete.
10. **Roadmap tracking and Transition Report** (BR-18, BR-19, BRD 8.4). Status,
    due dates, checkboxes, no padding, immediate next steps, the report, PDF export.
11. **Dashboard and Progress Review** (BR-22 to BR-25). Metrics and charts,
    progress updates, gap reassessment, replanning of remaining weeks.
12. **Job Match** (BR-26).
13. **Resume Optimizer** (BR-27).
14. **Polish.** Accessibility and mobile pass, View Demo account, performance
    check, full README and demo walkthrough.

## Out of scope

- Applying to jobs on the user's behalf or any browser automation.
- Interview preparation coaching.
- LinkedIn or GitHub login, profile import or scraping.
- Automatic verification of course completion.
- Payments, subscriptions, admin accounts, reminders and notifications.

## Definition of done

Signed in with Google, I can upload my resume or answer the intake questions,
confirm my Career Profile, see evidence-based strengths and prioritized gaps, get
resources that respect my budget and learning preferences (including YouTube) with
working links, refine and approve them, and get a six-month roadmap that fits my
weekly hours with domain portfolio projects. I can download the AI Career
Transition Report as a PDF. When I come back I can report progress, see my
readiness score change and get a refreshed plan. I can see matching jobs with a
match score and an explanation, and for one of them get a tailored resume that
contains nothing I have not done, as PDF or DOCX. The app uses the PRD's dark
design throughout, works on a phone, and a different Google account sees none of
my data.
