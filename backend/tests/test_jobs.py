"""Job Match (milestone 12): allowlisted search, verified links, the Python match score, the checked skill
mapping with its name-only fallback, Save / Apply marks, and per-user isolation."""
import anthropic
import httpx
from sqlalchemy import select

from core import db as dbmod
from core.agents.job_search import matching
from core.agents.job_search.schemas import Assessments, Job, SkillMatch
from core.agents.job_search.source import on_allowed_site, to_findings
from core.models import AgentOutput
from tests.conftest import assess_nothing, login
from tests.test_gap_analysis import confirmed_user
from tests.test_resources import fake_gaps, gaps_confirmed_user  # noqa: F401  (fixture)
from tests.test_roadmap_tracking import START, today  # noqa: F401  (fixture)

SITES = ["boards.greenhouse.io", "jobs.lever.co", "indeed.com", "wellfound.com/jobs"]


def finding(n, required=("Python", "Deep learning", "Kubernetes"), **extra):
    return {
        "title": f"ML Engineer {n}", "company": f"Company {n}", "url": f"https://boards.greenhouse.io/c{n}/jobs/{n}",
        "location": "Remote", "work_mode": "remote", "salary": "$120,000 - $150,000", "experience": "5+ years",
        "summary": "Builds fraud models.", "required_skills": list(required), **extra,
    }


def mapped(have=None, in_plan=None, explanation="Your background fits; deep learning is the main gap."):
    """An assessment that maps by the given {required: skill} dicts."""
    have, in_plan = have or {}, in_plan or {}

    def reply(text):
        base = assess_nothing(text)
        for job in base["jobs"]:
            job["explanation"] = explanation
            for m in job["matches"]:
                m["have"], m["in_plan"] = have.get(m["required"]), in_plan.get(m["required"])
        return base
    return reply


def search(client, **query):
    return client.post("/api/jobs/search", json={"location": "", "remote": True, **query})


# --- pure ---------------------------------------------------------------------------


def test_only_search_result_urls_on_allowed_sites_are_kept():
    raw = [
        finding(1),
        finding(2, url="https://www.linkedin.com/jobs/view/2"),  # not on an allowed site
        finding(3, url="https://uk.indeed.com/viewjob?jk=3"),  # subdomain of an allowed site
        finding(4, url="https://jobs.lever.co/x/4"),  # not in the search results
        finding(5, url="https://wellfound.com/company/x"),  # allowed host but outside the allowed path
        {"title": "broken"},
    ]
    allowed = {"https://boards.greenhouse.io/c1/jobs/1", "https://www.linkedin.com/jobs/view/2",
               "https://uk.indeed.com/viewjob?jk=3", "https://wellfound.com/company/x"}
    assert [f.company for f in to_findings(raw, allowed, SITES)] == ["Company 1", "Company 3"]
    assert on_allowed_site("https://wellfound.com/jobs/123", SITES)
    assert not on_allowed_site("https://evil-indeed.com/x", SITES)


def test_salary_parsing():
    assert matching.parse_salary("$120,000 - $150,000 a year") == (120000, 150000)
    assert matching.parse_salary("£60k–£70k") == (60000, 70000)
    assert matching.parse_salary("EUR 120.000") == (120000, 120000)
    assert matching.parse_salary("$45/hour") == (None, None)
    assert matching.parse_salary("Competitive") == (None, None) and matching.parse_salary(None) == (None, None)


def test_check_accepts_only_the_users_own_names():
    job = Job(id="job-1", title="t", company="c", url="https://x", summary="s", required_skills=["Python", "MLOps"],
              found_on=START)
    ok = Assessments.model_validate({"jobs": [{"job_id": "job-1", "explanation": "Good fit.", "matches": [
        {"required": "python", "have": "python"}, {"required": "MLOps", "in_plan": "Deep learning"}]}]})
    assert matching.check(ok, [job], ["Python"], ["Deep learning"]) == []
    bad = Assessments.model_validate({"jobs": [{"job_id": "job-1", "explanation": "A 90% match, see https://x", "matches": [
        {"required": "Python", "have": "Rust", "in_plan": "Deep learning"}]}]})
    problems = " ".join(matching.check(bad, [job], ["Python"], ["Deep learning"]))
    for part in ("exactly once", "both have and in_plan", '"Rust" is not one of', "links, percentages"):
        assert part in problems


def test_score_counts_completed_plan_gaps():
    job = Job(id="job-1", title="t", company="c", url="https://x", summary="s", found_on=START,
              required_skills=["Python", "Deep learning", "Go"])
    matches = [SkillMatch(required="Python", have="Python"), SkillMatch(required="Deep learning", in_plan="Deep learning"),
               SkillMatch(required="Go")]
    job = matching.apply(job, matches, "Fits.", ["Python"], ["Deep learning"])
    v = matching.view(job, set(), {"deep learning": 2})
    assert v.score == 33 and v.have == ["Python"]
    assert [(m.skill, m.in_plan, m.phase) for m in v.missing] == [("Deep learning", "Deep learning", 2), ("Go", None, None)]
    assert matching.view(job, {"deep learning"}, {}).score == 67


# --- endpoints ----------------------------------------------------------------------


def test_requires_a_gap_analysis(anon, searcher):
    confirmed_user(anon, "j1")
    state = anon.get("/api/jobs").json()
    assert state["status"] == "none" and not state["can_search"] and state["sites"]
    assert search(anon).status_code == 409 and searcher.jobs.calls == []


