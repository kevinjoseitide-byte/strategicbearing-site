#!/usr/bin/env python3
"""Read a DGCA monthly domestic traffic PDF into tidy rows.

The files are "Microsoft Print to PDF" exports with a real text layer, so
there is no OCR here. What there is, is drift: airline columns come and go
as carriers merge or fail, the month columns grow through the year, and the
wording of headings changes between reports. So nothing is keyed on a fixed
row or column index. Every anchor is a piece of header text, and anything
that cannot be located raises rather than returning a plausible-looking
half-answer. A parser that guesses is worse than one that stops, because
validation downstream can only catch numbers that are wrong, not numbers
that were never there.

Each report restates the whole calendar year to date, so parsing the latest
file re-derives every month of the current year. That is deliberate: it is
how a restatement of an earlier month gets picked up.
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

import pdfplumber

MONTH_ABBR = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
              'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
MONTH_RE = re.compile(r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP(?:T)?|OCT|NOV|DEC)',
                      re.I)
NUM_RE = re.compile(r'^-?[\d,]+(?:\.\d+)?$')

# header text that marks each table. Matched case-insensitively against the
# page text, so wording changes around them do not matter.
ANCHOR_SHARE = re.compile(r'passengers?\s+carried\s+by\s+domestic\s+airlines', re.I)
ANCHOR_PLF = re.compile(r'passenger\s+load\s+factor', re.I)
ANCHOR_MKT = re.compile(r'market\s+share\s+of\s+(?:domestic\s+)?(?:scheduled\s+)?airlines', re.I)

# the headline sentence, e.g. "... were 1223.53 lakh as against 1233.70 lakh
# ... thereby registering a growth of -0.82%"
YTD_RE = re.compile(
    r'([\d,]+\.\d+)\s*lakh.{0,80}?([\d,]+\.\d+)\s*lakh.{0,120}?'
    r'(?:growth|change|de-?growth)[^\-\d%]{0,30}(-?\d+\.\d+)\s*%',
    re.I | re.S)


class ParseError(RuntimeError):
    pass


def _f(s: str) -> float | None:
    s = s.strip().replace(',', '').replace('−', '-').replace('–', '-')
    if not s or s in {'-', '--', 'NA', 'N.A.', 'N/A'}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _rows(page, tol: float = 2.4) -> list[list[dict]]:
    """Group a page's words into visual rows, left to right."""
    buckets: dict[int, list[dict]] = collections.defaultdict(list)
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        buckets[round(w['top'] / tol)].append(w)
    return [sorted(v, key=lambda w: w['x0'])
            for _, v in sorted(buckets.items())]


def _header_months(row: list[dict], year: int) -> list[tuple[float, str]]:
    """Month columns in a header row, as (x-centre, 'YYYY-MM')."""
    out = []
    for w in row:
        m = MONTH_RE.match(w['text'])
        if m:
            idx = [i for i, a in enumerate(MONTH_ABBR)
                   if w['text'].upper().startswith(a)]
            if idx:
                out.append(((w['x0'] + w['x1']) / 2, f'{year}-{idx[0] + 1:02d}'))
    return out


def _value_for(row: list[dict], centre: float, slack: float = 26.0) -> float | None:
    """The number in this row sitting under a given column centre."""
    best, bestd = None, slack
    for w in row:
        if not NUM_RE.match(w['text']):
            continue
        d = abs((w['x0'] + w['x1']) / 2 - centre)
        if d < bestd:
            best, bestd = w['text'], d
    return _f(best) if best is not None else None


def _label(row: list[dict], first_col_x: float) -> str:
    """The row label: everything left of the first numeric column."""
    return ' '.join(w['text'] for w in row
                    if (w['x0'] + w['x1']) / 2 < first_col_x - 12).strip()


