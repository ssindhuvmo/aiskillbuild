"""DELETE /api/account/data ("Start over"): removes only the signed-in user's rows and keeps the sign-in."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from core import db as dbmod
from core import repository
from core.db import Base
from tests.test_resources import fake_gaps  # noqa: F401  (fixture)
from tests.test_roadmap import approved_user, fake  # noqa: F401  (fixture)
from tests.test_scheduler_budget import draft


def row_counts(sub):
    """Rows per table for this user, over every table that has a user_id (so new tables are covered)."""
    with dbmod.SessionLocal() as db:
        return {
            t.name: db.execute(select(func.count()).select_from(t).where(t.c.user_id == sub)).scalar()
            for t in Base.metadata.sorted_tables
            if "user_id" in t.c
        }


def full_user(client, sub, fake_gaps, fake):  # noqa: F811
    """Signed in with data in every table: profile, chat, gaps, resources, approval and roadmap."""
    ids = approved_user(client, sub, fake_gaps)
    fake(draft(resource_id=ids[0]))
    assert client.post("/api/roadmap/generate").status_code == 200
    with dbmod.SessionLocal() as db:
        repository.append_message(db, sub, "user", "hello")
    counts = row_counts(sub)
    assert all(counts.values()), counts
    return client


def test_start_over_deletes_all_of_the_users_data(anon, fake_gaps, fake):  # noqa: F811
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


def test_start_over_leaves_other_users_untouched(anon, fake_gaps, fake):  # noqa: F811
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