def test_search_verifies_links_scores_and_saves(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j2", fake_gaps)
    searcher.jobs.results = [finding(1), finding(2, required=("Python", "Deep learning")), finding(3), finding(4)]
    searcher.link_status["https://boards.greenhouse.io/c3/jobs/3"] = "fail"
    searcher.link_status["https://boards.greenhouse.io/c4/jobs/4"] = "blocked"
    searcher.job_llm.replies = [mapped(have={"Python": "Python"}, in_plan={"Deep learning": "Deep learning"})]

    state = search(anon, location="Berlin", hybrid=True).json()
    query, seeker = searcher.jobs.calls[0]
    assert (query.location, query.remote, query.hybrid) == ("Berlin", True, True)
    assert seeker.target_role and "Python" in seeker.skills  # a strength from the analysis
    assert state["status"] == "ready" and state["notice"] is None and state["query"]["location"] == "Berlin"
    jobs = {v["job"]["company"]: v for v in state["jobs"]}
    assert set(jobs) == {"Company 1", "Company 2", "Company 4"}  # the failed link is dropped
    assert jobs["Company 4"]["job"]["link"] == "blocked" and jobs["Company 1"]["job"]["link"] == "ok"
    assert jobs["Company 2"]["score"] == 50 and jobs["Company 1"]["score"] == 33
    assert [v["job"]["company"] for v in state["jobs"]][0] == "Company 2"  # best match first
    assert jobs["Company 1"]["job"]["salary_min"] == 120000 and jobs["Company 1"]["job"]["found_on"] == START.isoformat()
    assert jobs["Company 1"]["missing"][0] == {"skill": "Deep learning", "in_plan": "Deep learning", "phase": None}
    assert jobs["Company 1"]["job"]["explained_by"] == "ai"
    assert "Python" in searcher.job_llm.requests[0] and "<postings>" in searcher.job_llm.requests[0]
    assert anon.get("/api/jobs").json() == state
    with dbmod.SessionLocal() as db:
        assert db.scalars(select(AgentOutput).where(AgentOutput.user_id == "j2", AgentOutput.agent == "job_search")).one()


def test_score_rises_when_a_plan_gap_is_completed(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j3", fake_gaps)
    searcher.jobs.results = [finding(1, required=("Python", "Deep learning"))]
    searcher.job_llm.replies = [mapped(have={"Python": "Python"}, in_plan={"Deep learning": "Deep learning"})]
    assert search(anon).json()["jobs"][0]["score"] == 50
    anon.put("/api/progress", json={"skills": [{"skill": "Deep learning", "completed": True}]})
    assert anon.get("/api/jobs").json()["jobs"][0]["score"] == 100  # no new search


def test_a_bad_mapping_is_retried_then_falls_back_to_names(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j4", fake_gaps)
    searcher.jobs.results = [finding(1, required=("Python", "Kubernetes"))]
    searcher.job_llm.replies = [mapped(have={"Python": "Rust"})] * 2
    state = search(anon).json()
    assert len(searcher.job_llm.requests) == 2 and "was rejected" in searcher.job_llm.requests[1]
    job = state["jobs"][0]
    assert job["job"]["explained_by"] == "default" and "name only" in state["notice"]
    assert job["have"] == ["Python"] and job["score"] == 50  # "Python" strength matched by name

    error = anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=httpx.Request("POST", "https://x")), body=None)
    searcher.job_llm.replies = [error]
    assert search(anon).json()["jobs"][0]["job"]["explained_by"] == "default"


def test_search_failure_and_no_results(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j5", fake_gaps)
    searcher.jobs.results = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    r = search(anon)
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
    assert anon.get("/api/jobs").json()["status"] == "none"
    searcher.jobs.results = []
    state = search(anon).json()
    assert state["status"] == "ready" and state["jobs"] == [] and "No open postings" in state["notice"]


def test_save_and_apply_survive_a_refresh_and_reach_the_dashboard(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j6", fake_gaps)
    searcher.jobs.results = [finding(1), finding(2)]
    first, second = (v["job"]["id"] for v in search(anon).json()["jobs"])

    assert anon.put("/api/jobs/marks", json={"job_id": first, "saved": True}).json()["jobs"][0]["saved"] is not None
    state = anon.put("/api/jobs/marks", json={"job_id": second, "applied": True}).json()
    applied = next(v for v in state["jobs"] if v["job"]["id"] == second)
    assert applied["applied"] and applied["applied_at"]
    assert anon.put("/api/jobs/marks", json={"job_id": "job-nope", "saved": True}).status_code == 422
    d = anon.get("/api/dashboard").json()["dashboard"]
    assert (d["jobs_applied"], d["jobs_saved"]) == (1, 1)

    searcher.jobs.results = [finding(3)]  # a refresh with different postings keeps the marked jobs
    state = search(anon).json()
    assert [v["job"]["company"] for v in state["jobs"]] == ["Company 3"]
    assert {v["job"]["id"] for v in state["kept"]} == {first, second}
    state = anon.put("/api/jobs/marks", json={"job_id": first, "saved": False}).json()  # unsave: the row goes
    assert {v["job"]["id"] for v in state["kept"]} == {second}


def test_jobs_are_per_user(anon, fake_gaps, searcher, today):  # noqa: F811
    gaps_confirmed_user(anon, "j7", fake_gaps)
    searcher.jobs.results = [finding(1)]
    job = search(anon).json()["jobs"][0]["job"]["id"]
    anon.put("/api/jobs/marks", json={"job_id": job, "applied": True})
    anon.post("/api/auth/logout")

    gaps_confirmed_user(anon, "j8", fake_gaps)
    state = anon.get("/api/jobs").json()
    assert state["status"] == "none" and state["kept"] == []
    assert anon.put("/api/jobs/marks", json={"job_id": job, "saved": True}).status_code == 422
    anon.post("/api/auth/logout")
    login(anon, "j7")
    assert anon.get("/api/jobs").json()["jobs"][0]["applied"]
