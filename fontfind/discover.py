"""Find license/EULA/FAQ pages on a foundry website."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from fontfind import fetch

LICENSE_HINT = re.compile(r"licen[cs]|eula|terms|faq|pricing|information|legal", re.I)
STRONG_HINT = re.compile(r"licen[cs]|eula", re.I)
MAX_LINKS = 6


def license_links(html: str, base_url: str) -> list[str]:
    """Same-site links that look like license pages, strongest first."""
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.removeprefix("www.")
    scored: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or parts.netloc.removeprefix("www.") != host:
            continue
        haystack = f"{parts.path} {a.get_text(' ', strip=True)}"
        if not LICENSE_HINT.search(haystack):
            continue
        score = 2 if STRONG_HINT.search(haystack) else 1
        scored[url] = max(scored.get(url, 0), score)
    ranked = sorted(scored, key=lambda u: (-scored[u], len(u)))
    return ranked[:MAX_LINKS]


def discover(website: str) -> list[str]:
    resp = fetch.get(website)
    return license_links(resp.text, resp.url)
