"""One command that finds foundries, reviews them and rebuilds the report."""

from __future__ import annotations

import collections
import shutil
import sys

import yaml

from fontfind import crawl, db, info, progress, report, review, status

SOURCES_PATH = db.ROOT / "data" / "sources.yaml"
STEPS = ["roundups", "searches", "peers", "screen", "promote", "judge", "info", "report"]
PHASES = {
    "find": ["roundups", "searches", "peers"],
    "screen": ["screen", "promote"],
    "review": ["judge", "info", "report"],
}
ALIASES = dict(PHASES)


def _sources() -> dict:
    return yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or {}


def _tally() -> collections.Counter:
    return collections.Counter(f.get("qualifies", "unknown") for f in db.load())


def expand(names: list[str] | None, deep: bool) -> list[str]:
    steps = []
    for name in names or STEPS:
        steps.extend(ALIASES.get(name, [name]))
    if deep and "sources" not in steps:
        steps.insert(0, "sources")
    return [s for s in dict.fromkeys(steps)]


def update(steps: list[str] | None = None, limit: int = 25, deep: bool = False, title: str = "FontFind", review_opts: dict | None = None) -> int:
    steps = expand(steps, deep)
    before = _tally()
    src = _sources()
    shutil.copy2(db.DB_PATH, db.DB_PATH.with_name("foundries.yaml.bak"))

    st = status.Status(steps, title)
    progress.attach(st)
    real_stdout = sys.stdout
    sys.stdout = status.Tee(st, real_stdout, echo=not real_stdout.isatty())
    live = None
    if real_stdout.isatty():
        from rich.console import Console
        from rich.live import Live

        live = Live(status.terminal_view(st), console=Console(file=real_stdout), refresh_per_second=8, redirect_stdout=False, redirect_stderr=False)
        live.start()
        st.view = live
    aborted = False
    try:
        _run(steps, limit, src, st, review_opts or {})
    except KeyboardInterrupt:
        aborted = True
        review.kill_children()
    finally:
        sys.stdout = real_stdout
        progress.attach(None)
        st.finish(aborted=aborted)
        if live:
            live.update(status.terminal_view(st))
            live.stop()

    after = _tally()
    if aborted:
        print("\nStopped. Everything finished so far is saved. Run update again to continue where it left off.")
    print("\nSummary (before -> after)")
    for q in ("yes", "likely", "partial", "unknown", "no"):
        print(f"  {q:8} {before[q]:3} -> {after[q]:3}")
    pending = review.pending_count()
    if pending:
        print(f"  {pending} candidates still waiting for review: run `review` again")
    return 130 if aborted else 0


def run_phase(phase: str, limit: int = 25, deep: bool = False, **review_opts) -> int:
    steps = ["sources"] if (phase == "find" and deep) else PHASES[phase]
    if review_opts.get("dry_run"):
        steps = [s for s in steps if s == "judge"]
    return update(steps, limit=limit, deep=deep, title=phase.capitalize(), review_opts=review_opts)


def _run(steps: list[str], limit: int, src: dict, st: "status.Status", review_opts: dict) -> None:
    actions = {
        "sources": lambda: crawl.sources(),
        "roundups": lambda: (crawl.add_seed_sites(src.get("seeds") or []), crawl.add_roundup_pages(src.get("roundups") or [])),
        "searches": lambda: crawl.add_searched_sites(src.get("searches") or []),
        "peers": lambda: crawl.peers(),
        "screen": lambda: crawl.screen(),
        "promote": lambda: (progress.total(1), crawl.promote(), progress.tick("done")),
        "judge": lambda: review.review(limit=limit, **review_opts),
        "info": lambda: info.collect(),
        "report": lambda: (progress.total(1), print(report.build()), progress.tick("done")),
    }
    for step in steps:
        st.start(step)
        actions[step]()
