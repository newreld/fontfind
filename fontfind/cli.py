"""Command line: python -m fontfind <command>."""

from __future__ import annotations

import argparse
import datetime as dt

from fontfind import db, discover, fetch, report, scrape


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

    args = p.parse_args(argv)
    return args.func(args)
