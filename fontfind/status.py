"""Live terminal display for `update`: steps, counts and recent activity, redrawn in place."""

from __future__ import annotations

import collections
import io
import time

from fontfind import crawl, db, review

LABELS = {
    "discover": "Find foundries", "screen": "Screen license pages", "promote": "Pick candidates",
    "review": "Review with Claude", "info": "Images and typefaces", "report": "Build report",
}


def terminal_view(status: "Status"):
    """A rich renderable of the current state."""
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
        self._counts: list[tuple[str, int, str]] = []
        self._counts_at = 0.0

    def start(self, step: str) -> None:
        for s, state in self.steps.items():
            if state == "running":
                self.steps[s] = "done"
        self.steps[step] = "running"
        self.refresh()

    def line(self, text: str) -> None:
        self.log.append(text)
        running = next((s for s, st in self.steps.items() if st == "running"), None)
        if running and text.strip():
            self.detail[running] = text.strip()[:90]
        self.refresh()

    def finish(self) -> None:
        for s in self.steps:
            self.steps[s] = "done"
        self.finished = True
        self.refresh()

    def counts(self) -> list[tuple[str, int, str]]:
        if self._counts and time.time() - self._counts_at < 8:
            return self._counts
        people = collections.Counter(f.get("qualifies", "unknown") for f in db.load())
        self._counts = [
            ("Match", people["yes"], "green"), ("Likely", people["likely"], "blue"), ("Partial", people["partial"], "yellow"),
            ("To review", review.pending_count(), "white"), ("Screened", len(crawl._read(crawl.SCREEN_PATH)), "white"),
            ("Known", len(crawl._read(crawl.DIRECTORY_PATH)), "white"),
        ]
        self._counts_at = time.time()
        return self._counts

    def refresh(self) -> None:
        if self.view is not None:
            self.view.update(terminal_view(self))


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
