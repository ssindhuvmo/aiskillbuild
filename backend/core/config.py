import json
import os
from pathlib import Path

import truststore
from dotenv import load_dotenv

# Verify HTTPS with the OS certificate store (the Windows store trusts this machine's
# proxy CA; Python's bundled certifi does not). Verification stays on.
truststore.inject_into_ssl()

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'career_strategist.db'}")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# SQLite file for the course search graph's checkpoints (the paused refinement chat per user).
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", str(BACKEND_DIR / "graph_checkpoints.db"))
# Uploaded resumes, one folder per user (gitignored; never served back to the browser).
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "uploads"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() not in ("0", "false", "no")
SESSION_MAX_AGE = 14 * 24 * 3600  # seconds

if not GOOGLE_CLIENT_ID or not SESSION_SECRET or SESSION_SECRET == "change-me":
    raise RuntimeError(
        "GOOGLE_CLIENT_ID and SESSION_SECRET must be set in backend/.env (see .env.example)."
    )


KB_PATH = BACKEND_DIR / "data" / "knowledge_base.json"


def load_domains() -> list[str]:
    with open(BACKEND_DIR / "config" / "domains.json", encoding="utf-8") as f:
        return json.load(f)["domains"]
