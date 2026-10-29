"""Fetch each foundry's license pages, snapshot them and classify the text."""

from __future__ import annotations

import datetime as dt
import hashlib
import sys

from fontfind import classify, db, discover, fetch


def _snapshot_path(foundry: dict, url: str):
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return db.SNAPSHOT_DIR / db.slugify(foundry["name"]) / f"{digest}.txt"


def _page_text(foundry: dict, url: str, offline: bool) -> str:
    path = _snapshot_path(foundry, url)
    if offline:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    text = fetch.fetch_text(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"URL: {url}\n\n{text}", encoding="utf-8")
    return text


def scrape_one(foundry: dict, offline: bool = False) -> dict:
    urls = list(foundry.get("license_urls") or [])
    errors = []
    if not urls and foundry.get("website") and not offline:
        try:
            urls = discover.discover(foundry["website"])
            foundry["license_urls"] = urls
        except fetch.FetchError as e:
            errors.append(str(e))

    texts = []
    for url in urls:
        try:
            texts.append(_page_text(foundry, url, offline))
        except fetch.FetchError as e:
            errors.append(str(e))

    combined = "\n".join(texts)
    content_hash = hashlib.sha256(combined.encode()).hexdigest()[:16] if combined else None
    previous = (foundry.get("auto") or {}).get("content_hash")

    auto = classify.classify(combined).as_dict() if combined else {}
    auto["checked"] = dt.date.today().isoformat()
    auto["content_hash"] = content_hash
    auto["changed_since_last_check"] = bool(previous and content_hash and previous != content_hash)
    if errors:
        auto["errors"] = errors
    foundry["auto"] = auto
    return auto


def scrape(only: list[str] | None = None, offline: bool = False) -> int:
    foundries = db.load()
    targets = [f for f in foundries if not only or db.slugify(f["name"]) in {db.slugify(n) for n in only}]
    if not targets:
        print("no matching foundries", file=sys.stderr)
        return 1
    for f in targets:
        print(f"• {f['name']}", flush=True)
        auto = scrape_one(f, offline=offline)
        for err in auto.get("errors", []):
            print(f"    error: {err}")
        if "suggested_qualifies" in auto:
            flag = "  (license text CHANGED)" if auto["changed_since_last_check"] else ""
            print(
                f"    metric={auto['suggested_metric']} logo={auto['suggested_logo']} "
                f"→ {auto['suggested_qualifies']} (database says: {f.get('qualifies', '?')}){flag}"
            )
        db.save(foundries)  # save as we go so an interrupted run keeps its work
    return 0
