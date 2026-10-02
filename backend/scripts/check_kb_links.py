"""Check that every knowledge-base URL resolves. Needs the network, so it is not part of pytest.

    cd backend && python scripts/check_kb_links.py

Exits 1 if any link fails. Some sites refuse automated requests (HTTP 403/429); those are
reported as "blocked" so you can open them in a browser, and don't count as failures.
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import core.config  # noqa: E402,F401  (injects truststore: the OS certificate store verifies HTTPS)
from core.knowledge.store import load_knowledge_base  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (AI Career Strategist link check)"}
BLOCKED = {401, 403, 429}


def check(url: str) -> tuple[str, str]:
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=20)
        if r.status_code >= 400:  # some servers reject HEAD; retry with GET
            r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=20, stream=True)
        if r.status_code < 400:
            return "ok", str(r.status_code)
        return ("blocked" if r.status_code in BLOCKED else "fail"), str(r.status_code)
    except requests.RequestException as e:
        return "fail", type(e).__name__


def main() -> int:
    resources = load_knowledge_base().resources
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda r: (r, *check(str(r.url))), resources))
    for r, status, detail in results:
        if status != "ok":
            print(f"{status.upper():8} {detail:>20}  {r.id}  {r.url}")
    failed = sum(status == "fail" for _, status, _ in results)
    blocked = sum(status == "blocked" for _, status, _ in results)
    print(f"{len(results)} links: {len(results) - failed - blocked} ok, {blocked} blocked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
