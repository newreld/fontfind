"""Collect every foundry we can find, screen each for company-size licensing, promote candidates.

Three resumable stages, each safe to interrupt and re-run:
  sources  - list foundries on Fonts In Use and look up each one's official website
  screen   - fetch each website's license pages and run the classifier
  promote  - add screened candidates to data/foundries.yaml for human review
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from fontfind import classify, db, discover, fetch, progress

DIRECTORY_PATH = db.ROOT / "data" / "directory.json"
SCREEN_PATH = db.ROOT / "data" / "screen.json"
LISTING_URL = "https://fontsinuse.com/foundries"
FOUNDRY_PATH = re.compile(r"^/foundry/\d+/[^/]+$")
SCREEN_PAGES = 4
SAVE_EVERY = 25


def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def parse_listing(html: str, base: str = LISTING_URL) -> dict[str, str]:
    """Foundry page URL -> display name, from the Fonts In Use directory page."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        if FOUNDRY_PATH.match(a["href"]):
            found[urljoin(base, a["href"])] = a.get_text(" ", strip=True) or a["href"].rsplit("/", 1)[-1]
    return found


def parse_foundry_page(html: str) -> str | None:
    """The foundry's own website: the 'Official Site' link."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("http") and "official site" in a.get_text(" ", strip=True).lower():
            return a["href"]
    return None


def sources(limit: int | None = None) -> int:
    directory = _read(DIRECTORY_PATH)
    try:
        listing = parse_listing(fetch.get(LISTING_URL).text)
    except fetch.FetchError as e:
        print(f"could not read directory: {e}", file=sys.stderr)
        return 1
    for url, name in listing.items():
        directory.setdefault(url, {"name": name, "source": "fontsinuse.com"})
    _write(DIRECTORY_PATH, directory)
    todo = [u for u, d in directory.items() if "website" not in d and d.get("tries", 0) < 2]
    print(f"{len(directory)} foundries listed, {len(todo)} still need a website", flush=True)
    progress.total(len(todo[:limit]))
    try:
        for i, url in enumerate(todo[:limit], 1):
            d = directory[url]
            progress.tick(d["name"])
            try:
                d["website"] = parse_foundry_page(fetch.get(url).text) or ""
            except fetch.FetchError as e:
                d["tries"] = d.get("tries", 0) + 1
                print(f"  {d['name']}: {e}", flush=True)
            if i % SAVE_EVERY == 0:
                _write(DIRECTORY_PATH, directory)
    finally:
        _write(DIRECTORY_PATH, directory)
    return 0


def seed(path: str) -> int:
    add_seed_sites(open(path, encoding="utf-8").read().splitlines())
    return 0


def add_seed_sites(lines: list[str]) -> int:
    """Add foundries from lines of 'https://site' or 'Name, https://site'."""
    directory = _read(DIRECTORY_PATH)
    have = known_hosts(directory)
    added = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, site = line.rpartition(",")
        site = site.strip()
        if not site.startswith("http"):
            site = "https://" + site
        if seen(host_of(site), have):
            continue
        have.add(host_of(site))
        directory[f"seed:{host_of(site)}"] = {"name": name.strip() or host_of(site), "source": "seed", "website": site}
        added += 1
    _write(DIRECTORY_PATH, directory)
    print(f"added {added} seed foundries")
    return added


IGNORED_HOSTS = re.compile(
    r"(instagram|facebook|twitter|x\.com|linkedin|youtube|vimeo|tiktok|threads\.net|pinterest|behance|dribbble|"
    r"github|gumroad|myfonts|fonts\.com|fontspring|adobe|google|apple|mailchimp|shopify|cloudflare|paypal|stripe|"
    r"framerusercontent|cloudfront|amazonaws|googleusercontent|wixstatic|webflow\.io|squarespace-cdn|wikipedia|fontsinuse|typewolf|substack|medium\.com|are\.na|notion|vercel|netlify|wixsite|squarespace|"
    r"cargo\.site|fontsource|fontshare|typekit|bsky|mastodon|typo\.social|whatsapp|t\.me|spotify|soundcloud)",
    re.I,
)
GOOD_QUALIFIES = {"yes", "likely", "partial"}


def external_links(html: str, base_url: str) -> dict[str, str]:
    """host -> url for links that leave the site and are not social/marketplace hosts."""
    soup = BeautifulSoup(html, "html.parser")
    own = host_of(base_url)
    out = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"])
        parts = urlparse(url)
        host = host_of(url)
        if parts.scheme in ("http", "https") and host and host != own and "." in host and not IGNORED_HOSTS.search(host):
            out.setdefault(host, f"{parts.scheme}://{parts.netloc}")
    return out


def peers() -> int:
    """Add sites linked from curated yes/likely/partial foundries to the directory."""
    directory = _read(DIRECTORY_PATH)
    known = {host_of(d["website"]) for d in directory.values() if d.get("website")}
    known |= {host_of(f["website"]) for f in db.load() if f.get("website")}
    added = 0
    targets = [f for f in db.load() if f.get("qualifies") in GOOD_QUALIFIES and f.get("website")]
    progress.total(len(targets))
    try:
        for f in targets:
            progress.tick(f["name"])
            for page in [f["website"], *(f.get("license_urls") or [])[:3]]:
                try:
                    links = external_links(fetch.get(page).text, page)
                except fetch.FetchError:
                    continue
                for host, site in links.items():
                    if seen(host, known):
                        continue
                    known.add(host)
                    directory[f"peer:{host}"] = {"name": host, "source": f"linked from {f['name']}", "website": site}
                    added += 1
    finally:
        _write(DIRECTORY_PATH, directory)
    print(f"added {added} linked sites to the directory")
    return 0


def brand(host: str) -> str:
    """First label of a host, e.g. 'foundry.oplerou.studio' -> 'oplerou'."""
    parts = host.split(".")
    return parts[-2] if len(parts) >= 2 and parts[-2] not in ("co", "com", "org", "ac") else parts[0]


def seen(host: str, have: set[str]) -> bool:
    """Exact host match, or the same brand under another domain (arillatype.com vs arillatype.studio)."""
    if host in have:
        return True
    b = brand(host)
    return len(b) >= 3 and any(len(o) >= 3 and (b.startswith(o) or o.startswith(b)) for o in map(brand, have))


def known_hosts(directory: dict) -> set[str]:
    hosts = {host_of(d["website"]) for d in directory.values() if d.get("website")}
    return hosts | {host_of(f["website"]) for f in db.load() if f.get("website")}


def add_roundup_pages(pages: list[str]) -> int:
    """Extract foundry links from article/directory pages and add the new ones to the directory."""
    directory = _read(DIRECTORY_PATH)
    have = known_hosts(directory)
    added = 0
    progress.total(len(pages))
    try:
        for page in pages:
            progress.tick(host_of(page))
            try:
                links = external_links(fetch.get(page).text, page)
            except fetch.FetchError as e:
                print(f"  skipped {page}: {e}")
                continue
            new = {}
            for h, u in links.items():
                if not seen(h, have):
                    have.add(h)
                    new[h] = u
            for host, site in new.items():
                directory[f"roundup:{host}"] = {"name": host, "source": f"linked from {page}", "website": site}
            added += len(new)
            print(f"  {len(links)} links, {len(new)} new: {page}", flush=True)
    finally:
        _write(DIRECTORY_PATH, directory)
    print(f"added {added} sites from roundup pages")
    return added


def roundups(path: str) -> int:
    add_roundup_pages([l.strip() for l in open(path, encoding="utf-8") if l.strip().startswith("http")])
    return 0


SEARCH_PROMPT = """Use web search to find independent type foundries or font studios that sell font licenses priced by company size or employee count.
Search focus: {query}
Reply with ONLY a JSON list (max 15) of objects {{"name": ..., "website": ...}} giving each foundry's OWN official website seen in the search results. Exclude marketplaces (MyFonts, Fonts.com, Adobe, Google Fonts, Creative Market), articles and social media. Never guess a URL."""


