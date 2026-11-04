"""Live terminal display for the find, screen and review commands: per-step progress bars, an overall bar and recent activity."""

from __future__ import annotations

import collections
import io
import time

from fontfind import crawl, db, review

LABELS = {
    "sources": "Read Fonts In Use", "lookup": "Find websites by name", "roundups": "Read roundup articles", "searches": "Search the web with Claude",
    "peers": "Follow links from matches", "screen": "Screen license pages", "promote": "Pick candidates",
    "judge": "Review with Claude", "info": "Images and typefaces", "report": "Build report",
}


def _clock(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60:02d}s"


class Status:
    def __init__(self, steps: list[str], title: str = "Update"):
        self.title = title
        self.view = None
        self.steps = {s: "pending" for s in steps}
        self.totals: dict[str, int] = {}
        self.done: dict[str, int] = collections.defaultdict(int)
        self.detail: dict[str, str] = {}
        self.step_started: dict[str, float] = {}
        self.log: collections.deque[str] = collections.deque(maxlen=40)
        self.started = time.time()
        self.finished = False
        self.aborted = False
        self._counts: list[tuple[str, int, str]] = []
        self._counts_at = 0.0

    @property
    def current(self) -> str | None:
        return next((s for s, st in self.steps.items() if st == "running"), None)

    def start(self, step: str) -> None:
        for s, state in self.steps.items():
            if state == "running":
                self.steps[s] = "done"
        self.steps[step] = "running"
        self.step_started[step] = time.time()
        self.refresh()

    def plan(self, total: int) -> None:
        if self.current:
            self.totals[self.current] = total
            self.refresh()

    def tick(self, label: str = "", n: int = 1) -> None:
        if self.current:
            self.done[self.current] += n
            self.detail[self.current] = label
            self.refresh()

    def line(self, text: str) -> None:
        self.log.append(text.strip())
        self.refresh()

    def finish(self, aborted: bool = False) -> None:
        self.aborted = aborted
        if not aborted:
            for s in self.steps:
                self.steps[s] = "done"
        self.finished = True
        self.refresh()

    def fraction(self, step: str) -> float:
        state = self.steps[step]
        if state == "done":
            return 1.0
        total = self.totals.get(step)
        if state == "running" and total:
            return min(self.done[step] / total, 1.0)
        return 0.0

    def overall(self) -> float:
        return sum(self.fraction(s) for s in self.steps) / max(len(self.steps), 1)

    def eta(self, step: str) -> str:
        total, done = self.totals.get(step, 0), self.done[step]
        if not total or not done or self.steps[step] != "running":
            return ""
        per_item = (time.time() - self.step_started[step]) / done
        return f"~{_clock(per_item * (total - done))} left"

    def counts(self) -> list[tuple[str, int, str]]:
        if self._counts and time.time() - self._counts_at < 8:
            return self._counts
        people = collections.Counter(f.get("qualifies", "unknown") for f in db.load())
        self._counts = [
            ("To screen", len(crawl.screen_todo()), "magenta"), ("Screened", len(crawl._read(crawl.SCREEN_PATH)), "white"),
            ("To review", review.pending_count(), "magenta"),
            ("Match", people["yes"], "green"), ("Likely", people["likely"], "blue"), ("Partial", people["partial"], "yellow"),
        ]
        self._counts_at = time.time()
        return self._counts

    def refresh(self) -> None:
        if self.view is not None:
            self.view.update(terminal_view(self))


def terminal_view(status: Status):
    from rich.console import Group
    from rich.panel import Panel
    from rich.progress_bar import ProgressBar
    from rich.spinner import Spinner
    from rich.table import Table
    from rich.text import Text

    elapsed = time.time() - status.started
    percent = status.overall() * 100

    overall = Table.grid(padding=(0, 2), expand=True)
    overall.add_column(ratio=1)
    overall.add_column(width=5, justify="right")
    overall.add_row(ProgressBar(total=100, completed=percent, width=None, complete_style="cyan", finished_style="green"), Text(f"{percent:.0f}%", style="bold"))

    steps = Table.grid(padding=(0, 2), expand=True)
    steps.add_column(width=2)
    steps.add_column(width=28, no_wrap=True)
    steps.add_column(width=22)
    steps.add_column(width=9, justify="right", no_wrap=True)
    steps.add_column(width=15, no_wrap=True)
    steps.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    for name, state in status.steps.items():
        label = LABELS.get(name, name)
        total, done = status.totals.get(name), status.done[name]
        count = f"{done}/{total}" if total else ""
        if state == "done":
            note = "nothing to do" if total == 0 else ""
            steps.add_row(Text("✓", style="green"), Text(label, style="green"), ProgressBar(total=1, completed=1, width=22, finished_style="green") if total != 0 else Text(""), Text(count, style="green"), Text(""), Text(note, style="dim"))
        elif state == "running":
            bar = ProgressBar(total=total or 1, completed=done if total else 0, width=22, complete_style="cyan", pulse=not total)
            steps.add_row(Spinner("dots", style="cyan"), Text(label, style="bold cyan"), bar, Text(count, style="bold"), Text(status.eta(name), style="yellow"), Text(status.detail.get(name, ""), style="dim"))
        else:
            steps.add_row(Text("○", style="dim"), Text(label, style="dim"), Text(""), Text(""), Text(""), Text(""))

    counts = status.counts()
    divider_at = 3  # first three counts are work in progress, the rest are results
    stats = Table.grid(padding=(0, 3))
    top, bottom = [], []
    for i, (label, n, color) in enumerate(counts):
        if i == divider_at:
            stats.add_column(justify="center", width=1)
            top.append(Text("│", style="dim"))
            bottom.append(Text("│", style="dim"))
        stats.add_column(justify="center")
        top.append(Text(str(n), style=f"bold {color}"))
        bottom.append(Text(label, style="dim"))
    stats.add_row(*top)
    stats.add_row(*bottom)

    recent = Text("\n".join(list(status.log)[-5:]) or " ", style="dim", no_wrap=True, overflow="ellipsis")
    if status.aborted:
        title, border = "[bold yellow]Stopped[/]  progress is saved, run the command again to continue", "yellow"
    elif status.finished:
        title, border = f"[bold green]{status.title} finished[/]", "green"
    else:
        title, border = f"[bold]{status.title} running[/]  Ctrl-C stops safely", "cyan"
    return Panel(
        Group(overall, Text(""), steps, Text(""), stats, Text(""), recent),
        title=title, subtitle=f"{_clock(elapsed)} elapsed", border_style=border, padding=(1, 2),
    )


class Tee(io.TextIOBase):
    """Send printed lines to the status display; echo them to the terminal only when it is not a live display."""

    def __init__(self, status: Status, real, echo: bool = True):
        self.status, self.real, self.echo, self._buf = status, real, echo, ""

    def write(self, text: str) -> int:
        if self.echo:
            self.real.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.status.line(line)
        return len(text)

    def flush(self) -> None:
        self.real.flush()
