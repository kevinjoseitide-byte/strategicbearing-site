"""Shared fixtures: the repo's own data, and a synthetic DGCA report.

The synthetic PDF is built from the real figures already in the repo, laid
out the way a DGCA monthly report lays them out. It cannot prove the parser
survives DGCA's actual page furniture — only a live file does that — but it
does prove the row grouping, column centring, number matching, name
resolution, merge, grouped rebuild, validation and export all work on a
table of this shape, against a known answer.
"""
import pathlib
import shutil
import sys

import pandas as pd
import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

PIPELINE = pathlib.Path(__file__).resolve().parents[1]
ROOT = PIPELINE.parent
DATA = ROOT / 'tools' / 'domestic-traffic' / 'data'
MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP',
          'OCT', 'NOV', 'DEC']

sys.path.insert(0, str(PIPELINE))


@pytest.fixture(scope='session')
def data_dir() -> pathlib.Path:
    assert DATA.exists(), f'site data not found at {DATA}'
    return DATA


@pytest.fixture
def work_data(tmp_path, data_dir) -> pathlib.Path:
    """A throwaway copy of the live data."""
    d = tmp_path / 'data'
    shutil.copytree(data_dir, d)
    return d


@pytest.fixture(scope='session')
def latest(data_dir) -> str:
    return max(pd.read_csv(data_dir / 'national_monthly_domestic.csv').period)


@pytest.fixture(scope='session')
def fake_report(tmp_path_factory, data_dir, latest) -> pathlib.Path:
    """A DGCA-shaped PDF carrying the real figures for the latest month."""
    year = latest[:4]
    n_mon = int(latest[5:])
    mon = MONTHS[:n_mon]

    car = pd.read_csv(data_dir / 'market_share_by_carrier.csv')
    plf = pd.read_csv(data_dir / 'plf_by_carrier.csv')
    car = car[car.period.str.startswith(year)]
    plf = plf[plf.period.str.startswith(year)]

    ytd = pd.read_csv(data_dir / 'national_monthly_domestic.csv')
    import json
    meta = json.loads((PIPELINE / 'meta.json').read_text(encoding='utf-8'))['ytd']

    out = tmp_path_factory.mktemp('pdf') / f'DGCA_Domestic_{latest}.pdf'
    W, H = landscape(A4)
    c = canvas.Canvas(str(out), pagesize=(W, H))

    c.setFont('Helvetica-Bold', 13)
    c.drawString(40, H - 50, f'TRAFFIC - DOMESTIC: {mon[-1]} {year}')
    c.setFont('Helvetica', 10)
    lines = [
        f'Passengers carried by domestic airlines during {mon[0].title()}-'
        f'{mon[-1].title()} {year} were {meta["pax"]} lakh as',
        f'against {meta["prev"]} lakh during the corresponding period of previous '
        f'year thereby',
        f'registering a growth of {meta["growth"]}%.',
        '',
        '* Air India Group includes Air India & Air India Express.',
        '** Flybig suspended scheduled flights operation during October 2025.']
    for i, ln in enumerate(lines):
        c.drawString(40, H - 80 - i * 15, ln)
    c.showPage()

    def table(title, rows, value, fmt):
        c.setFont('Helvetica-Bold', 11)
        c.drawString(40, H - 45, title)
        x0, dx, y = 150, 62.0, H - 75
        c.setFont('Helvetica-Bold', 9)
        c.drawString(40, y, 'AIRLINES')
        for j, m in enumerate(mon):
            c.drawRightString(x0 + j * dx + 44, y, m)
        c.setFont('Helvetica', 9)
        for i, lab in enumerate(rows):
            yy = y - 20 - i * 15
            c.drawString(40, yy, lab)
            for j in range(len(mon)):
                v = value(lab, f'{year}-{j + 1:02d}')
                if v is not None and not pd.isna(v):
                    c.drawRightString(x0 + j * dx + 44, yy, fmt.format(v))
        c.showPage()

    pax = {(r.airline_raw, r.period): r.pax_lakh for r in car.itertuples()}
    pct = {(r.airline_raw, r.period): r.share_pct_reported for r in car.itertuples()}
    lf = {(r.airline_raw, r.period): r.plf_pct for r in plf.itertuples()}
    tot = car.groupby('period').pax_lakh.sum().round(2).to_dict()
    order = list(car[car.period == latest].airline_raw)
    lf_order = list(plf[plf.period == latest].airline_raw)

    table('PASSENGERS CARRIED BY DOMESTIC AIRLINES (IN LAKHS)',
          order + ['TOTAL'],
          lambda a, p: tot.get(p) if a == 'TOTAL' else pax.get((a, p)), '{:.2f}')
    table('MARKET SHARE OF DOMESTIC AIRLINES (%)',
          order, lambda a, p: pct.get((a, p)), '{:.2f}')
    table('TABLE 1: PASSENGER LOAD FACTOR (%)',
          lf_order, lambda a, p: lf.get((a, p)), '{:.1f}')
    c.save()
    assert ytd is not None
    return out
