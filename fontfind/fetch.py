"""Polite page fetching: robots.txt, rate limiting, HTML/PDF to text."""

from __future__ import annotations

import io
import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "FontFind/0.1 (license research; +https://github.com/newreld/fontfind)"
DELAY_SECONDS = 2.0

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_request: dict[str, float] = {}
_lock = threading.Lock()
MAX_CRAWL_DELAY = 15.0
TOTAL_SECONDS = 60
MAX_BYTES = 15_000_000


class FetchError(Exception):
    pass


def _session() -> requests.Session:
    """A fresh session that gives up on endless redirect chains."""
    s = requests.Session()
    s.max_redirects = 5
    s.headers["User-Agent"] = USER_AGENT
    return s


def _allowed(url: str) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = _session().get(base + "/robots.txt", timeout=(8, 15))
            rp.parse(resp.text.splitlines() if resp.ok else [])
            _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def _delay_for(url: str) -> float:
    parts = urlparse(url)
    rp = _robots.get(f"{parts.scheme}://{parts.netloc}")
    declared = rp.crawl_delay(USER_AGENT) if rp else None
    return min(max(DELAY_SECONDS, float(declared or 0)), MAX_CRAWL_DELAY)


def _throttle(host: str, delay: float) -> None:
    # Reserve the next slot under the lock, then sleep outside it.
    with _lock:
        now = time.monotonic()
        slot = max(now, _last_request.get(host, 0.0) + delay)
        _last_request[host] = slot
    if slot > now:
        time.sleep(slot - now)


def get(url: str) -> requests.Response:
    if not _allowed(url):
        raise FetchError(f"robots.txt disallows {url}")
    _throttle(urlparse(url).netloc, _delay_for(url))
    try:
        resp = _session().get(url, timeout=(8, 30), stream=True)
        deadline, body = time.time() + TOTAL_SECONDS, bytearray()
        for chunk in resp.iter_content(65536):  # a slow-drip server must not stall the run
            body += chunk
            if time.time() > deadline or len(body) > MAX_BYTES:
                raise FetchError(f"{url}: too slow or too large")
        resp._content = bytes(body)
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
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # encrypted, damaged or unsupported PDF
        raise FetchError(f"could not read PDF: {e}") from e


def fetch_text(url: str) -> str:
    resp = get(url)
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        return pdf_to_text(resp.content)
    return html_to_text(resp.text)
