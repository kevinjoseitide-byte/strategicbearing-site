#!/usr/bin/env python3
"""Rebuild the page's data file from the tidy CSVs.

The CSVs are the record; dgca_domestic.json is a compact projection of them
for the browser. Keeping the projection derived rather than hand-edited means
a refresh can never leave the page and the downloads disagreeing.

Curated material that is not in the CSVs — DGCA's footnote events, the
year-to-date headline, and the PDF-vs-XLSX check results — lives in
pipeline/meta.json and is merged in here.

    python3 pipeline/export_site.py tools/domestic-traffic/data
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import pandas as pd

MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
       'August', 'September', 'October', 'November', 'December']
HERE = pathlib.Path(__file__).resolve().parent


def _n(v):
    """None for a missing value, otherwise the number exactly as the CSV has it.

    No re-rounding here. DGCA prints two decimals where a share is below a
    tenth of a point (IndiaOne Air at 0.01%), and rounding those to one
    decimal turns a real carrier into a zero. The CSV already holds the
    published precision, so the projection carries it rather than imposing
    a format of its own.
    """
    if v is None or pd.isna(v):
        return None
    return float(v)


def build(data_dir: str | pathlib.Path, meta_path: str | pathlib.Path | None = None) -> dict:
    d = pathlib.Path(data_dir)
    meta = json.loads(pathlib.Path(meta_path or HERE / 'meta.json').read_text(encoding='utf-8'))

    nat = pd.read_csv(d / 'national_monthly_domestic.csv').sort_values('period')
    car = pd.read_csv(d / 'market_share_by_carrier.csv')
    grp = pd.read_csv(d / 'market_share_grouped.csv')
    plf = pd.read_csv(d / 'plf_by_carrier.csv')

    as_of = str(nat.period.iloc[-1])
    y, m = as_of.split('-')
    as_of_label = f'{MON[int(m) - 1][:3]} {y}'

    doc = {
        'as_of': as_of,
        'as_of_label': as_of_label,
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'),
        'source': 'DGCA, Government of India',
        'reports': {str(r.period): str(r.month_report_url) for r in nat.itertuples()},
        'national': [
            {'p': str(r.period), 'pax': _n(r.pax_lakh), 'yoy': _n(r.yoy_pct),
             'basis': str(r.yoy_basis), 'yoy_dgca': _n(r.month_yoy_pct_reported)}
            for r in nat.itertuples()],
        'share': [
            {'p': str(r.period), 'g': str(r.group), 'pax': _n(r.pax_lakh),
             's': _n(r.share_pct_reported), 'c': str(r.carriers)}
            for r in grp.itertuples()],
        'share_raw': [
            {'p': str(r.period), 'a': str(r.airline), 's': _n(r.share_pct_reported),
             'pax': _n(r.pax_lakh)}
            for r in car.itertuples()],
        'plf': [
            {'p': str(r.period), 'a': str(r.airline), 'v': _n(r.plf_pct)}
            for r in plf.itertuples()],
        'ytd': meta['ytd'],
        'checks': {'n': int(meta['checks']['n']), 'months': int(nat.period.nunique()),
                   'fails': meta['checks']['fails']},
        'events': meta['events'],
    }
    return doc


def write(data_dir: str | pathlib.Path, meta_path=None) -> pathlib.Path:
    d = pathlib.Path(data_dir)
    doc = build(d, meta_path)
    p = d / 'dgca_domestic.json'
    # separators matter: the file ships as-is and every byte is bandwidth
    p.write_text(json.dumps(doc, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    print(f'export_site: {p.name} {p.stat().st_size:,} bytes, as of {doc["as_of_label"]}, '
          f'{len(doc["national"])} months')
    return p


if __name__ == '__main__':
    write(sys.argv[1] if len(sys.argv) > 1 else 'tools/domestic-traffic/data')
