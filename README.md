# fontfind

A database of type foundries that license fonts **by company size**, meaning the price
depends on how many people work at the company, not on seats, page views or app
users. For each foundry it records whether **logo/wordmark use** is in that license.

- `data/foundries.yaml` holds the database. People edit it, and the scraper adds an `auto` block.
- `docs/index.html` is a filterable page built from the database. Open it in a browser.
- `fontfind/` is the scraper and classifier.

## What counts as a match

| `qualifies` | Meaning |
|---|---|
| `yes` | Priced by company size, logo use is included, and one license covers all media |
| `likely` | Looks like a match, but one point is still unconfirmed (see `todo`) |
| `partial` | Priced by company size, but logo or some media costs extra |
| `no` | Priced by seats, devices or traffic |
| `unknown` | Not enough information yet |

Each entry lists evidence with source URLs. `verified.method: search-snippet` means
the entry was checked through search results quoting the foundry's own pages, not
by reading the full EULA. Always read the current license before buying.

## Usage

```sh
pip install -r requirements.txt

python -m fontfind list                      # whole table
python -m fontfind list --qualifies yes,likely
python -m fontfind scrape                    # fetch every license page and classify it
python -m fontfind scrape "Mass-Driver"      # one foundry
python -m fontfind scrape --offline          # re-classify saved snapshots, no network
python -m fontfind add https://example-foundry.com --scrape   # new candidate
python -m fontfind report                    # rebuild docs/index.html
python -m unittest                           # tests
```

`scrape` respects robots.txt and waits 2 seconds between requests to the same site.
It saves page text to `data/snapshots/`, which git ignores, and writes an `auto`
block for each foundry:

- `suggested_metric`, `suggested_logo`, `suggested_qualifies`: what the keyword heuristics think.
- `evidence`: the sentences that triggered each signal, so you can confirm them quickly.
- `content_hash` / `changed_since_last_check`: tells you when a foundry changed its license text.

The suggestions are only hints. A person decides the real `qualifies` value.
