"""Headless browser look: render JavaScript pages and list the price controls on a font page."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from fontfind import fetch, info

PRICE_WORDS = re.compile(r"(?:[$€£]|\b(?:USD|EUR|GBP|CHF)\b)\s?\d|\d[\d.,']*\s?(?:[$€£]|\b(?:USD|EUR|GBP|CHF)\b)", re.I)
CONTROLS_JS = """
() => {
  const label = el => {
    const id = el.id && document.querySelector(`label[for="${el.id}"]`);
    const near = el.closest('label, tr, li, div');
    return ((id && id.innerText) || el.getAttribute('aria-label') || (near && near.innerText) || el.name || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  };
  const out = [];
  document.querySelectorAll('select').forEach(s => out.push({kind: 'select', label: label(s),
    options: [...s.options].map(o => o.innerText.replace(/\\s+/g, ' ').trim()).filter(Boolean).slice(0, 12)}));
  const radios = {};
  document.querySelectorAll('input[type=radio]').forEach(r => { (radios[r.name] ||= []).push(label(r)); });
  Object.entries(radios).forEach(([n, opts]) => out.push({kind: 'choice', label: n, options: opts.slice(0, 12)}));
  document.querySelectorAll('input[type=number], input[type=range]').forEach(i => out.push({kind: 'number', label: label(i), options: []}));
  return out;
}
"""
TIMEOUT_MS = 30000


def _open(page, url: str) -> None:
    """Load a page; wait for scripts to settle, but never hang on sites that keep connections open."""
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass


class BrowserUnavailable(Exception):
    pass


def _launch(p):
    try:
        return p.chromium.launch()
    except Exception as e:  # browser not installed
        raise BrowserUnavailable(str(e)) from e


def render_text(url: str) -> str:
    """Page text after JavaScript has run."""
    from playwright.sync_api import sync_playwright

    if not fetch._allowed(url):
        raise fetch.FetchError(f"robots.txt disallows {url}")
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page(user_agent=fetch.USER_AGENT)
            _open(page, url)
            return fetch.html_to_text(page.content())
        except Exception as e:
            raise fetch.FetchError(f"{url}: {e}") from e
        finally:
            browser.close()


def product_pages(html: str, base_url: str, limit: int = 2) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.removeprefix("www.")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0].split("?")[0]
        parts = urlparse(url)
        if parts.netloc.removeprefix("www.") == host and info.TYPEFACE_PATH.search(parts.path) and url not in urls:
            urls.append(url)
    return urls[:limit]


def look(website: str) -> dict:
    """Render the homepage and a font page; return the price controls and visible prices found."""
    from playwright.sync_api import sync_playwright

    if not fetch._allowed(website):
        return {"checked": False, "reason": "robots.txt disallows"}
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page(user_agent=fetch.USER_AGENT)
            _open(page, website)
            candidates = product_pages(page.content(), page.url)
            for url in candidates:
                _open(page, url)
                controls = page.evaluate(CONTROLS_JS)
                prices = sorted(set(m.group(0).strip() for m in PRICE_WORDS.finditer(page.inner_text("body"))))[:8]
                if controls or prices:
                    return {"checked": True, "page": page.url, "controls": controls[:14], "prices": prices}
            return {"checked": bool(candidates), "page": candidates[0] if candidates else "", "controls": [], "prices": [],
                    "reason": "no price controls found on the font pages" if candidates else "no font page found"}
        except BrowserUnavailable:
            raise
        except Exception as e:
            return {"checked": False, "reason": str(e)[:120]}
        finally:
            browser.close()


def describe(observation: dict) -> str:
    """Plain text version of a look() result for the review prompt."""
    if not observation.get("checked"):
        return f"The font page could not be inspected ({observation.get('reason', 'unknown reason')})."
    lines = [f"Rendered font page: {observation['page']}"]
    if observation["prices"]:
        lines.append("Visible prices: " + ", ".join(observation["prices"]))
    if not observation["controls"]:
        lines.append("No price controls (dropdowns, choices, number fields) were found on the page.")
    for c in observation["controls"]:
        options = "; ".join(c["options"]) if c["options"] else "(free input)"
        lines.append(f"- {c['kind']} \"{c['label']}\": {options}")
    return "\n".join(lines)
