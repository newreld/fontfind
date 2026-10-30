"""One command that finds foundries, reviews them and rebuilds the report."""

from __future__ import annotations

import collections

import yaml

import sys

from fontfind import crawl, db, info, report, review, status

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
    st = status.Status(steps)
    real_stdout = sys.stdout
    sys.stdout = status.Tee(st, real_stdout, echo=not real_stdout.isatty())
    live = None
    if real_stdout.isatty():
        from rich.live import Live

        live = Live(status.terminal_view(st), refresh_per_second=8, redirect_stdout=False, redirect_stderr=False)
        live.start()
        st.view = live
    st.refresh()
    try:
        _run(steps, limit, deep, src, st)
    finally:
        sys.stdout = real_stdout
        st.finish()
        if live:
            live.update(status.terminal_view(st))
            live.stop()

    after = _tally()
    print("\nSummary (before -> after)")
    for q in ("yes", "likely", "partial", "unknown", "no"):
        print(f"  {q:8} {before[q]:3} -> {after[q]:3}")
    pending = review.pending_count()
    if pending:
        print(f"  {pending} candidates still waiting for review: run update again")
    return 0


def _run(steps: list[str], limit: int, deep: bool, src: dict, st: "status.Status") -> None:

    if "discover" in steps:
        st.start("discover")
        crawl.add_seed_sites(src.get("seeds") or [])
        crawl.add_roundup_pages(src.get("roundups") or [])
        crawl.add_searched_sites(src.get("searches") or [])
        crawl.peers()
        if deep:
            crawl.sources()
    if "screen" in steps:
        st.start("screen")
        crawl.screen()
    if "promote" in steps:
        st.start("promote")
        crawl.promote()
    if "review" in steps:
        st.start("review")
        review.review(limit=limit)
    if "info" in steps:
        st.start("info")
        info.collect()
    if "report" in steps:
        st.start("report")
        print(report.build())
