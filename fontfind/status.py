"""Live status page for `update`: data/status.html, refreshed while the pipeline runs."""

from __future__ import annotations

import collections
import html
import io
import json
import re
import sys
import time

from fontfind import crawl, db, review

PATH = db.ROOT / "data" / "status.html"
LABELS = {
    "discover": "Find foundries", "screen": "Screen license pages", "promote": "Pick candidates",
    "review": "Review with Claude", "info": "Images and typefaces", "report": "Build report",
}
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
__REFRESH__<title>FontFind update</title>
<style>
:root{--bg:#fbfaf8;--card:#fff;--fg:#14181f;--muted:#5f6672;--line:#e3e1dc;--accent:#1c3557;--yes:#1d6b4f;--likely:#245c7a;--partial:#8a5a14;--unknown:#5f6672}
@media(prefers-color-scheme:dark){:root{--bg:#0f1319;--card:#151b23;--fg:#eceef2;--muted:#9aa3b0;--line:#262d38;--accent:#9db8dc;--yes:#7fd0ac;--likely:#86c1dd;--partial:#e2b564;--unknown:#9aa3b0}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 20px 60px}
h1{font:600 34px/1.1 "Iowan Old Style",Georgia,serif;margin:0 0 6px}
.sub{color:var(--muted);margin:0 0 28px}
.steps{display:grid;gap:8px;margin-bottom:28px}
.step{display:flex;align-items:center;gap:12px;padding:12px 16px;border:1px solid var(--line);border-radius:6px;background:var(--card)}
.dot{width:12px;height:12px;border-radius:50%;border:2px solid var(--muted);flex:none}
.step.done .dot{background:var(--yes);border-color:var(--yes)}
.step.running{border-color:var(--accent)}
.step.running .dot{border-color:var(--accent);background:var(--accent);animation:p 1.2s ease-in-out infinite}
@keyframes p{50%{opacity:.3}}
.step b{flex:1;font-weight:600}.step span{color:var(--muted);font-size:13px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:28px}
.stat{border:1px solid var(--line);border-radius:6px;padding:12px 14px;background:var(--card)}
.stat b{display:block;font:600 26px/1 "Iowan Old Style",Georgia,serif}.stat span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:0 0 8px}
pre{margin:0;padding:14px 16px;border:1px solid var(--line);border-radius:6px;background:var(--card);font:12.5px/1.55 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto}
.fin{color:var(--yes);font-weight:600}
</style></head><body><main>
<h1>__TITLE__</h1><p class="sub">__SUB__</p>
<div class="steps">__STEPS__</div>
<div class="stats">__STATS__</div>
<h2>Latest activity</h2><pre>__LOG__</pre>
</main></body></html>"""


def terminal_view(status: "Status"):
    """A rich renderable of the current state, for the live terminal display."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.table import Table
    from rich.text import Text

    elapsed = int(time.time() - status.started)
    steps = Table.grid(padding=(0, 2), expand=True)
    steps.add_column(width=2)
    steps.add_column(ratio=1, no_wrap=True)
    steps.add_column(ratio=2, no_wrap=True, overflow="ellipsis")
    for name, state in status.steps.items():
        label = LABELS.get(name, name)
        if state == "done":
            steps.add_row(Text("✓", style="green"), Text(label, style="green"), Text(""))
        elif state == "running":
            steps.add_row(Spinner("dots", style="cyan"), Text(label, style="bold cyan"), Text(status.detail.get(name, ""), style="dim"))
        else:
            steps.add_row(Text("○", style="dim"), Text(label, style="dim"), Text(""))
    counts = status.counts()
    stats = Table.grid(padding=(0, 3))
    for _ in counts:
        stats.add_column(justify="center")
    stats.add_row(*[Text(str(n), style=f"bold {color}") for _, n, color in counts])
    stats.add_row(*[Text(label, style="dim") for label, _, _ in counts])
    recent = Text("\n".join(list(status.log)[-6:]), style="dim", no_wrap=True, overflow="ellipsis")
    title = "[bold green]Update finished[/]" if status.finished else "[bold]Update running[/]"
    return Panel(Group(steps, Text(""), stats, Text(""), recent), title=title, subtitle=f"{elapsed // 60}m {elapsed % 60:02d}s", padding=(1, 2))


class Status:
    def __init__(self, steps: list[str]):
        self.view = None
        self.steps = {s: "pending" for s in steps}
        self.detail: dict[str, str] = {}
        self.log: collections.deque[str] = collections.deque(maxlen=40)
        self.started = time.time()
        self.finished = False
        self._last = 0.0
        self._stats_at = 0.0
        self._stats = ""

    def start(self, step: str) -> None:
        for s, state in self.steps.items():
            if state == "running":
                self.steps[s] = "done"
        self.steps[step] = "running"
        self.write(force=True)

    def line(self, text: str) -> None:
        self.log.append(text)
        if self.steps and "running" in self.steps.values():
            running = next(s for s, st in self.steps.items() if st == "running")
            if text.strip():
                self.detail[running] = text.strip()[:90]
        self.write()

    def finish(self) -> None:
        for s in self.steps:
            self.steps[s] = "done"
        self.finished = True
        self.write(force=True)

    def counts(self) -> list[tuple[str, int, str]]:
        if time.time() - getattr(self, "_counts_at", 0) < 8 and getattr(self, "_counts", None):
            return self._counts
        people = collections.Counter(f.get("qualifies", "unknown") for f in db.load())
        self._counts = [
            ("Match", people["yes"], "green"), ("Likely", people["likely"], "blue"), ("Partial", people["partial"], "yellow"),
            ("To review", review.pending_count(), "white"), ("Screened", len(crawl._read(crawl.SCREEN_PATH)), "white"),
            ("Known", len(crawl._read(crawl.DIRECTORY_PATH)), "white"),
        ]
        self._counts_at = time.time()
        return self._counts

    def stats(self) -> str:
        if time.time() - self._stats_at < 8 and self._stats:
            return self._stats
        counts = collections.Counter(f.get("qualifies", "unknown") for f in db.load())
        pending = review.pending_count()
        directory = len(crawl._read(crawl.DIRECTORY_PATH))
        screened = len(crawl._read(crawl.SCREEN_PATH))
        cells = [
            (counts["yes"], "Match", "yes"), (counts["likely"], "Likely", "likely"), (counts["partial"], "Partial", "partial"),
            (pending, "To review", "unknown"), (screened, "Sites screened", "unknown"), (directory, "Sites known", "unknown"),
        ]
        self._stats = "".join(f'<div class="stat"><b style="color:var(--{c})">{n}</b><span>{label}</span></div>' for n, label, c in cells)
        self._stats_at = time.time()
        return self._stats

    def write(self, force: bool = False) -> None:
        if self.view is not None:
            self.view.update(terminal_view(self))
        if not force and time.time() - self._last < 1.0:
            return
        self._last = time.time()
        elapsed = int(time.time() - self.started)
        steps = "".join(
            f'<div class="step {state}"><i class="dot"></i><b>{html.escape(LABELS.get(s, s))}</b>'
            f'<span>{html.escape(self.detail.get(s, "") if state == "running" else {"done": "done", "pending": ""}.get(state, ""))}</span></div>'
            for s, state in self.steps.items()
        )
        page = (
            PAGE.replace("__REFRESH__", "" if self.finished else '<meta http-equiv="refresh" content="3">')
            .replace("__TITLE__", "Update finished" if self.finished else "Update running")
            .replace("__SUB__", f'<span class="fin">Finished</span> after {elapsed // 60} min {elapsed % 60} s' if self.finished else f"Running for {elapsed // 60} min {elapsed % 60} s. This page refreshes itself.")
            .replace("__STEPS__", steps)
            .replace("__STATS__", self.stats())
            .replace("__LOG__", html.escape("\n".join(self.log)))
        )
        PATH.write_text(page, encoding="utf-8")


class Tee(io.TextIOBase):
    """Mirror stdout to the terminal and the status page."""

    def __init__(self, status: Status, real, echo: bool = True):
        self.status, self.real, self.echo, self._buf = status, real, echo, ""

    def write(self, text: str) -> int:
        if self.echo:
            self.real.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip() and not re.match(r"^\s*(warnings\.warn|.*NotOpenSSLWarning)", line):
                self.status.line(line)
        return len(text)

    def flush(self) -> None:
        self.real.flush()
