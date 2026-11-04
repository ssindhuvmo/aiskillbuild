"""The /api/resume endpoints: upload -> review -> save, profile pre-fill, per-user files (fake LLM)."""
from fastapi.testclient import TestClient

from app.main import app
from core.agents.resume_parser import storage
from tests.conftest import login
from tests.resume_files import RESUME_LINES, make_docx, make_pdf
from tests.test_gap_analysis import PROFILE
from tests.test_resume_parser import fake, good  # noqa: F401  (fixture)

PDF = make_pdf(RESUME_LINES)


def upload(client, content=PDF, name="Jane_Resume.pdf"):
    return client.post("/api/resume", files={"file": (name, content, "application/pdf")})


def test_upload_review_and_save_prefills_the_profile(anon, fake):  # noqa: F811
    login(anon, "cv1")
    assert anon.get("/api/resume").json()["status"] == "none"
    fake(good())
    r = upload(anon)
    assert r.status_code == 200, r.text
    state = r.json()
    assert state["status"] == "review" and state["filename"] == "Jane_Resume.pdf"
    assert state["data"]["skills"] == ["Python", "PostgreSQL", "Kafka", "AWS"]
    assert state["profile"]["resume_status"] == "review"

    # The user corrects the draft (adds a skill the parser missed) and saves it.
    data = {**state["data"], "skills": [*state["data"]["skills"], "Terraform"]}
    r = anon.put("/api/resume", json=data)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["status"] == "reviewed" and "Terraform" in saved["data"]["skills"]
    profile = saved["profile"]
    assert profile["current_role"] == "Senior Backend Engineer"
    assert profile["years_experience"] == saved["years_experience"] >= 11
    assert profile["domain"] == "FinTech"
    assert profile["field_sources"] == {"current_role": "resume", "years_experience": "resume", "domain": "resume"}
    assert {s["id"]: s["done"] for s in profile["steps"]}["resume"] is True


def test_prefill_keeps_values_the_user_entered(anon, fake):  # noqa: F811
    login(anon, "cv2")
    anon.put("/api/profile", json={"current_role": "Platform Lead"})
    fake(good())
    data = upload(anon).json()["data"]
    profile = anon.put("/api/resume", json=data).json()["profile"]
    assert profile["current_role"] == "Platform Lead"
    assert profile["field_sources"]["current_role"] == "user"
    assert profile["field_sources"]["domain"] == "resume"


def test_confirm_is_blocked_while_the_resume_is_in_review(anon, fake):  # noqa: F811
    login(anon, "cv3")
    anon.put("/api/profile", json=PROFILE)
    fake(good())
    data = upload(anon).json()["data"]
    r = anon.post("/api/profile/confirm")
    assert r.status_code == 422 and "resume" in r.json()["detail"]["errors"]
    anon.put("/api/resume", json=data)
    assert anon.post("/api/profile/confirm").status_code == 200


def test_saving_the_resume_unconfirms_the_profile(anon, fake):  # noqa: F811
    login(anon, "cv4")
    anon.put("/api/profile", json=PROFILE)
    anon.post("/api/profile/confirm")
    fake(good(), good())
    data = upload(anon).json()["data"]
    assert anon.put("/api/resume", json=data).json()["profile"]["confirmed"] is False


def test_partial_result_reports_what_was_dropped(anon, fake):  # noqa: F811
    login(anon, "cv5")
    fake(*[good(skills=["Python", "Rust"])] * 3)
    state = upload(anon).json()
    assert state["data"]["skills"] == ["Python"] and state["dropped"] == ['Skill "Rust"']


def test_bad_uploads(anon, fake):  # noqa: F811
    login(anon, "cv6")
    assert upload(anon, b"MZ\x90\x00", "cv.pdf").status_code == 415
    assert upload(anon, b"%PDF-" + b"0" * (5 * 1024 * 1024), "cv.pdf").status_code == 413
    assert upload(anon, make_pdf([]), "scan.pdf").status_code == 422
    fake(*[{"skills": ["Rust"]}] * 3)
    assert upload(anon).status_code == 502
    assert anon.get("/api/resume").json()["status"] == "none"  # nothing stored after a failure
    assert not storage.user_dir("cv6").exists()


def test_docx_upload(anon, fake):  # noqa: F811
    login(anon, "cv7")
    fake(good())
    r = upload(anon, make_docx(RESUME_LINES), "cv.docx")
    assert r.status_code == 200 and (storage.user_dir("cv7") / "resume.docx").exists()


def test_save_checks_dates_and_needs_an_upload(anon, fake):  # noqa: F811
    login(anon, "cv8")
    assert anon.put("/api/resume", json=good()).status_code == 409
    fake(good())
    upload(anon)
    bad = good(roles=[{"title": "Engineer", "employer": "Co", "start": "2020-05", "end": "2019-01"}])
    r = anon.put("/api/resume", json=bad)
    assert r.status_code == 422 and "ends before it starts" in r.json()["detail"]["errors"]["resume"]
    assert anon.put("/api/resume", json={**good(), "skills": "x"}).status_code == 422


def test_delete_removes_file_and_row(anon, fake):  # noqa: F811
    login(anon, "cv9")
    fake(good())
    anon.put("/api/resume", json=upload(anon).json()["data"])
    assert storage.user_dir("cv9").exists()
    state = anon.delete("/api/resume").json()
    assert state["status"] == "none" and not storage.user_dir("cv9").exists()
    assert state["profile"]["current_role"] == "Senior Backend Engineer"  # kept, no longer labelled
    assert state["profile"]["field_sources"] == {}
    assert anon.delete("/api/resume").status_code == 200  # nothing to delete is fine


def test_users_only_see_their_own_resume(anon, fake):  # noqa: F811
    login(anon, "cv10")
    fake(good(), good())
    upload(anon)
    with TestClient(app, base_url="https://testserver") as other:
        login(other, "cv11")
        assert other.get("/api/resume").json()["status"] == "none"
        assert other.put("/api/resume", json=good()).status_code == 409
        assert other.delete("/api/resume").status_code == 200
        upload(other, name="other.pdf")
        assert other.get("/api/resume").json()["filename"] == "other.pdf"
    assert anon.get("/api/resume").json()["filename"] == "Jane_Resume.pdf"
    assert storage.user_dir("cv10") != storage.user_dir("cv11")
    assert (storage.user_dir("cv10") / "resume.pdf").exists() and (storage.user_dir("cv11") / "resume.pdf").exists()


def test_start_over_removes_the_file(anon, fake):  # noqa: F811
    login(anon, "cv12")
    fake(good())
    upload(anon)
    assert anon.delete("/api/account/data").status_code == 200
    assert not storage.user_dir("cv12").exists()
    assert anon.get("/api/resume").json()["status"] == "none"


def test_unsafe_user_ids_are_hashed(uploads):
    assert storage.user_dir("abc_123-X") == uploads / "abc_123-X"
    hashed = storage.user_dir("../../etc")
    assert hashed.parent == uploads and len(hashed.name) == 64
