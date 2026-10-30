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

import requests

from fontfind import db, discover, fetch

MAX_PAGE_CHARS = 30000
MODEL = os.environ.get("FONTFIND_MODEL", "claude-sonnet-5-5")
METHOD = "auto-reviewed (claude, quotes checked)"
PROTECTED = ("page-read",)

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


def gather(foundry: dict) -> dict[str, str]:
    urls = list(foundry.get("license_urls") or [])
    if not urls and foundry.get("website"):
        urls = discover.discover(foundry["website"])
    pages = {}
    for url in urls[:6]:
        try:
            pages[url] = fetch.fetch_text(url)[:MAX_PAGE_CHARS]
        except fetch.FetchError as e:
            print(f"    could not read {url}: {e}", file=sys.stderr)
    return pages


def _complete(prompt: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]},
            timeout=300,
        )
        if not resp.ok:
            raise RuntimeError(f"API {resp.status_code}: {resp.text[:200]}")
        return "".join(b.get("text", "") for b in resp.json().get("content", []))
    proc = subprocess.run(["claude", "-p", "--output-format", "json"], input=prompt, capture_output=True, text=True, timeout=600)
    data = json.loads(proc.stdout or "{}")
    if proc.returncode != 0 or data.get("is_error"):
        raise RuntimeError(data.get("result") or proc.stderr.strip() or "claude failed (set ANTHROPIC_API_KEY or run `claude` to log in)")
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


def review_one(foundry: dict) -> bool:
    pages = gather(foundry)
    if not pages:
        print("    no readable license pages")
        return False
    body = "\n\n".join(f"=== PAGE {url} ===\n{text}" for url, text in pages.items())
    verdict = ask_claude(PROMPT.format(name=foundry["name"], pages=body))
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
    print(f"    -> {qualifies} ({len(evidence)} quotes verified)")
    return True


def review(only: list[str] | None = None, force: bool = False) -> int:
    foundries = db.load()
    wanted = {db.slugify(n) for n in only or []}

    def needs_review(f: dict) -> bool:
        method = (f.get("verified") or {}).get("method", "")
        if wanted:
            return db.slugify(f["name"]) in wanted
        return "not reviewed" in method or (force and not method.startswith(PROTECTED))

    targets = [f for f in foundries if needs_review(f)]
    print(f"reviewing {len(targets)} foundries", flush=True)
    for f in targets:
        print(f"• {f['name']}", flush=True)
        try:
            review_one(f)
        except Exception as e:  # keep going; one bad foundry should not stop the batch
            print(f"    error: {e}", file=sys.stderr)
        db.save(foundries)
    return 0