def add_searched_sites(queries: list[str]) -> int:
    """Ask Claude (with web search) for foundries per query and add the new ones to the directory."""
    import json as _json
    from fontfind import review

    directory = _read(DIRECTORY_PATH)
    have = known_hosts(directory)
    added = 0
    progress.total(len(queries))
    try:
        for query in queries:
            progress.tick(query[:60])
            try:
                reply = review._complete(SEARCH_PROMPT.format(query=query), tools="WebSearch")
                found = _json.loads(re.search(r"\[.*\]", reply, re.S).group(0))
            except Exception as e:
                print(f"  search failed ({query[:40]}...): {e}")
                continue
            new = 0
            for item in found:
                site = str(item.get("website", "")).strip()
                if not site.startswith("http") or seen(host_of(site), have) or IGNORED_HOSTS.search(host_of(site)):
                    continue
                have.add(host_of(site))
                directory[f"search:{host_of(site)}"] = {"name": item.get("name") or host_of(site), "source": f"search: {query[:60]}", "website": site}
                new += 1
            added += new
            print(f"  {new} new from search: {query[:60]}", flush=True)
    finally:
        _write(DIRECTORY_PATH, directory)
    return added




def screen_site(website: str) -> dict:
    urls = discover.discover(website)[:SCREEN_PAGES] or discover.fallback(website)
    texts, errors = [], []
    for u in urls:
        try:
            texts.append(fetch.fetch_text(u))
        except fetch.FetchError as e:
            errors.append(str(e))
    result = classify.classify("\n".join(texts)) if texts else None
    out = {"license_urls": urls, "checked": dt.date.today().isoformat()}
    if result:
        out["auto"] = result.as_dict()
    if errors:
        out["errors"] = errors
    if not urls:
        out["errors"] = errors or ["no license page found"]
    return out


