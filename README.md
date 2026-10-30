# fontfind

A list of type foundries that sell **one license priced by company size** (headcount) covering
**web, logo and all media**. Open `docs/index.html` in a browser to see it.

## Run it

```sh
pip3 install -r requirements.txt         # once
python3 -m playwright install chromium   # once: a headless browser, about 500 MB in ~/Library/Caches
python3 -m fontfind                      # find, screen and review in a row
```

Claude does the judging, so log in once with `claude` and `/login` (or set `ANTHROPIC_API_KEY`).
Three commands, each also runnable alone. Ctrl-C stops any of them safely; run it again to continue.

| Command | What it does |
|---|---|
| `find` | Looks for new foundry websites: the roundup articles and Claude web searches in `data/sources.yaml`, plus links from foundries already on the list. `--deep` also crawls all of Fonts In Use (hours). |
| `screen` | Reads each new site's license pages and keeps the ones whose text points to company-size pricing: these become candidates. |
| `review` | Claude judges each candidate (up to 25 per run, `--limit N`), adds an image and typefaces, and rebuilds the report. `review "Name"` re-judges one foundry; `--dry-run` prints without saving. |

Also: `list` (table in the terminal), `add <url>` (add a site by hand), `report` (rebuild the page only).

## How a verdict is reached

For each candidate `review`:
1. downloads the license pages (and renders JavaScript pages in the headless browser),
2. renders one font page and lists every price control on it (users, domains, followers, apps...),
3. asks Claude to judge, with exact quotes (a quote that is not on the page is dropped),
4. for a would-be match, asks Claude a second time to try to disprove it.

A **Match** needs all of: price set by company size, web included, logo included, all media in one
license, a font page that could be inspected, and a second check with no objection. Anything less is
**Close** (each card says what is missing) or **Unclear**. Foundries priced by seats or traffic are
hidden. Nothing has been verified by a person: read the current license before buying.

## Files

| Path | What it is |
|---|---|
| `data/foundries.yaml` | The list: verdict, evidence quotes, prices, info |
| `data/sources.yaml` | Where new foundries are searched for. Add lines here to widen the search |
| `data/directory.json`, `data/screen.json` | Machine-written: every site seen and its screening result |
| `docs/index.html` | The report |
| `fontfind/` | The code |

Entries marked `browser-reviewed` were read page by page in a browser by Claude helpers; the
automatic `review` never overwrites them.
