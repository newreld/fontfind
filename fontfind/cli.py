"""Command line: python3 -m fontfind [find | screen | review]."""

from __future__ import annotations

import argparse

from fontfind import crawl, pipeline, report


def cmd_all(args) -> int:
    return pipeline.update(title="FontFind", limit=getattr(args, "limit", 25))


def cmd_find(args) -> int:
    return pipeline.run_phase("find", deep=args.deep, names=args.names, limit=args.limit)


def cmd_screen(args) -> int:
    return pipeline.run_phase("screen")


def cmd_review(args) -> int:
    return pipeline.run_phase(
        "review", limit=args.limit, only=args.only, force=args.force, dry_run=args.dry_run, workers=args.workers
    )


def cmd_list(args) -> int:
    print(report.table(set(args.qualifies.split(",")) if args.qualifies else None))
    return 0


def cmd_report(args) -> int:
    print(f"wrote {report.build()}")
    return 0


def cmd_add(args) -> int:
    added = crawl.add_seed_sites(args.websites)
    print("Added. Run `screen` and then `review` to judge it." if added else "Already known.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fontfind",
        description="Find type foundries that license by company size. With no command it runs find, screen and review.",
    )
    p.set_defaults(func=cmd_all)
    sub = p.add_subparsers(dest="command", title="commands")

    s = sub.add_parser("find", help="look for new foundry websites")
    s.add_argument("--deep", action="store_true", help="instead, crawl the whole Fonts In Use directory for websites (hours, resumable)")
    s.add_argument("--names", action="store_true", help="instead, search the web for the websites of listed foundries that have none (uses Claude)")
    s.add_argument("--limit", type=int, default=None, help="with --names: only this many foundries (default: all)")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("screen", help="read their license pages and keep the ones that look like company-size pricing")
    s.set_defaults(func=cmd_screen)

    s = sub.add_parser("review", help="Claude judges the candidates, adds images, rebuilds the report")
    s.add_argument("only", nargs="*", help="foundry names (default: all waiting)")
    s.add_argument("--force", action="store_true", help="also re-review automatic reviews")
    s.add_argument("--limit", type=int, default=25, help="review at most this many foundries per run")
    s.add_argument("--dry-run", action="store_true", help="print results without saving")
    s.add_argument("--workers", type=int, default=3, help="foundries reviewed at the same time")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("list", help="print the list as a table")
    s.add_argument("--qualifies", help="comma list, e.g. yes,likely")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("add", help="add foundry websites by hand")
    s.add_argument("websites", nargs="+")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("report", help="rebuild docs/index.html only")
    s.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    return args.func(args)
