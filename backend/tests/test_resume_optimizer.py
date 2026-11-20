"""Resume Optimizer (milestone 13): references instead of facts, the checks on the model's text, completed
roadmap work as evidence, one version per job, the user's edits, exports and per-user isolation."""
import io
import zipfile

import anthropic
import pytest

from core import db as dbmod
from core.agents.job_search.schemas import Job
from core.agents.resume_optimizer import assemble, rules
from core.agents.resume_optimizer.schemas import DoneProject, Evidence, PendingProject, TailoredText
from core.agents.resume_parser.schemas import ResumeData
from core.agents.scheduler.schemas import Project
from core.llm import LLMUnavailable
from core.models import AgentOutput, Resume
from tests.conftest import facts_of, login, tailor_plainly
from tests.test_jobs import finding
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_resume_parser import good
from tests.test_roadmap import approved_user, fake, generate  # noqa: F401  (fixture)
from tests.test_roadmap_tracking import START, today  # noqa: F401  (fixture)

HIGHLIGHT = "Built the card payments API handling 3 million requests a day."


def resume_data():
    data = good()
    data["roles"][0]["highlights"] = [HIGHLIGHT, "Led integration of partner APIs."]
    return data


def evidence(**changes) -> Evidence:
    base = dict(
        name="Ada", email="ada@example.com", current_role="Backend Engineer", target_role="ML Engineer",
        years_experience=9, resume=ResumeData.model_validate(resume_data()), has_resume=True,
        skills=["Python", "PostgreSQL", "Kafka", "AWS", "Deep learning"], completed_gaps=["Deep learning"],
        projects=[DoneProject(id="p1", phase=1, project=Project(
            title="Fraud model", problem="Card fraud.", dataset="IEEE-CIS Fraud Detection",
            deliverables=["A trained classifier"]))],
        courses=[], pending_gaps=["PCI-DSS"],
        pending_projects=[PendingProject(id="p2", phase=2, months=[3, 4], title="AML pipeline")],
    )
    return Evidence(**{**base, **changes})


JOB = Job(id="job-1", title="ML Engineer", company="Company 1", url="https://x", summary="Builds fraud models with "
          "deep learning on payments data.", required_skills=["Python", "Deep learning", "Kubernetes"], found_on=START)


def text(**changes) -> TailoredText:
    base = {
        "headline": "Senior Backend Engineer · Payments and ML", "summary": "Backend engineer moving into ML.",
        "roles": [{"ref": 0, "highlights": [HIGHLIGHT]}, {"ref": 1, "highlights": []}],
        "skills": ["Python", "Deep learning"], "projects": [{"ref": "p1", "bullets": ["Trained a fraud classifier."]}],
        "courses": [], "keywords": ["fraud models"],
        "to_add": [{"kind": "skill", "name": "Kubernetes", "note": "Not in your plan yet."}],
    }
    base["summary"] = "Backend engineer moving into ML, building fraud models."
    return TailoredText.model_validate({**base, **changes})


# --- pure ---------------------------------------------------------------------------


def test_valid_text_passes_the_checks():
    assert rules.check(text(), evidence(), JOB) == []


@pytest.mark.parametrize("changes, expected", [
    ({"roles": [{"ref": 0, "highlights": []}]}, "every role exactly once"),
    ({"skills": ["Python", "Kubernetes"]}, '"Kubernetes" is not one the person can claim'),
    ({"projects": [{"ref": "p2", "bullets": ["x"]}]}, "not a completed project"),
    ({"courses": ["kb-unknown"]}, "not a completed course"),
    ({"summary": "Cut fraud losses by 40% since 2012."}, "2012, 40 is not in the person's data"),
    ({"summary": "See https://example.com"}, "URLs or links"),
    ({"summary": "Ready to join Company 1."}, "do not name Company 1"),
    ({"keywords": ["blockchain"]}, "not in the posting"),
    ({"keywords": ["payments data"]}, "does not appear in the tailored resume"),
    ({"to_add": [{"kind": "skill", "name": "Python", "note": "x"}]}, "does not have yet"),
    ({"to_add": [{"kind": "project", "name": "Moon base", "note": "x"}]}, "unfinished roadmap project"),
])
def test_checks_reject_invented_content(changes, expected):
    assert expected in " ".join(rules.check(text(**changes), evidence(), JOB))


def test_placeholders_and_source_numbers_are_allowed():
    t = text(roles=[{"ref": 0, "highlights": [HIGHLIGHT.replace("3 million", "[add your scale]")]},
                    {"ref": 1, "highlights": ["Shipped services for 9 years of growth [add team size of 12]."]}])
    assert rules.check(t, evidence(), JOB) == []  # 9 = years of experience; 12 sits in a placeholder


