# fontfind

A list of type foundries that sell **one license priced by company size** (headcount) that covers
**web, logo and all media**. Claude finds the foundries, reads their license pages and reviews them.

Open `docs/index.html` in a browser to see the result.

## Run it

```sh
pip3 install -r requirements.txt     # once
python3 -m fontfind update           # find, then evaluate (does everything)
python3 -m fontfind find             # only look for new foundries and pick candidates
python3 -m fontfind evaluate         # only review candidates with Claude and rebuild the report
```

`update` needs Claude: either run `claude` once and log in with `/login`, or set `ANTHROPIC_API_KEY`.

What `update` does, in order:

1. **Discover**: collects foundry websites from `data/sources.yaml` (roundup articles, web searches Claude runs, your own seeds) plus links from foundries already matched.
2. **Screen**: reads each site's license pages and keeps those whose text points to company-size pricing.
3. **Review**: Claude reads the real license pages and sets the verdict. Every evidence quote must appear word for word on the page, otherwise it is dropped, and a `yes` needs two verified quotes and confirmed web use.
4. **Info**: preview image and typeface names.
5. **Report**: rebuilds `docs/index.html`.

`update` shows live progress with a bar and time estimate for each step. Press Ctrl-C any time: everything finished so far is saved, files are written atomically, and a backup of the foundry list is kept in `data/foundries.yaml.bak`. Run `update` again to continue.

Review does at most 25 foundries per run (`--limit N`); run `update` again for more.
To find more foundries, add lines to `data/sources.yaml`.

## Other commands

```sh
python3 -m fontfind list --qualifies yes,likely    # table in the terminal
python3 -m fontfind add https://some-foundry.com   # add one foundry by hand
python3 -m fontfind report                         # rebuild the page only
python3 -m fontfind update --steps review          # run chosen steps only
python3 -m fontfind update --deep                  # also crawl all of Fonts In Use (hours)
python3 -m unittest                                # tests
```

## The verdict

| `qualifies` | Meaning |
|---|---|
| `yes` | Company-size price, web included, logo included, all media in one license |
| `likely` | Looks like a match, one point unconfirmed (see `todo`) |
| `partial` | Company-size price, but web, logo or some media costs extra |
| `no` | Priced by seats, devices, users or traffic (hidden from the report) |
| `unknown` | Not enough information |

## Files

| Path | What it is |
|---|---|
| `data/foundries.yaml` | The reviewed foundries: verdict, evidence quotes, prices, info |
| `data/sources.yaml` | Where new foundries are searched for |
| `data/directory.json`, `data/screen.json` | Every site seen and its screening result (machine-written) |
| `docs/index.html` | The report |
| `fontfind/` | The code. `pipeline.py` is the `update` command |

Entries marked `page-read` were read by a person (or by Claude working with one); `update` never
overwrites them. Always read the current license before buying.
