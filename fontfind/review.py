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

from fontfind import db, discover, fetch, progress

MAX_PAGE_CHARS = 30000
MODEL = os.environ.get("FONTFIND_MODEL", "claude-sonnet-5-5")
METHOD = "auto-reviewed (claude, quotes checked)"
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


def ask_claude(prompt: str) -> dict:
    result = _complete(prompt)
    match = re.search(r"\{.*\}", result, re.S)
    if not match:
        raise RuntimeError("no JSON in reply")
    return json.loads(match.group(0))


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


def assess(foundry: dict) -> tuple[dict, dict[str, str]] | list[str]:
    """Fetch the pages and ask Claude. Returns the list of errors when no page could be read.
    No shared state is touched, so it is safe to run in threads."""
    pages, errors = gather(foundry)
    if not pages:
        return errors or ["no license page found"]
    body = "\n\n".join(f"=== PAGE {url} ===\n{text}" for url, text in pages.items())
    return ask_claude(PROMPT.format(name=foundry["name"], pages=body)), pages


def apply(foundry: dict, verdict: dict, pages: dict[str, str]) -> str:
    evidence = verified_evidence(verdict.get("evidence"), pages)
    qualifies = verdict.get("qualifies", "unknown")
    if qualifies == "yes" and (len(evidence) < 2 or verdict.get("web") != "yes"):
        qualifies = "likely"
        verdict["todo"] = (verdict.get("todo") or "Fewer than two quotes could be verified or web use is not confirmed.").strip()
    foundry.update({
        "pricing_metric": verdict.get("pricing_metric", "unknown"),
        "logo": verdict.get("logo", "unknown"),
        "all_media": verdict.get("all_media", "unknown"),
        "qualifies": qualifies,
        "summary": verdict.get("summary", ""),
        "evidence": evidence,
        "license_urls": list(pages),
        "verified": {"date": dt.date.today().isoformat(), "method": METHOD},
    })
    if verdict.get("todo"):
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
            if not dry_run:
                db.save(foundries)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if unreadable:
        print(f"{len(unreadable)} could not be read and will be retried in {RETRY_AFTER_DAYS} days: {', '.join(unreadable)}")
    return 0
