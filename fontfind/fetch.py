"""Polite page fetching: robots.txt, rate limiting, HTML/PDF to text."""

from __future__ import annotations

import io
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "FontFind/0.1 (license research; +https://github.com/newreld/fontfind)"
DELAY_SECONDS = 2.0

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_request: dict[str, float] = {}


class FetchError(Exception):
    pass


def _allowed(url: str) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(base + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
            rp.parse(resp.text.splitlines() if resp.ok else [])
            _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def _throttle(host: str) -> None:
    wait = DELAY_SECONDS - (time.monotonic() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def get(url: str) -> requests.Response:
    if not _allowed(url):
        raise FetchError(f"robots.txt disallows {url}")
    _throttle(urlparse(url).netloc)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        raise FetchError(f"{url}: {e}") from e
    if not resp.ok:
        raise FetchError(f"{url}: HTTP {resp.status_code}")
    return resp


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise FetchError("install pypdf to read PDF license files") from e
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_text(url: str) -> str:
    resp = get(url)
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return pdf_to_text(resp.content)
    return html_to_text(resp.text)
