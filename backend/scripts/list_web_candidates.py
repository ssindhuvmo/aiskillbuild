"""List web resources that users approved and that are not in the knowledge base yet, most approved
first, so good ones can be promoted into data/knowledge_base.json.

    cd backend && python scripts/list_web_candidates.py          # table
    cd backend && python scripts/list_web_candidates.py --json   # entries ready to paste into "resources"

Review each entry before pasting it: pick a readable id, check the tags, level, hours and description,
then run scripts/check_kb_links.py. Once a URL is in the knowledge base it drops off this list.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import OperationalError  # noqa: E402

from core.agents.course_search.search import url_key  # noqa: E402
from core.db import SessionLocal  # noqa: E402
from core.knowledge.store import load_knowledge_base  # noqa: E402
from core.models import WebResourceCandidate  # noqa: E402


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "resource"


def main() -> int:
    curated = {url_key(r.url) for r in load_knowledge_base().resources}
    try:
        with SessionLocal() as db:
            rows = db.query(WebResourceCandidate).all()
    except OperationalError:
        print("No web_resource_candidates table yet: start the backend once so the database is migrated.")
        return 1
    rows = [r for r in rows if url_key(r.resource["url"]) not in curated]
    rows.sort(key=lambda r: (r.approvals, r.last_approved_at), reverse=True)
    if "--json" in sys.argv:
        print(json.dumps([{**r.resource, "id": slug(r.resource["title"])} for r in rows], indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        res = r.resource
        print(f"{r.approvals:3}x  {res['title']} ({res['provider']})")
        print(f"      {res['url']}")
        print(f"      {res['format']}, {res['level']}, {res['cost']}, {res['hours']} h; tags {res['skills']}; "
              f"approved for {', '.join(r.gaps)}; last {r.last_approved_at:%Y-%m-%d}")
    print(f"{len(rows)} approved web resources not in the knowledge base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
