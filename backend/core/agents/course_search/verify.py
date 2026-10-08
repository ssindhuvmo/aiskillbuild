"""URL verification: does a link resolve? Used by the graph for every web result and by
scripts/check_kb_links.py for the knowledge base. HTTPS is verified with the OS certificate
store (truststore, injected in core.config)."""
import ipaddress
import socket
from collections.abc import Callable
from functools import partial
from urllib.parse import urlsplit

import requests

import core.config  # noqa: F401  (injects truststore)

HEADERS = {"User-Agent": "Mozilla/5.0 (AI Career Strategist link check)"}
BLOCKED = {401, 403, 429}  # the site refuses automated requests; the page may still be fine in a browser
TIMEOUT = 20
WEB_TIMEOUT = 10  # the user is waiting while web results are checked

Checker = Callable[[str], tuple[str, str]]


def _public_host(host: str) -> bool:
    """False for loopback, private and link-local addresses, so a link can't point the server at
    its own network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def check(url: str, timeout: float = TIMEOUT) -> tuple[str, str]:
    """Return (status, detail): status is "ok", "blocked" (HTTP 401/403/429) or "fail"."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "fail", "not an http(s) URL"
    if not _public_host(parts.hostname):
        return "fail", "not a public address"
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=timeout)
        if r.status_code >= 400:  # some servers reject HEAD; retry with GET
            r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=timeout, stream=True)
            r.close()
        if r.status_code < 400:
            return "ok", str(r.status_code)
        return ("blocked" if r.status_code in BLOCKED else "fail"), str(r.status_code)
    except requests.RequestException as e:
        return "fail", type(e).__name__


def get_checker() -> Checker:
    """The one place that picks the URL checker for web results (tests replace it)."""
    return partial(check, timeout=WEB_TIMEOUT)
