"""DELETE /api/account/data ("Start over"): removes only the signed-in user's rows and keeps the sign-in."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from core import db as dbmod
from core import repository
from core.agents.course_search.graph import get_graph
from core.db import Base
from core.models import Resume
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_report import report_llm  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, fake, generate  # noqa: F401  (fixture)


def row_counts(sub):
    """Rows per table for this user, over every table that has a user_id (so new tables are covered)."""
    with dbmod.SessionLocal() as db:
        return {
            t.name: db.execute(select(func.count()).select_from(t).where(t.c.user_id == sub)).scalar()
            for t in Base.metadata.sorted_tables
            if "user_id" in t.c
        }


def full_user(client, sub, fake_gaps, fake):  # noqa: F811
    """Signed in with data in every table: profile, chat, gaps, resources, approval, roadmap, checks and report."""
    ids = approved_user(client, sub, fake_gaps)
    generate(client)
    assert client.put("/api/resources/progress", json={"resource_id": ids[0], "saved": True}).status_code == 200
    assert client.put("/api/roadmap/items", json={"item_id": "m1", "done": True}).status_code == 200
    assert client.post("/api/report/generate").status_code == 200
    with dbmod.SessionLocal() as db:
        repository.append_message(db, sub, "user", "hello")
        # The resume row directly (tests/test_resume_api.py covers uploads and their files).
        db.add(Resume(user_id=sub, filename="cv.pdf", stored_path="", content_type="application/pdf", size=1,
                      text="", status="reviewed"))
        db.commit()
    counts = row_counts(sub)
    assert all(counts.values()), counts
    return client


def test_start_over_deletes_all_of_the_users_data(anon, fake_gaps, fake, report_llm):  # noqa: F811
    full_user(anon, "s1", fake_gaps, fake)
    assert anon.delete("/api/account/data").json() == {"ok": True}

    counts = row_counts("s1")
    assert counts.pop("users") == 1
    assert not any(counts.values()), counts

    # Still signed in, and every step is back to its starting state.
    assert anon.get("/api/auth/me").json()["name"] == "User s1"
    intake = anon.get("/api/intake").json()
    assert intake["messages"] == [] and intake["profile"]["current_role"] is None
    assert intake["profile"]["confirmed"] is False
    assert anon.get("/api/gaps").json()["status"] == "none"
    assert anon.get("/api/resources").json()["status"] == "none"
    assert anon.get("/api/roadmap").json()["status"] == "none"
    # The refinement chat lives in the graph's checkpoints, not in a table: it is gone too.
    assert get_graph().get_state({"configurable": {"thread_id": "s1"}}).values == {}


def test_start_over_leaves_other_users_untouched(anon, fake_gaps, fake, report_llm):  # noqa: F811
    full_user(anon, "s2", fake_gaps, fake)
    with TestClient(app, base_url="https://testserver") as other:
        full_user(other, "s3", fake_gaps, fake)
        before = row_counts("s3")
        roadmap = other.get("/api/roadmap").json()

        assert anon.delete("/api/account/data").status_code == 200

        assert row_counts("s3") == before
        assert other.get("/api/roadmap").json() == roadmap
        assert other.get("/api/intake").json()["messages"] == [{"role": "user", "content": "hello"}]
    assert anon.get("/api/roadmap").json()["status"] == "none"


def test_start_over_with_no_data_is_fine(anon):
    from tests.conftest import login

    login(anon, "s4")
    assert anon.delete("/api/account/data").status_code == 200
    assert anon.get("/api/auth/me").status_code == 200
