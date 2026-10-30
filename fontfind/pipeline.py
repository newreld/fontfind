"""One command that finds foundries, reviews them and rebuilds the report."""

from __future__ import annotations

import collections

import yaml

from fontfind import crawl, db, info, report, review

SOURCES_PATH = db.ROOT / "data" / "sources.yaml"
STEPS = ["discover", "screen", "promote", "review", "info", "report"]


def _sources() -> dict:
    return yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or {}


def _tally() -> collections.Counter:
    return collections.Counter(f.get("qualifies", "unknown") for f in db.load())


def update(steps: list[str] | None = None, limit: int = 25, deep: bool = False) -> int:
    steps = steps or STEPS
    before = _tally()
    src = _sources()

    if "discover" in steps:
        print("\n== Discover ==", flush=True)
        crawl.add_seed_sites(src.get("seeds") or [])
        crawl.add_roundup_pages(src.get("roundups") or [])
        crawl.add_searched_sites(src.get("searches") or [])
        crawl.peers()
        if deep:
            crawl.sources()
    if "screen" in steps:
        print("\n== Screen ==", flush=True)
        crawl.screen()
    if "promote" in steps:
        print("\n== Promote candidates ==", flush=True)
        crawl.promote()
    if "review" in steps:
        print(f"\n== Review (up to {limit}) ==", flush=True)
        review.review(limit=limit)
    if "info" in steps:
        print("\n== Foundry info ==", flush=True)
        info.collect()
    if "report" in steps:
        print("\n== Report ==", flush=True)
        print(report.build())

    after = _tally()
    print("\nSummary (before -> after)")
    for q in ("yes", "likely", "partial", "unknown", "no"):
        print(f"  {q:8} {before[q]:3} -> {after[q]:3}")
    pending = sum(1 for f in db.load() if "not reviewed" in (f.get("verified") or {}).get("method", ""))
    if pending:
        print(f"  {pending} candidates still waiting for review: run update again")
    return 0