def screen(limit: int | None = None, workers: int = 8) -> int:
    directory = _read(DIRECTORY_PATH)
    screened = _read(SCREEN_PATH)
    known = {host_of(f["website"]) for f in db.load() if f.get("website")}
    todo = {}
    for d in directory.values():
        site = d.get("website")
        if site and host_of(site) not in screened and not seen(host_of(site), known):
            todo.setdefault(host_of(site), site)
    sites = list(todo.items())[:limit]
    print(f"screening {len(sites)} sites ({len(screened)} done already)", flush=True)

    def work(item):
        host, site = item
        try:
            return host, {"website": site, **screen_site(site)}
        except fetch.FetchError as e:
            return host, {"website": site, "errors": [str(e)], "checked": dt.date.today().isoformat()}

    progress.total(len(sites))
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [pool.submit(work, s) for s in sites]
        for i, fut in enumerate(as_completed(futures), 1):
            host, res = fut.result()
            screened[host] = res
            progress.tick(host)
            if i % SAVE_EVERY == 0:
                _write(SCREEN_PATH, screened)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        _write(SCREEN_PATH, screened)
    return 0


NOT_FOUNDRY_HOSTS = re.compile(
    r"(\.ca$|college|university|\.edu|bit\.ly|luma\.com|typeform|jotform|wordpress|ghost\.org|craftcms|semplice|"
    r"gestalten|dielineawards|appliedarts|eventbrite|medium\.com)", re.I,
)


def is_candidate(res: dict, host: str = "") -> bool:
    """Company size clearly outweighs seats and traffic in the license text."""
    if host and (NOT_FOUNDRY_HOSTS.search(host) or IGNORED_HOSTS.search(host)):
        return False
    scores = (res.get("auto") or {}).get("metric_scores") or {}
    company = scores.get("company_size", 0)
    return company >= 3 and company >= scores.get("seats", 0) + scores.get("traffic", 0)


def display_name(host: str, directory: dict) -> str:
    for d in directory.values():
        if d.get("website") and host_of(d["website"]) == host:
            return d["name"]
    return host


def promote() -> int:
    directory = _read(DIRECTORY_PATH)
    screened = _read(SCREEN_PATH)
    foundries = db.load()
    known = {host_of(f["website"]) for f in foundries if f.get("website")}
    added = 0
    for host, res in sorted(screened.items()):
        if seen(host, known) or not is_candidate(res, host):
            continue
        name = display_name(host, directory)
        if db.find(foundries, name):
            name = f"{name} ({host})"
        foundries.append({
            "name": name,
            "website": res["website"],
            "license_urls": res.get("license_urls", []),
            "pricing_metric": "unknown",
            "logo": "unknown",
            "all_media": "unknown",
            "qualifies": "unknown",
            "summary": "",
            "evidence": [],
            "verified": {"date": dt.date.today().isoformat(), "method": "auto-screened, not reviewed"},
            "auto": {**res["auto"], "checked": res["checked"]},
        })
        added += 1
    if added:
        db.save(foundries)
    print(f"promoted {added} candidates into {db.DB_PATH.name}")
    return 0


def directory_rows() -> list[dict]:
    """Every known foundry with its screening status, for the report."""
    directory = _read(DIRECTORY_PATH)
    screened = _read(SCREEN_PATH)
    curated = {host_of(f["website"]): f for f in db.load() if f.get("website")}
    rows = []
    for d in directory.values():
        site = d.get("website") or ""
        host = host_of(site) if site else ""
        if host in curated:
            status = "curated:" + str(curated[host].get("qualifies", "unknown"))
        elif host in screened:
            res = screened[host]
            status = "candidate" if is_candidate(res, host) else ("no-license-page" if res.get("errors") and "auto" not in res else "not-company-size")
        else:
            status = "no-site" if not site else "unscreened"
        rows.append({"name": d["name"], "website": site, "status": status})
    listed = {host_of(r["website"]) for r in rows if r["website"]}
    for host, f in curated.items():
        if host not in listed:
            rows.append({"name": f["name"], "website": f["website"], "status": "curated:" + str(f.get("qualifies", "unknown"))})
    return sorted(rows, key=lambda r: r["name"].lower())
