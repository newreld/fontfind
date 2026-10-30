"""Automatic review: Claude reads a foundry's license pages and fills in the verdict.

Every evidence quote must appear word for word in a fetched page, otherwise it is dropped,
and a verdict that rests on no verified quote is capped at 'likely'.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from fontfind import browser, db, discover, fetch, progress

MAX_PAGE_CHARS = 30000
MODEL = os.environ.get("FONTFIND_MODEL", "claude-sonnet-5-5")
METHOD = "auto-reviewed (rendered page, second check)"
PROTECTED = ("browser-reviewed",)

PROMPT = """You are reviewing the font license of one type foundry. Use ONLY the page texts below. Never use outside knowledge.

Goal: does the foundry sell ONE license priced by company size (employee count / headcount) that covers web use, logo use and all media?

Fields:
- pricing_metric: company_size | mixed | seats | traffic | unknown   (what the price actually scales with; company_size only if employee count / company size is the price input and not users, computers, pageviews, followers or downloads)
- logo: included | separate | separate_size_based | restricted | unknown
- all_media: yes (print, web, apps, social etc. in one license) | partial | no | unknown
- web: yes (web use included in the company-size license, no pageview pricing or separate web license) | no | unknown
- qualifies: yes (company_size AND logo included AND all_media yes AND web yes) | likely (looks like a match, one point unconfirmed) | partial (company size pricing but logo, web or media is extra) | no (not priced by company size) | unknown (text insufficient)
- summary: 1-3 plain sentences.
- evidence: 2-5 items {{"claim": short statement, "quote": EXACT verbatim text copied from a page, max 300 chars, "source": the page URL}}.
- todo: what is unconfirmed, or "".

If a point is not stated in the text, use unknown. Reply with ONLY one JSON object with keys pricing_metric, logo, all_media, web, qualifies, summary, evidence, todo.

Foundry: {name}

BROWSER OBSERVATIONS (a real browser rendered one font page and listed every price control on it; if any control asks for users, computers, pageviews, visitors, followers, downloads, apps or domains, the price is NOT set by company size alone):
{observations}

{pages}
"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).strip().lower()


def _read_pages(urls: list[str]) -> tuple[dict[str, str], list[str]]:
    pages, errors = {}, []
    for url in urls[:6]:
        try:
            pages[url] = fetch.fetch_text(url)[:MAX_PAGE_CHARS]
        except fetch.FetchError as e:
            errors.append(str(e))
    return pages, errors


def gather(foundry: dict) -> tuple[dict[str, str], list[str]]:
    """Read the stored license pages; if none can be read, rediscover them, then try common paths."""
    pages, errors = _read_pages(list(foundry.get("license_urls") or []))
    site = foundry.get("website")
    if not pages and site:
        try:
            pages, more = _read_pages(discover.discover(site))
            errors += more
        except fetch.FetchError as e:
            errors.append(str(e))
    if not pages and site:
        pages, more = _read_pages(discover.fallback(site))
        errors += more
    return pages, errors


SKEPTIC_PROMPT = """A reviewer concluded that this type foundry sells ONE license priced by company size (employee count) that covers web use, logo use and all media. Your only job is to try to DISPROVE that, using ONLY the texts below.

Look for: other price inputs (users, computers, pageviews, visitors, followers, downloads, number of apps or domains, revenue); separate or extra licenses or fees for web, logo, trademark registration, social media, apps, broadcast, film, TV, video or other media; conditions that exclude web or logo; "contact us" or custom licenses for common uses.

Do NOT object to these, they are normal scope limits and not extra licenses: web use being limited to one named domain or the licensee's own sites; subsidiaries, affiliates or agencies needing to be added; how headcount is counted; perpetual vs annual terms; prohibitions on redistributing or modifying the fonts. Small amounts shown on a page (like "$2") are not an objection unless the text says what they are for. An objection must be about a PRICE INPUT other than company size, or a separate paid license/fee for web, logo or a media type that the main license does not cover.

Reviewer's verdict: {verdict}

Reply with ONLY one JSON object: {{"objections": [{{"point": short statement, "quote": EXACT verbatim text copied from below, max 300 chars}}], "still_yes": true or false, "downgrade_to": "partial" (a known extra license or fee exists) or "likely" (something is unclear)}}.
Use still_yes false only if a verified objection shows it is not a full match.

BROWSER OBSERVATIONS:
{observations}

{pages}
"""


