#!/usr/bin/env python3
"""Check DGCA for a new monthly report and fold it into the site's data.

    python3 pipeline/refresh.py                 # check, and update if there is one
    python3 pipeline/refresh.py --check-only    # just say whether one is out
    python3 pipeline/refresh.py --pdf FILE --period 2026-10   # parse a local file

Exit codes: 0 nothing to do, 10 data updated, 1 something failed.
The caller (the GitHub workflow) turns a 10 into a pull request.

Each report restates the whole calendar year, so one file re-derives every
month of that year. Earlier years are left alone — their December report is
the authority and nothing later restates them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / 'tools' / 'domestic-traffic' / 'data'
MANIFEST = HERE / 'manifest.json'
NAMES = HERE / 'airlines.json'

sys.path.insert(0, str(HERE))
import build_capacity          # noqa: E402
import dgca_parse              # noqa: E402
import dgca_portal             # noqa: E402
import export_site             # noqa: E402
import validate                # noqa: E402

MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
       'August', 'September', 'October', 'November', 'December']


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------- name map
def load_names() -> dict:
    return json.loads(NAMES.read_text(encoding='utf-8'))


def resolve(raw: str, names: dict) -> tuple[str, str]:
    """DGCA's spelling -> (display name, group). Unknown names stop the run."""
    key = ' '.join(raw.split()).strip(' *').lower()
    hit = names['airlines'].get(key)
    if not hit:
        raise SystemExit(
            f'\nUnknown airline in the DGCA table: "{raw}".\n'
            f'This is deliberate — a carrier that appears for the first time\n'
            f'needs a display name and a group decided by a person, not\n'
            f'guessed. Add it to pipeline/airlines.json:\n\n'
            f'    "{key}": {{"name": "{raw.strip()}", "group": "Others"}}\n')
    return hit['name'], hit['group']