def test_facts_are_copied_and_changes_are_marked():
    e = evidence()
    doc = assemble.tailored(e, text(roles=[{"ref": 1, "highlights": []},
                                           {"ref": 0, "highlights": ["Built the card payments API for fraud models."]}]))
    assert [(r.title, r.employer, r.dates) for r in doc.roles] == [
        ("Software Engineer", "Globex", "2015-06 – 2019-02"), ("Senior Backend Engineer", "Acme Payments", "2019-03 – present")]
    segments = doc.roles[1].highlights[0]
    assert assemble.plain(segments) == "Built the card payments API for fraud models."
    assert [s.text for s in segments if s.added] == ["for fraud models."]
    assert [(s.name, s.added) for s in doc.skills] == [("Python", False), ("Deep learning", True)]
    assert doc.projects[0].title == "Fraud model" and doc.education == ["BSc Computer Science, State University, 2015"]


def test_default_text_is_the_resume_plus_completed_work():
    from core.agents.job_search import matching
    view = matching.view(JOB, set(), {})
    t = assemble.default_text(evidence(), view)
    assert rules.check(t, evidence(), JOB) == []
    assert [r.ref for r in t.roles] == [0, 1] and t.roles[0].highlights[0] == HIGHLIGHT
    assert "Deep learning" in t.skills and t.projects[0].ref == "p1"
    assert [(a.kind, a.name) for a in t.to_add] == [("skill", "Kubernetes"), ("project", "AML pipeline")]


# --- endpoints ----------------------------------------------------------------------


def set_resume(sub, data):
    with dbmod.SessionLocal() as db:
        db.merge(Resume(user_id=sub, filename="cv.pdf", stored_path="", content_type="application/pdf", size=1,
                        text="", status="reviewed", data=data))
        db.commit()


def ready_user(client, sub, fake_gaps, searcher, resume=True, jobs=(1,)):  # noqa: F811
    """Approved resources, a roadmap, a reviewed resume and Job Match results. Returns (resource ids, roadmap)."""
    ids = approved_user(client, sub, fake_gaps)
    roadmap = generate(client)[1]["roadmap"]
    if resume:
        set_resume(sub, resume_data())
    searcher.jobs.results = [finding(n) for n in jobs]
    assert client.post("/api/jobs/search", json={"remote": True}).status_code == 200
    return ids, roadmap


def job_ids(client):
    return [j["id"] for j in client.get("/api/resume-optimizer").json()["jobs"]]


def optimize(client, job):
    r = client.post(f"/api/resume-optimizer/{job}")
    assert r.status_code == 200, r.text
    return r.json()


def test_needs_an_analysis_and_a_known_job(anon, fake_gaps, fake, today, searcher):  # noqa: F811
    login(anon, "ro1")
    assert anon.get("/api/resume-optimizer").json() == {"can_optimize": False, "has_resume": False, "jobs": []}
    assert anon.post("/api/resume-optimizer/job-x").status_code == 409
    ready_user(anon, "ro1", fake_gaps, searcher)
    assert anon.post("/api/resume-optimizer/job-x").status_code == 422
    job = job_ids(anon)[0]
    assert anon.get(f"/api/resume-optimizer/{job}").status_code == 404
    assert anon.get(f"/api/resume-optimizer/{job}/export.pdf").status_code == 404


def test_optimize_copies_facts_and_saves_one_version_per_job(anon, fake_gaps, fake, today, searcher, resume_llm):  # noqa: F811
    ready_user(anon, "ro2", fake_gaps, searcher, jobs=(1, 2))
    first, second = job_ids(anon)
    view = optimize(anon, first)
    assert view["source"] == "ai" and view["notice"] is None and not view["stale"] and view["has_resume"]
    roles = view["tailored"]["roles"]
    assert [(r["title"], r["employer"]) for r in roles] == [("Senior Backend Engineer", "Acme Payments"),
                                                           ("Software Engineer", "Globex")]
    assert view["original"]["roles"][0]["highlights"][0][0]["text"] == HIGHLIGHT
    assert view["tailored"]["name"] == "User ro2" and view["text"].startswith("User ro2\nro2@example.com\n")
    assert view["improvements"] == view["job"]["missing"] and view["improvements"]
    facts = facts_of(resume_llm.requests[0])
    assert facts["completed_projects"] == [] and facts["pending_gaps"] == ["Deep learning", "PCI-DSS"]
    assert "<job>" in resume_llm.requests[0]

    optimize(anon, second)
    options = {j["id"]: j for j in anon.get("/api/resume-optimizer").json()["jobs"]}
    assert options[first]["has_version"] and options[second]["has_version"]
    assert anon.get(f"/api/resume-optimizer/{first}").json()["job"]["job"]["id"] == first
    with dbmod.SessionLocal() as db:
        assert db.query(AgentOutput).filter_by(user_id="ro2", agent="resume_optimizer").count() == 2


