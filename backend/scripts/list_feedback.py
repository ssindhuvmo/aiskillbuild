"""List what users sent through the feedback form, newest first, with the average rating and counts per area
(a message about several areas counts once for each).

    cd backend && python scripts/list_feedback.py              # every message
    cd backend && python scripts/list_feedback.py --days 7     # only the last 7 days
    cd backend && python scripts/list_feedback.py --json       # as JSON

The sender's email is shown while the user still exists; after "Start over" the message is kept as "(anonymous)".
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import OperationalError  # noqa: E402

from core.db import SessionLocal  # noqa: E402
from core.models import Feedback, User  # noqa: E402


def _days() -> int | None:
    if "--days" not in sys.argv:
        return None
    i = sys.argv.index("--days")
    try:
        return int(sys.argv[i + 1])
    except (IndexError, ValueError):
        raise SystemExit("--days needs a number, e.g. --days 7")


def main() -> int:
    days = _days()
    try:
        with SessionLocal() as db:
            q = db.query(Feedback, User.email).outerjoin(User, Feedback.user_id == User.user_id)
            if days is not None:
                since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
                q = q.filter(Feedback.created_at >= since)
            rows = q.order_by(Feedback.created_at.desc()).all()
    except OperationalError:
        print("No feedback table yet: start the backend once so the database is migrated.")
        return 1
    if "--json" in sys.argv:
        out = [{"id": f.id, "created_at": f.created_at.isoformat(), "email": email, "rating": f.rating,
                "areas": f.areas, "message": f.message} for f, email in rows]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for f, email in rows:
        rating = f"{f.rating}/5" if f.rating else "no rating"
        print(f"{f.created_at:%Y-%m-%d %H:%M}  {email or '(anonymous)'}  {rating}  {', '.join(f.areas) or 'whole platform'}")
        for line in f.message.splitlines():
            print(f"    {line}")
        print()
    ratings = [f.rating for f, _ in rows if f.rating]
    average = f", average rating {sum(ratings) / len(ratings):.1f} of 5 ({len(ratings)} rated)" if ratings else ""
    print(f"{len(rows)} messages{average}")
    areas = Counter(a for f, _ in rows for a in (f.areas or ["whole platform"]))
    if areas:
        print("By area: " + ", ".join(f"{a} {n}" for a, n in areas.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
