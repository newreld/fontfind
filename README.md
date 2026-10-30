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
python -m fontfind crawl                     # build the full directory, screen it, promote candidates
python -m fontfind crawl sources|screen|promote   # run one stage (all are resumable)
python -m unittest                           # tests
```

`scrape` respects robots.txt and waits 2 seconds between requests to the same site.
It saves page text to `data/snapshots/`, which git ignores, and writes an `auto`
block for each foundry:

- `suggested_metric`, `suggested_logo`, `suggested_qualifies`: what the keyword heuristics think.
- `evidence`: the sentences that triggered each signal, so you can confirm them quickly.
- `content_hash` / `changed_since_last_check`: tells you when a foundry changed its license text.

The suggestions are only hints. A person decides the real `qualifies` value.


## Automatic directory

`crawl` removes the manual adding. It runs in three resumable stages:

1. `sources` lists every foundry on Fonts In Use (about 5,300) and reads each one's official site
   into `data/directory.json`. It honors that site's 10 second `Crawl-delay`, so a full run takes many hours.
2. `screen` finds each site's license pages, classifies them and stores the result in `data/screen.json`.
3. `promote` adds foundries whose text points to company-size pricing to `data/foundries.yaml`
   as `unknown` / `auto-screened, not reviewed`, ready for a human to read and set `qualifies`.

A match requires web use to be in the same company-size license, so the classifier only suggests
`likely` when the license text also mentions web use. `docs/index.html` lists the whole directory
with each foundry's status below the curated results.

To feed in another list of foundries, put one website per line (optionally `Name, https://site`) in a
text file and run `python -m fontfind crawl seed list.txt`. Don't run `seed` while `sources` is running:
both write `data/directory.json`.


## Automatic review

`python3 -m fontfind review` replaces the manual reading step. For every foundry marked
`not reviewed` it fetches the license pages, asks Claude to judge them against the match rule
(company-size pricing that covers web, logo included, all media in one license), and writes
the verdict, summary and evidence. Every evidence quote must appear word for word on a fetched
page, otherwise it is dropped, and a `yes` with fewer than two verified quotes or without
confirmed web use is capped at `likely`. Results are marked `auto-reviewed (claude, quotes checked)`;
entries a person marked `page-read` are never overwritten.

It needs either `ANTHROPIC_API_KEY` in the environment, or a logged-in `claude` command-line tool.
`python3 -m fontfind crawl` (all stages) now ends with this step.