def test_completed_roadmap_work_becomes_evidence(anon, fake_gaps, fake, today, searcher, resume_llm):  # noqa: F811
    ids, roadmap = ready_user(anon, "ro3", fake_gaps, searcher)
    job = job_ids(anon)[0]
    optimize(anon, job)

    # Finish phase 1's portfolio project and one course, and mark a plan skill completed.
    phase = roadmap["phases"][0]
    project_tasks = [t["id"] for m in roadmap["months"] if m["number"] in phase["months"]
                     for w in m["weeks"] for t in w["tasks"] if t["kind"] == "project"]
    assert project_tasks
    for tid in project_tasks:
        assert anon.put("/api/roadmap/items", json={"item_id": tid, "done": True}).status_code == 200
    assert anon.put("/api/resources/progress", json={"resource_id": ids[0], "status": "completed"}).status_code == 200
    anon.put("/api/progress", json={"skills": [{"skill": "PCI-DSS", "completed": True}]})

    assert anon.get(f"/api/resume-optimizer/{job}").json()["stale"]  # progress changed since it was written
    view = optimize(anon, job)
    facts = facts_of(resume_llm.requests[-1])
    assert [p["id"] for p in facts["completed_projects"]] == ["p1"]
    assert [c["id"] for c in facts["completed_courses"]] == [ids[0]]
    assert "PCI-DSS" in facts["allowed_skills"] and "PCI-DSS" not in facts["pending_gaps"]
    assert [p["id"] for p in facts["pending_projects"]] == ["p2", "p3"]
    tailored = view["tailored"]
    assert tailored["projects"][0]["title"] == phase["project"]["title"] and tailored["courses"]
    assert not view["stale"] and "PCI-DSS" in [s["name"] for s in tailored["skills"]]


def test_rejected_text_is_retried_then_falls_back(anon, fake_gaps, fake, today, searcher, resume_llm):  # noqa: F811
    ready_user(anon, "ro4", fake_gaps, searcher)
    job = job_ids(anon)[0]

    def invented(text):
        reply = tailor_plainly(text)
        reply["skills"] = ["Kubernetes"]
        return reply

    resume_llm.replies = [invented, tailor_plainly]
    view = optimize(anon, job)
    assert view["source"] == "ai" and "Kubernetes" in resume_llm.requests[1]

    resume_llm.replies = [invented, invented]
    view = optimize(anon, job)
    assert view["source"] == "default" and "didn't pass the checks" in view["notice"]
    assert [r["employer"] for r in view["tailored"]["roles"]] == ["Acme Payments", "Globex"]
    assert any(a["kind"] == "project" for a in view["to_add"])  # the unfinished roadmap projects

    resume_llm.replies = [LLMUnavailable("ANTHROPIC_API_KEY is not set.")]
    assert optimize(anon, job)["source"] == "default"
    resume_llm.replies = [anthropic.APIConnectionError(request=None)]
    assert optimize(anon, job)["source"] == "default"


def test_edits_are_saved_checked_and_reset(anon, fake_gaps, fake, today, searcher):  # noqa: F811
    ready_user(anon, "ro5", fake_gaps, searcher)
    job = job_ids(anon)[0]
    view = optimize(anon, job)
    body = {"headline": "Payments engineer", "summary": "Built payments at [add your scale].",
            "roles": [["Built the payments API handling 2 million calls."], []], "skills": ["Python"], "projects": []}
    edited = anon.put(f"/api/resume-optimizer/{job}", json=body).json()
    assert edited["edited"] and edited["placeholders"] == 1
    assert edited["tailored"]["roles"][0]["employer"] == "Acme Payments"  # not editable
    assert "2 million" in edited["text"]  # the user is the source of their own numbers

    assert anon.put(f"/api/resume-optimizer/{job}", json={**body, "roles": [[]]}).status_code == 422
    assert anon.put(f"/api/resume-optimizer/{job}", json={**body, "summary": "www.me.com"}).status_code == 422
    reset = anon.delete(f"/api/resume-optimizer/{job}/edits").json()
    assert not reset["edited"] and reset["text"] == view["text"]

    anon.put(f"/api/resume-optimizer/{job}", json=body)
    assert not optimize(anon, job)["edited"]  # optimizing again replaces the edits


def test_without_a_resume_there_is_no_work_history(anon, fake_gaps, fake, today, searcher):  # noqa: F811
    ready_user(anon, "ro6", fake_gaps, searcher, resume=False)
    view = optimize(anon, job_ids(anon)[0])
    assert not view["has_resume"] and view["tailored"]["roles"] == [] and "Upload one" in view["notice"]


def test_exports(anon, fake_gaps, fake, today, searcher):  # noqa: F811
    ready_user(anon, "ro7", fake_gaps, searcher)
    job = job_ids(anon)[0]
    optimize(anon, job)
    pdf = anon.get(f"/api/resume-optimizer/{job}/export.pdf")
    assert pdf.content.startswith(b"%PDF-") and "resume-company-1" in pdf.headers["content-disposition"]
    docx = anon.get(f"/api/resume-optimizer/{job}/export.docx")
    document = zipfile.ZipFile(io.BytesIO(docx.content)).read("word/document.xml").decode()
    assert "Acme Payments" in document and "To add" not in document


def test_versions_are_per_user(anon, fake_gaps, fake, today, searcher):  # noqa: F811
    ready_user(anon, "ro8", fake_gaps, searcher)
    job = job_ids(anon)[0]
    optimize(anon, job)
    login(anon, "ro9")
    assert anon.get(f"/api/resume-optimizer/{job}").status_code == 404
    assert anon.post(f"/api/resume-optimizer/{job}").status_code == 409  # no analysis, and not their job
