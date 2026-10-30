"""Command line: python -m fontfind <command>."""

from __future__ import annotations

import argparse
import datetime as dt

from fontfind import crawl, db, discover, fetch, info, pipeline, report, review, scrape


def cmd_list(args) -> int:
    print(report.table(set(args.qualifies.split(",")) if args.qualifies else None))
    return 0


def cmd_scrape(args) -> int:
    return scrape.scrape(only=args.only, offline=args.offline)


def cmd_add(args) -> int:
    foundries = db.load()
    added = 0
    for website in args.websites:
        name = args.name if args.name and len(args.websites) == 1 else website.split("//")[-1].split("/")[0]
        if db.find(foundries, name):
            print(f"already in database: {name}")
            continue
        try:
            urls = discover.discover(website)
        except fetch.FetchError as e:
            print(f"could not read {website}: {e}")
            urls = []
        entry = {
            "name": name,
            "website": website,
            "license_urls": urls,
            "pricing_metric": "unknown",
            "logo": "unknown",
            "all_media": "unknown",
            "qualifies": "unknown",
            "summary": "",
            "evidence": [],
            "verified": {"date": dt.date.today().isoformat(), "method": "added, not reviewed"},
        }
        foundries.append(entry)
        added += 1
        print(f"added {name}: {len(urls)} license page(s) found")
        for u in urls:
            print(f"    {u}")
        if args.scrape:
            scrape.scrape_one(entry)
            auto = entry["auto"]
            if "suggested_qualifies" in auto:
                print(f"    suggestion: {auto['suggested_qualifies']} (metric={auto['suggested_metric']}, logo={auto['suggested_logo']})")
    if added:
        db.save(foundries)
    return 0


def cmd_report(args) -> int:
    print(f"wrote {report.build()}")
    return 0


def cmd_update(args) -> int:
    return pipeline.update(steps=args.steps.split(",") if args.steps else None, limit=args.limit, deep=args.deep)


def cmd_review(args) -> int:
    return review.review(only=args.only, force=args.force, limit=args.limit, dry_run=args.dry_run)


def cmd_info(args) -> int:
    return info.collect(only=args.only, force=args.force)


def cmd_crawl(args) -> int:
    if args.stage == "sources":
        return crawl.sources(limit=args.limit)
    if args.stage == "screen":
        return crawl.screen(limit=args.limit, workers=args.workers)
    if args.stage == "peers":
        return crawl.peers()
    if args.stage == "roundups":
        return crawl.roundups(args.file)
    if args.stage == "seed":
        return crawl.seed(args.file)
    if args.stage == "promote":
        return crawl.promote()
    for stage in (lambda: crawl.sources(limit=args.limit), lambda: crawl.screen(limit=args.limit, workers=args.workers), crawl.promote, review.review):
        stage()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fontfind", description="Track company-size font licenses.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="print the database as a table")
    s.add_argument("--qualifies", help="comma list, e.g. yes,likely")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("scrape", help="fetch license pages and classify them")
    s.add_argument("only", nargs="*", help="foundry names (default: all)")
    s.add_argument("--offline", action="store_true", help="re-classify saved snapshots without fetching")
    s.set_defaults(func=cmd_scrape)

    s = sub.add_parser("add", help="add foundries by website and find their license pages")
    s.add_argument("websites", nargs="+")
    s.add_argument("--name", help="display name (only with a single website)")
    s.add_argument("--scrape", action="store_true", help="also classify the found pages")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("report", help="write docs/index.html")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("update", help="find new foundries, review them, rebuild the report (does everything)")
    s.add_argument("--steps", help=f"comma list from: {','.join(pipeline.STEPS)}")
    s.add_argument("--limit", type=int, default=25, help="review at most this many foundries per run")
    s.add_argument("--deep", action="store_true", help="also crawl the full Fonts In Use directory (hours)")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("review", help="let Claude read license pages and fill in the verdict (quotes are verified)")
    s.add_argument("only", nargs="*", help="foundry names (default: all 'not reviewed')")
    s.add_argument("--force", action="store_true", help="also re-review entries that were auto-reviewed")
    s.add_argument("--limit", type=int, help="review at most this many foundries")
    s.add_argument("--dry-run", action="store_true", help="print results without saving")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("info", help="fetch preview image, description and typeface names for each foundry")
    s.add_argument("only", nargs="*", help="foundry names (default: all without info)")
    s.add_argument("--force", action="store_true", help="refetch even if info exists")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("crawl", help="build the full foundry directory and screen it automatically")
    s.add_argument("stage", nargs="?", default="all", choices=["all", "sources", "screen", "promote", "seed", "peers", "roundups"])
    s.add_argument("file", nargs="?", help="seed/roundups: text file with one website (seed) or article URL (roundups) per line")
    s.add_argument("--limit", type=int, help="process at most this many foundries per stage")
    s.add_argument("--workers", type=int, default=8, help="parallel sites while screening")
    s.set_defaults(func=cmd_crawl)

    args = p.parse_args(argv)
    return args.func(args)