# ------------------------------------------------------------------ merge
def merge(parsed: dict, names: dict) -> dict[str, pd.DataFrame]:
    """Fold a parsed report into the CSVs, replacing the months it covers."""
    url = parsed['url']
    report = parsed['period']
    months = parsed['months']

    car = pd.read_csv(DATA / 'market_share_by_carrier.csv')
    plf = pd.read_csv(DATA / 'plf_by_carrier.csv')
    nat = pd.read_csv(DATA / 'national_monthly_domestic.csv')

    # ---- carrier pax --------------------------------------------------
    rows = []
    for raw, by_month in parsed['share'].items():
        if raw.strip().upper().startswith('TOTAL'):
            continue
        name, group = resolve(raw, names)
        for p, v in by_month.items():
            rows.append({'period': p, 'airline_raw': raw.strip(), 'airline': name,
                         'group': group, 'pax_lakh': round(v, 2),
                         'report': report, 'report_url': url})
    new_car = pd.DataFrame(rows)
    if new_car.empty:
        raise SystemExit('the market share table parsed to no carrier rows')

    # DGCA's own TOTAL row is the national figure; fall back to the sum
    totals = parsed['share'].get('TOTAL') or {}
    nat_by_month = {p: round(totals.get(p, new_car[new_car.period == p].pax_lakh.sum()), 2)
                    for p in months}

    new_car['share_pct_computed'] = [
        round(r.pax_lakh / nat_by_month[r.period] * 100, 2) for r in new_car.itertuples()]
    # DGCA prints the share too; where the parser did not get it, our own
    # figure stands in, and the validation gate then compares like with like
    mkt = parsed.get('share_pct') or {}
    new_car['share_pct_reported'] = [
        round(mkt.get(r.airline_raw, {}).get(r.period, r.share_pct_computed), 2)
        for r in new_car.itertuples()]
    new_car = new_car[list(car.columns)]
    # within a month, largest carrier first. The PDF prints one table with a
    # fixed row order for the whole year, but each month's ranking is its own
    # — Star Air sits above SpiceJet in September and below it in January —
    # and the page reads top-down, so the rows carry that ranking.
    new_car = (new_car.sort_values(['period', 'pax_lakh'], ascending=[True, False],
                                   kind='stable').reset_index(drop=True))

    # ---- load factor ---------------------------------------------------
    prows = []
    for raw, by_month in parsed['plf'].items():
        if raw.strip().upper().startswith('TOTAL'):
            continue
        name, group = resolve(raw, names)
        for p, v in by_month.items():
            prows.append({'period': p, 'airline_raw': raw.strip(), 'airline': name,
                          'group': group, 'plf_pct': round(v, 1),
                          'report': report, 'report_url': url})
    new_plf = pd.DataFrame(prows)[list(plf.columns)]

    # ---- national ------------------------------------------------------
    prev = nat.set_index('period').pax_lakh.to_dict()
    nrows = []
    for p in months:
        y, m = int(p[:4]), int(p[5:])
        py = f'{y - 1}-{m:02d}'
        pv = prev.get(py)
        pax = nat_by_month[p]
        yoy = round((pax / pv - 1) * 100, 2) if pv else None
        nrows.append({'period': p, 'pax_lakh': pax, 'pax_prev_year_lakh': pv,
                      'yoy_pct': yoy, 'yoy_basis': 'computed',
                      'month_yoy_pct_reported': parsed.get('yoy_reported', {}).get(p, yoy),
                      'month_report_url': url})
    new_nat = pd.DataFrame(nrows)[list(nat.columns)]

    def swap(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
        """Replace the months this report covers, keep everything else.

        Sorting by period alone, stably, is deliberate. Within a month the
        rows stay in the order DGCA prints them — largest carrier first —
        and re-sorting by airline would reshuffle four years of history for
        no gain. A kept month and a replaced month never share a period, so
        a stable sort puts each block exactly where it belongs.
        """
        kept = old[~old.period.isin(months)]
        return (pd.concat([kept, new], ignore_index=True)
                .sort_values('period', kind='stable')
                .reset_index(drop=True))

    car2, plf2, nat2 = swap(car, new_car), swap(plf, new_plf), swap(nat, new_nat)

    # ---- grouped, derived from the carrier rows ------------------------
    tot = car2.groupby('period').pax_lakh.sum()
    grp = (car2.groupby(['period', 'group'])
           .agg(pax_lakh=('pax_lakh', 'sum'),
                share_pct_reported=('share_pct_reported', 'sum'),
                carriers=('airline_raw', lambda s: ' + '.join(sorted(s))))
           .reset_index())
    grp['pax_lakh'] = grp.pax_lakh.round(2)
    grp['share_pct_reported'] = grp.share_pct_reported.round(2)
    grp['share_pct_computed'] = (grp.pax_lakh / grp.period.map(tot) * 100).round(2)
    grp = grp[list(pd.read_csv(DATA / 'market_share_grouped.csv').columns)]

    return {'market_share_by_carrier.csv': car2, 'plf_by_carrier.csv': plf2,
            'national_monthly_domestic.csv': nat2, 'market_share_grouped.csv': grp}


# ------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check-only', action='store_true')
    ap.add_argument('--pdf')
    ap.add_argument('--period')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--data', help='override the data directory (for testing)')
    a = ap.parse_args()

    global DATA
    if a.data:
        DATA = pathlib.Path(a.data)

    nat = pd.read_csv(DATA / 'national_monthly_domestic.csv')
    have = max(nat.period)
    log(f'site data currently runs to {have}')

    manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}
    names = load_names()

    if a.pdf:                                           # local file, for testing
        period = a.period or dgca_portal.month_from_filename(a.pdf)
        pdf, url = pathlib.Path(a.pdf), f'file://{a.pdf}'
    else:
        reports = dgca_portal.list_reports()
        log(f'portal lists {len(reports)} monthly reports, latest {max(reports)}')
        period = max(reports)
        url = reports[period]
        if period <= have and not a.force:
            log(f'nothing new: DGCA has not published past {have} yet')
            return 0
        meta = dgca_portal.head(url)
        if manifest.get(period, {}).get('last_modified') == meta['last_modified'] \
                and not a.force:
            log(f'{period} is listed but unchanged since the last run')
            return 0
        if a.check_only:
            log(f'NEW REPORT: {period}')
            return 10
        import requests
        log(f'downloading {url}')
        r = requests.get(url, timeout=120,
                         headers={'User-Agent': dgca_portal.UA})
        r.raise_for_status()
        pdf = HERE / 'raw' / f'DGCA_Domestic_{period}.pdf'
        pdf.parent.mkdir(exist_ok=True)
        pdf.write_bytes(r.content)
        manifest[period] = {'url': url, 'last_modified': meta['last_modified'],
                            'bytes': len(r.content),
                            'sha256': hashlib.sha256(r.content).hexdigest(),
                            'fetched': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}

    log(f'parsing {pdf.name} as {period}')
    parsed = dgca_parse.parse(pdf, period)
    parsed['url'] = url
    log(f'  months in the file: {parsed["months"]}')
    log(f'  carriers: {len(parsed["share"])}, load factors: {len(parsed["plf"])}')

    frames = merge(parsed, names)
    before = {k: pd.read_csv(DATA / k) for k in frames}
    for k, df in frames.items():
        df.to_csv(DATA / k, index=False)
        log(f'  {k}: {len(before[k])} -> {len(df)} rows')

    try:
        validate.run(DATA)
    except validate.Failure as e:
        for k, df in before.items():                    # leave the live data untouched
            df.to_csv(DATA / k, index=False)
        log(f'\nVALIDATION FAILED, changes rolled back: {e}')
        return 1

    # the curated bits: DGCA's headline YTD, and any new footnote to review
    meta_path = HERE / 'meta.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    if parsed.get('ytd'):
        y, m = int(period[:4]), int(period[5:])
        meta['ytd'] = dict(parsed['ytd'], label=f'January - {MON[m - 1]} {y}')
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n',
                             encoding='utf-8')

    export_site.write(DATA, meta_path)
    build_capacity.build(DATA)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    known = {e['detail'] for e in meta['events']}
    fresh = [n for n in parsed['footnotes']
             if not any(n[:40] in k or k[:40] in n for k in known)]

    log('\n' + '=' * 60)
    log(f'UPDATED to {period}')
    n = frames['national_monthly_domestic.csv']
    row = n[n.period == period].iloc[0]
    log(f'  {period}: {row.pax_lakh} lakh, {row.yoy_pct:+.2f}% against a year earlier')
    if fresh:
        log('  new DGCA footnotes, worth checking against pipeline/events.json:')
        for f in fresh:
            log(f'    - {f[:150]}')
    log('=' * 60)
    return 10


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (dgca_portal.DiscoveryError, dgca_parse.ParseError) as err:
        # a full traceback here just buries the one line that matters in the
        # issue the workflow opens
        log(f'\nREFRESH FAILED\n{err}')
        raise SystemExit(1) from None
