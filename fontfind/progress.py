"""Tiny hook so pipeline steps can report 'n of total' without knowing about the display."""

from __future__ import annotations

_tracker = None


def attach(tracker) -> None:
    global _tracker
    _tracker = tracker


def total(n: int) -> None:
    if _tracker:
        _tracker.plan(n)


def tick(label: str = "", n: int = 1) -> None:
    if _tracker:
        _tracker.tick(label, n)
