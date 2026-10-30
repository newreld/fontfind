"""Collect display info for each foundry: preview image, description, typeface names."""

from __future__ import annotations

import re
import sys
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from fontfind import db, fetch

TYPEFACE_PATH = re.compile(r"/(?:typefaces?|fonts?|families|family|fontfamily|products?|collections?|projects?|shop|catalog(?:ue)?)/([^/?#]+)/?$", re.I)
NOT_TYPEFACE = re.compile(
    r"^(?:all|new|free|trial|trials|cart|licen[cs]\w*|about|contact|news|journal|blog|faq|info\w*|"
    r"custom|studio|search|login|account|shop|store|fonts?|typefaces?|families|collections?|bundles?|"
    r"gift\w*|prints?|posters?|merch|home|index|more|view all|see all|read more|buy|download\w*|"
    r"specimens?|tester|type tester|support|legal|privacy|terms|eula|newsletter|instagram)$",
    re.I,
)
MAX_TYPEFACES = 24


def meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return ""


def typefaces_from(soup: BeautifulSoup, base_url: str) -> list[str]:
    host = urlparse(base_url).netloc.removeprefix("www.")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        parts = urlparse(urljoin(base_url, a["href"]))
        if parts.netloc.removeprefix("www.") != host or not TYPEFACE_PATH.search(parts.path):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        if "/" in text or re.match(r"(?i)^(?:see|view|buy|shop|read|learn|discover|get|more)\b", text):
            slug = TYPEFACE_PATH.search(parts.path).group(1)
            text = re.sub(r"[-_]+", " ", slug).title()
        if 2 <= len(text) <= 32 and not NOT_TYPEFACE.match(text) and text.lower() not in {t.lower() for t in seen}:
            seen[text] = None
    return list(seen)[:MAX_TYPEFACES]


def info_for(website: str) -> dict:
    resp = fetch.get(website)
    soup = BeautifulSoup(resp.text, "html.parser")
    out = {}
    image = meta(soup, "og:image", "twitter:image")
    if image:
        out["image"] = urljoin(resp.url, image)
    description = meta(soup, "og:description", "description", "twitter:description")
    if description:
        out["description"] = " ".join(description.split())[:300]
    typefaces = typefaces_from(soup, resp.url)
    if typefaces:
        out["typefaces"] = typefaces
    return out


def collect(only: list[str] | None = None, force: bool = False) -> int:
    foundries = db.load()
    targets = [
        f for f in foundries
        if f.get("website") and f.get("qualifies") != "no"
        and (not only or db.slugify(f["name"]) in {db.slugify(n) for n in only})
        and (force or "info" not in f)
    ]
    for f in targets:
        print(f"• {f['name']}", flush=True)
        try:
            found = info_for(f["website"])
        except fetch.FetchError as e:
            print(f"    error: {e}", file=sys.stderr)
            found = {}
        f["info"] = found
        print(f"    image={'y' if 'image' in found else '-'} typefaces={len(found.get('typefaces', []))}")
        db.save(foundries)
    return 0
