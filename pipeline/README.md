# DGCA domestic traffic: monthly refresh

Keeps `/tools/domestic-traffic/` current without anyone remembering to check.

## How it runs

A GitHub Action looks for a new DGCA report daily through the second half of
each month, and weekly otherwise. DGCA publishes a month 20 to 40 days after
it ends — September 2026 went up on 28 October — so a single monthly cron
would sit on the wrong side of that window about half the time. A check that
finds nothing costs one request and stops.

**Nothing is pushed to the live site.** A refresh opens a pull request, so
the numbers that reach the page have been looked at by a person and
previewed by Netlify first. That matters more than usual here, because the
parser reads a PDF whose layout DGCA has already changed several times.

| Exit | Meaning |
| --- | --- |
| 0 | no new report, or the listed one is unchanged |
| 10 | data updated — the workflow opens a pull request |
| 1 | something failed — the workflow opens an issue, live data untouched |

## Why discovery, not a URL pattern

Across 45 consecutive months DGCA has filed the same monthly report as
`Jan2023.pdf`, `Traffic report Oct 23.pdf`,
`traffic Data Mar 24_240415_193719.pdf`, `TrafficReportApril2026.pdf` and
`traffic Data Sep 26.pdf`. There is no convention to extrapolate from, and
the S3 bucket blocks directory listing. So `dgca_portal.py` reads the
portal's own listing — one form POST that returns JSON, no browser, no
cookies — and maps each filename to a month. That mapping is tested against
all 45 real filenames.

## The pieces

| File | Does |
| --- | --- |
| `dgca_portal.py` | finds the reports; maps irregular filenames to months |
| `dgca_parse.py` | reads the PDF's tables, keyed on heading text, never on position |
| `refresh.py` | orchestrates, and merges a report into the CSVs |
| `validate.py` | the gates; nothing publishes unless all pass |
| `export_site.py` | rebuilds `dgca_domestic.json` from the CSVs |
| `build_capacity.py` | derives implied seats and the capacity chart's series |
| `airlines.json` | DGCA's spellings → display name and group |
| `meta.json` | the curated bits: YTD headline, footnote events, known checks |
| `manifest.json` | what was fetched, when, and its hash |

The CSVs under `tools/domestic-traffic/data/` are the record. The JSON the
page loads is a projection of them, rebuilt every time, so the charts and
the CSV downloads cannot drift apart.

## The gates

Every one of these blocks publication:

- airline rows sum to the national total, within 0.10 lakh
- grouped shares add to 100, within 0.6 points
- our computed share matches the share DGCA prints, within 0.15 points
- our year-on-year matches the figure DGCA prints, within 0.10 points
- seat factors and shares sit between 0 and 100
- the monthly series has no gap
- no carrier with real traffic vanishes from the table

Soft warnings — a new carrier, a small operator going quiet, a month-on-month
move beyond three sigma — are printed into the pull request rather than
blocking it.

A new airline DGCA has not used before **stops the run on purpose**. A
carrier appearing for the first time needs a display name and a group
decided by a person, not guessed; the error says exactly what to add to
`airlines.json`.

## Running it by hand

```bash
pip install -r pipeline/requirements.txt

python pipeline/refresh.py --check-only          # is a new report out?
python pipeline/refresh.py                       # fetch, parse, validate, write
python pipeline/refresh.py --force               # re-parse the latest anyway
python pipeline/validate.py tools/domestic-traffic/data
python -m pytest pipeline/tests -q
```

If a parse fails, see what the file actually contains:

```bash
python pipeline/dgca_parse.py pipeline/raw/DGCA_Domestic_2026-10.pdf --dump
```

## What is tested, and what is not

`pytest pipeline/tests` runs 43 checks covering the filename rule against
every real DGCA report, each validation gate against a deliberately
corrupted copy of the data, the JSON export round-tripping the shipped file
exactly, and the whole chain end to end — roll the data back a month, feed
the report through, confirm it lands byte-for-byte where it started.

The end-to-end test uses a synthetic PDF built from the real figures and
laid out the way DGCA lays them out. That proves the row grouping, column
centring, number matching, name resolution, merge and export all work on a
table of this shape. **It does not prove the parser survives DGCA's actual
page furniture** — only a live file can, and DGCA's S3 bucket was not
reachable from where this was built. The first real run is the test. If it
fails it opens an issue with the log and changes nothing, which is the point
of doing it this way.