def _grid(pdf, anchor: re.Pattern, year: int, what: str):
    """Locate a table by its heading and read it as {label: {period: value}}."""
    for page in pdf.pages:
        text = page.extract_text() or ''
        if not anchor.search(text):
            continue
        rows = _rows(page)
        for i, row in enumerate(rows):
            cols = _header_months(row, year)
            if len(cols) < 1:
                continue
            first_x = min(c for c, _ in cols)
            out: dict[str, dict[str, float]] = {}
            for r in rows[i + 1:]:
                lab = _label(r, first_x)
                if not lab or len(lab) > 60:
                    continue
                vals = {p: _value_for(r, c) for c, p in cols}
                vals = {p: v for p, v in vals.items() if v is not None}
                if vals:
                    out[lab] = vals
            if out:
                return out, [p for _, p in cols], page.page_number
    raise ParseError(
        f'could not find the {what} table. The heading this looks for is '
        f'/{anchor.pattern}/ and no page matched it, so DGCA has most likely '
        f'reworded it. Re-run with --dump to see the headings in the file.')


def parse(pdf_path: str | pathlib.Path, period: str) -> dict:
    """Parse one monthly report. `period` is its own month, 'YYYY-MM'."""
    year = int(period[:4])
    p = pathlib.Path(pdf_path)
    with pdfplumber.open(p) as pdf:
        full = '\n'.join((pg.extract_text() or '') for pg in pdf.pages)
        share, months, pg_share = _grid(pdf, ANCHOR_SHARE, year, 'passengers carried')
        plf, _, pg_plf = _grid(pdf, ANCHOR_PLF, year, 'passenger load factor')
        # DGCA prints the percentage share as well as the passenger count.
        # Having both is what lets validation compare our arithmetic against
        # DGCA's own, so it is worth looking for — but a report that only
        # gives the counts is still usable, with that one gate going quiet.
        try:
            mkt, _, _ = _grid(pdf, ANCHOR_MKT, year, 'market share')
        except ParseError:
            mkt = {}

    if period not in months:
        raise ParseError(
            f'the report is supposed to cover {period} but its month columns '
            f'are {months}. Either the file is for a different month or the '
            f'header row was misread.')

    # The column headers are bare month names, so the year comes from the
    # filename. If DGCA ever files a report under the wrong name, or the
    # filename rule misreads one, every row would be written against the
    # wrong year and still look perfectly consistent. So the document has to
    # name this month and this year together — "SEPTEMBER 2026" in the
    # title, or "Jan-Sep 2026" in the headline sentence. A bare year is not
    # enough: footnotes routinely mention other years.
    abbr = MONTH_ABBR[int(period[5:]) - 1]
    flat = re.sub(r'\s+', ' ', full)
    if not re.search(rf'\b{abbr}\w*\b[^A-Za-z0-9]{{0,4}}{year}\b', flat, re.I):
        raise ParseError(
            f'the filename says this report is for {period}, but the document '
            f'never names that month alongside {year}. Refusing to file its '
            f'rows under a period the file does not claim.')

    ytd = None
    m = YTD_RE.search(re.sub(r'\s+', ' ', full))
    if m:
        ytd = {'pax': _f(m.group(1)), 'prev': _f(m.group(2)), 'growth': _f(m.group(3)),
               'scope': 'ytd'}

    notes = [re.sub(r'\s+', ' ', n).strip()
             for n in re.findall(r'(?:^|\n)\s*\*{1,2}\s*([^\n]{10,240})', full)]

    return {'period': period, 'months': months, 'share': share, 'plf': plf,
            'share_pct': mkt, 'share_pct_source': 'dgca' if mkt else 'computed',
            'ytd': ytd, 'footnotes': notes,
            'pages': {'share': pg_share, 'plf': pg_plf},
            'source': p.name}


def dump(pdf_path: str | pathlib.Path, limit: int = 4) -> None:
    """Print what the file actually contains. For when a parse fails in CI."""
    with pdfplumber.open(pdf_path) as pdf:
        print(f'{len(pdf.pages)} pages')
        for pg in pdf.pages[:limit]:
            print(f'\n----- page {pg.page_number} -----')
            print((pg.extract_text() or '')[:2500])


if __name__ == '__main__':
    if '--dump' in sys.argv:
        dump(sys.argv[1])
    else:
        import json
        r = parse(sys.argv[1], sys.argv[2])
        r['share'] = {k: v for k, v in list(r['share'].items())[:40]}
        print(json.dumps(r, indent=1)[:4000])