_children: set = set()


def kill_children() -> None:
    """Stop any claude processes still running (used when the user aborts)."""
    for proc in list(_children):
        proc.kill()


def _complete(prompt: str, tools: str = "") -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}],
                  **({"tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]} if tools else {})},
            timeout=300,
        )
        if not resp.ok:
            raise RuntimeError(f"API {resp.status_code}: {resp.text[:200]}")
        return "".join(b.get("text", "") for b in resp.json().get("content", []))
    cmd = ["claude", "-p", "--output-format", "json"] + (["--allowedTools", tools] if tools else [])
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _children.add(proc)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=600)
    finally:
        _children.discard(proc)
    data = json.loads(stdout or "{}") if proc.returncode == 0 else {}
    if proc.returncode != 0 or data.get("is_error"):
        raise RuntimeError(data.get("result") or (stderr or "").strip() or "claude failed (set ANTHROPIC_API_KEY or run `claude` to log in)")
    return data.get("result", "")


def _first_json_object(text: str) -> dict:
    """The first complete JSON object in a reply, ignoring any prose or stray braces around it."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    raise RuntimeError("no JSON object in the reply")


def ask_claude(prompt: str, attempts: int = 2) -> dict:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return _first_json_object(_complete(prompt))
        except RuntimeError as e:
            last = e
    raise last  # type: ignore[misc]


def verified_evidence(items: list[dict], pages: dict[str, str]) -> list[dict]:
    normalised = {url: _norm(text) for url, text in pages.items()}
    kept = []
    for item in items or []:
        quote = _norm(str(item.get("quote", "")))
        if len(quote) < 20:
            continue
        for url, text in normalised.items():
            if quote in text:
                kept.append({"claim": f'{item.get("claim", "").strip()} "{item["quote"].strip()}"'.strip(), "source": url})
                break
    return kept


def _page_block(pages: dict[str, str]) -> str:
    return "\n\n".join(f"=== PAGE {url} ===\n{text}" for url, text in pages.items())


def assess(foundry: dict) -> tuple[dict, dict[str, str], dict] | list[str]:
    """Read the pages, look at a rendered font page, ask Claude, then let a second call try to disprove a yes.
    Returns the list of errors when no page could be read. Touches no shared state, so it is thread-safe."""
    pages, errors = gather(foundry)
    if not pages:
        return errors or ["no license page found"]
    try:
        observation = browser.look(foundry["website"]) if foundry.get("website") else {"checked": False, "reason": "no website"}
    except browser.BrowserUnavailable:
        observation = {"checked": False, "reason": "browser not installed (run: python3 -m playwright install chromium)"}
    observations = browser.describe(observation)
    verdict = ask_claude(PROMPT.format(name=foundry["name"], observations=observations, pages=_page_block(pages)))
    check = {}
    if verdict.get("qualifies") == "yes":
        check = ask_claude(SKEPTIC_PROMPT.format(verdict=json.dumps(verdict)[:3000], observations=observations, pages=_page_block(pages)))
    return verdict, {**pages, "(browser observations)": observations}, {"observation": observation, "check": check}


def apply(foundry: dict, verdict: dict, pages: dict[str, str], extra: dict | None = None) -> str:
    extra = extra or {}
    evidence = verified_evidence(verdict.get("evidence"), pages)
    qualifies = verdict.get("qualifies", "unknown")
    notes: list[str] = []
    if qualifies == "yes":
        objections = verified_evidence(extra.get("check", {}).get("objections"), pages)
        if extra.get("check", {}).get("still_yes") is False and objections:
            qualifies = extra["check"].get("downgrade_to") if extra["check"].get("downgrade_to") in ("partial", "likely") else "likely"
            evidence += objections
            notes.append("A second check found a problem: " + objections[0]["claim"][:200])
        elif len(evidence) < 2 or verdict.get("web") != "yes":
            qualifies = "likely"
            notes.append("Fewer than two quotes could be verified or web use is not confirmed.")
        elif not extra.get("observation", {}).get("checked"):
            qualifies = "likely"
            notes.append(f"Price options on a font page could not be inspected ({extra.get('observation', {}).get('reason', 'unknown')}).")
    verdict["todo"] = " ".join(filter(None, [(verdict.get("todo") or "").strip(), *notes]))
    foundry.update({
        "pricing_metric": verdict.get("pricing_metric", "unknown"),
        "logo": verdict.get("logo", "unknown"),
        "all_media": verdict.get("all_media", "unknown"),
        "qualifies": qualifies,
        "summary": verdict.get("summary", ""),
        "evidence": evidence,
        "license_urls": [u for u in pages if u.startswith("http")],
        "verified": {"date": dt.date.today().isoformat(), "method": METHOD},
    })
    if verdict["todo"]:
        foundry["todo"] = verdict["todo"]
    else:
        foundry.pop("todo", None)
    return f"{qualifies} ({len(evidence)} quotes verified)"


RETRY_AFTER_DAYS = 7
FAILED = "review failed"


def mark_unreadable(foundry: dict, errors: list[str]) -> str:
    reason = "; ".join(sorted({re.sub(r"^https?://\S+: ", "", e) for e in errors}))[:200] or "no license page found"
    foundry["verified"] = {"date": dt.date.today().isoformat(), "method": f"{FAILED} (license pages unreadable)"}
    foundry["todo"] = f"License pages could not be read: {reason}. Retried automatically after {RETRY_AFTER_DAYS} days, or run `review --force`."
    return reason


def review_one(foundry: dict) -> bool:
    result = assess(foundry)
    if isinstance(result, list):
        print(f"    {mark_unreadable(foundry, result)}")
        return False
    print(f"    -> {apply(foundry, *result)}")
    return True


def needs_review(f: dict) -> bool:
    verified = f.get("verified") or {}
    method = str(verified.get("method", ""))
    if method.startswith(FAILED):
        try:
            age = (dt.date.today() - dt.date.fromisoformat(str(verified.get("date")))).days
        except ValueError:
            return True
        return age >= RETRY_AFTER_DAYS
    return "not reviewed" in method or method == "search-snippet"


def pending_count() -> int:
    return sum(1 for f in db.load() if needs_review(f))


def review(only: list[str] | None = None, force: bool = False, limit: int | None = None, dry_run: bool = False, workers: int = 4) -> int:
    foundries = db.load()
    wanted = {db.slugify(n) for n in only or []}

    def wanted_now(f: dict) -> bool:
        method = (f.get("verified") or {}).get("method", "")
        if wanted:
            return db.slugify(f["name"]) in wanted
        return needs_review(f) or (force and not method.startswith(PROTECTED))

    targets = [f for f in foundries if wanted_now(f)][:limit]
    print(f"reviewing {len(targets)} foundries ({workers} at a time)", flush=True)
    progress.total(len(targets))
    unreadable: list[str] = []
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(assess, f): f for f in targets}
        for fut in as_completed(futures):
            f = futures[fut]
            progress.tick(f["name"])
            try:
                result = fut.result()
            except Exception as e:  # keep going; one bad foundry should not stop the batch
                print(f"  {f['name']}: error: {e}", flush=True)
                continue
            if isinstance(result, list):
                reason = mark_unreadable(f, result)
                unreadable.append(f["name"])
                print(f"  {f['name']}: could not read license pages ({reason[:60]})", flush=True)
            else:
                print(f"  {f['name']}: {apply(f, *result)}", flush=True)
            if dry_run and f.get("todo"):
                print(f"    note: {f['todo'][:300]}", flush=True)
            if not dry_run:
                db.save(foundries)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if unreadable:
        print(f"{len(unreadable)} could not be read and will be retried in {RETRY_AFTER_DAYS} days: {', '.join(unreadable)}")
    return 0
