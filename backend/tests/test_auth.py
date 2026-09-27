"""Google sign-in, sessions, and per-user data isolation (Google verification is faked)."""
import base64
import json

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login

PROTECTED = [
    ("get", "/api/auth/me", None),
    ("get", "/api/domains", None),
    ("get", "/api/intake", None),
    ("post", "/api/intake/chat", {"message": "hi"}),
    ("put", "/api/profile", {"hours_per_week": 5}),
    ("post", "/api/profile/confirm", None),
]


def test_endpoints_require_login(anon):
    for method, path, body in PROTECTED:
        r = getattr(anon, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 401, (method, path)
    assert anon.get("/api/health").status_code == 200


def test_invalid_token_rejected(anon):
    r = anon.post("/api/auth/google", json={"credential": "forged"})
    assert r.status_code == 401
    assert anon.get("/api/auth/me").status_code == 401


def test_login_session_cookie_and_logout(anon):
    r = anon.post("/api/auth/google", json={"credential": "good:alice"})
    assert r.json() == {"email": "alice@example.com", "name": "User alice", "picture": "https://example.com/alice.png"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert anon.get("/api/auth/me").json()["name"] == "User alice"
    assert anon.post("/api/auth/logout").status_code == 200
    assert anon.get("/api/auth/me").status_code == 401


def test_tampered_cookie_rejected(anon):
    login(anon, "victim")
    login(anon, "mallory")
    # Keep mallory's valid timestamp and signature but swap the payload to claim victim's sub.
    _, ts, sig = anon.cookies.get("session").split(".")
    forged = base64.b64encode(json.dumps({"uid": "victim"}).encode()).decode()
    anon.cookies.clear()
    anon.cookies.set("session", f"{forged}.{ts}.{sig}")
    assert anon.get("/api/auth/me").status_code == 401


def test_users_only_see_their_own_data(anon):
    alice = login(anon, "alice2")
    assert alice.put("/api/profile", json={"current_role": "Backend Engineer"}).status_code == 200
    with TestClient(app, base_url="https://testserver") as other:
        bob = login(other, "bob")
        assert bob.get("/api/intake").json()["profile"]["current_role"] is None
        assert bob.put("/api/profile", json={"current_role": "Data Analyst"}).status_code == 200
    assert alice.get("/api/intake").json()["profile"]["current_role"] == "Backend Engineer"


def test_relogin_keeps_data_and_refreshes_name(anon, monkeypatch):
    login(anon, "carol")
    anon.put("/api/profile", json={"hours_per_week": 8})
    anon.post("/api/auth/logout")
    from core import auth
    from tests.conftest import fake_verify

    monkeypatch.setattr(auth, "verify_google_token", lambda c: {**fake_verify(c), "name": "Carol New"})
    assert login(anon, "carol").get("/api/auth/me").json()["name"] == "Carol New"
    assert anon.get("/api/intake").json()["profile"]["hours_per_week"] == 8
