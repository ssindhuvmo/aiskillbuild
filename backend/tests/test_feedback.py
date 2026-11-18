"""POST /api/feedback: the feedback form. "Start over" keeps the messages but unlinks them from the user."""
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from core import db as dbmod
from core.models import Feedback
from tests.conftest import login
from tests.test_migrations import _engine, _upgrade


def rows(sub=None):
    with dbmod.SessionLocal() as db:
        q = db.query(Feedback)
        if sub is not None:
            q = q.filter_by(user_id=sub)
        return [(f.user_id, f.rating, f.areas, f.message) for f in q.order_by(Feedback.id)]


def test_saves_feedback_on_several_areas(anon):
    login(anon, "fb1")
    body = {"rating": 5, "areas": ["roadmap", "dashboard", "roadmap"], "message": "  Both are great.  "}
    r = anon.post("/api/feedback", json=body)
    assert r.status_code == 200 and r.json() == {"ok": True}
    # Repeated areas are kept once, in the order chosen.
    assert rows("fb1") == [("fb1", 5, ["roadmap", "dashboard"], "Both are great.")]


def test_rating_and_area_are_optional_and_every_message_is_kept(anon):
    login(anon, "fb2")
    assert anon.post("/api/feedback", json={"message": "First."}).status_code == 200
    assert anon.post("/api/feedback", json={"message": "Second.", "areas": ["other"]}).status_code == 200
    assert rows("fb2") == [("fb2", None, [], "First."), ("fb2", None, ["other"], "Second.")]


@pytest.mark.parametrize("body", [
    {},
    {"message": ""},
    {"message": "   \n "},
    {"message": "x" * 2001},
    {"message": "ok", "rating": 0},
    {"message": "ok", "rating": 6},
    {"message": "ok", "areas": ["pricing"]},
    {"message": "ok", "areas": "roadmap"},
])
def test_invalid_feedback_is_rejected(anon, body):
    login(anon, "fb3")
    assert anon.post("/api/feedback", json=body).status_code == 422
    assert rows("fb3") == []


def test_start_over_keeps_the_feedback_without_the_user(anon):
    login(anon, "fb4")
    assert anon.post("/api/feedback", json={"rating": 2, "message": "Search was slow."}).status_code == 200
    with TestClient(app, base_url="https://testserver") as other:
        login(other, "fb5")
        assert other.post("/api/feedback", json={"message": "Mine stays."}).status_code == 200

        assert anon.delete("/api/account/data").status_code == 200

        assert rows("fb4") == []
        assert (None, 2, [], "Search was slow.") in rows()
        assert rows("fb5") == [("fb5", None, [], "Mine stays.")]


def test_migration_0009_turns_the_area_into_a_list(tmp_path):
    engine = _engine(tmp_path / "old.db")
    _upgrade(engine, "0008")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO feedback (rating, area, message, created_at) VALUES "
                          "(4, 'roadmap', 'one', '2026-11-11'), (NULL, NULL, 'none', '2026-11-11')"))
    _upgrade(engine)
    with engine.connect() as conn:
        got = conn.execute(text("SELECT message, areas FROM feedback ORDER BY id")).all()
    assert got == [("one", '["roadmap"]'), ("none", "[]")]
