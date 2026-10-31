#!/usr/bin/env python3
"""Validation gates for the DGCA domestic traffic set.

Nothing publishes unless every gate passes. A parser that silently drops a
column or misreads a decimal point is worse than a parser that crashes: the
page would keep working and keep being wrong. So these checks are the
difference between a refresh that is automatic and one that is trustworthy.

Run standalone against the live data to confirm the gates still hold:

    python3 pipeline/validate.py tools/domestic-traffic/data
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# tolerances, chosen against four years of real DGCA files
TOL_SUM_LAKH = 0.10     # airline rows vs the national total, in lakh
TOL_SHARE_PCT = 0.60    # reported shares summing to 100
TOL_SHARE_ROW = 0.15    # one carrier's reported share vs the computed one
TOL_YOY_PP = 0.10       # our YoY vs the YoY DGCA prints
SIGMA_MOM = 3.0         # month-on-month move flagged for a human look
MIN_CARRIER_LAKH = 0.25  # a carrier above this must not silently disappear


class Failure(Exception):
    pass


def _load(d: pathlib.Path):
    return (pd.read_csv(d / 'national_monthly_domestic.csv'),
            pd.read_csv(d / 'market_share_by_carrier.csv'),
            pd.read_csv(d / 'market_share_grouped.csv'),
            pd.read_csv(d / 'plf_by_carrier.csv'))


def run(data_dir: str | pathlib.Path) -> list[str]:
    """Return a list of warnings. Raise Failure on anything that blocks."""
    d = pathlib.Path(data_dir)
    nat, car, grp, plf = _load(d)
    warn: list[str] = []

    # ---- 1. every airline row adds up to the national total -------------
    s = car.groupby('period').pax_lakh.sum().round(2)
    j = nat.set_index('period').pax_lakh.round(2)
    gap = (s - j).abs().dropna()
    if len(gap) and gap.max() > TOL_SUM_LAKH:
        bad = gap[gap > TOL_SUM_LAKH]
        raise Failure(f'airline pax do not sum to the national total in '
                      f'{len(bad)} month(s), worst {bad.max():.2f} lakh: '
                      f'{list(bad.index)[:5]}')

    # ---- 2. reported shares add to 100 ----------------------------------
    t = grp.groupby('period').share_pct_reported.sum()
    off = (t - 100).abs()
    if len(off) and off.max() > TOL_SHARE_PCT:
        bad = off[off > TOL_SHARE_PCT]
        raise Failure(f'grouped shares do not add to 100 in {len(bad)} '
                      f'month(s), worst {bad.max():.2f}pp: {list(bad.index)[:5]}')

    # ---- 3. our arithmetic against DGCA's own printed figures -----------
    rs = (car.share_pct_reported - car.share_pct_computed).abs()
    if len(rs) and rs.max() > TOL_SHARE_ROW:
        k = car.loc[rs.idxmax()]
        raise Failure(f'a carrier share disagrees with DGCA by '
                      f'{rs.max():.2f}pp: {k.period} {k.airline}')

    y = nat.dropna(subset=['yoy_pct', 'month_yoy_pct_reported'])
    dy = (y.yoy_pct - y.month_yoy_pct_reported).abs()
    if len(dy) and dy.max() > TOL_YOY_PP:
        k = y.loc[dy.idxmax()]
        raise Failure(f'our YoY disagrees with the YoY DGCA prints by '
                      f'{dy.max():.2f}pp in {k.period}')

    # ---- 4. values inside their physical range --------------------------
    for name, col, lo, hi in (('plf_pct', plf.plf_pct, 0, 100),
                              ('share_pct_reported', car.share_pct_reported, 0, 100),
                              ('pax_lakh', car.pax_lakh, 0, 10_000)):
        bad = col[(col < lo) | (col > hi)].dropna()
        if len(bad):
            raise Failure(f'{name} outside {lo}..{hi} in {len(bad)} row(s): '
                          f'{list(bad.head(3))}')

    # ---- 5. a continuous monthly series, no gaps ------------------------
    p = pd.PeriodIndex(nat.period.sort_values(), freq='M')
    missing = pd.period_range(p.min(), p.max(), freq='M').difference(p)
    if len(missing):
        raise Failure(f'gap in the monthly series: {[str(m) for m in missing]}')

    # ---- 6. soft: an unusual month-on-month move ------------------------
    mom = nat.sort_values('period').pax_lakh.pct_change() * 100
    if mom.std(ddof=0) > 0:
        z = (mom - mom.mean()) / mom.std(ddof=0)
        for i in z[z.abs() > SIGMA_MOM].index:
            warn.append(f'{nat.period[i]}: month-on-month {mom[i]:+.1f}% is '
                        f'{z[i]:+.1f}σ, worth a look before publishing')

    # ---- 7. a carrier disappearing --------------------------------------
    # The sum gate cannot see this. A carrier flying 0.01 lakh sits an order
    # of magnitude below the 0.10 lakh tolerance, so dropping its row leaves
    # the total untouched. Small operators do stop flying, so this only
    # blocks when a carrier with real traffic vanishes: that is a parser
    # that lost a row, not an airline that lost its licence.
    months = sorted(car.period.unique())
    if len(months) >= 2:
        prev = car[car.period == months[-2]].set_index('airline').pax_lakh
        a, b = set(prev.index), set(car[car.period == months[-1]].airline)
        for x in sorted(b - a):
            warn.append(f'{months[-1]}: new carrier "{x}" in the table')
        gone = {x: prev[x] for x in sorted(a - b)}
        big = {x: v for x, v in gone.items() if v >= MIN_CARRIER_LAKH}
        if big:
            raise Failure(
                f'{months[-1]}: carrier(s) with real traffic vanished from the '
                f'table — ' + ', '.join(f'{x} ({v:.2f} lakh last month)'
                                        for x, v in big.items()) +
                '. If this is a genuine exit, add it to pipeline/events.json.')
        for x, v in gone.items():
            warn.append(f'{months[-1]}: carrier "{x}" has dropped out '
                        f'(was {v:.2f} lakh, below the {MIN_CARRIER_LAKH} lakh '
                        f'threshold, so not blocking)')

    print(f'validate: {len(nat)} months, {len(car)} carrier-months, '
          f'{len(plf)} seat-factor rows — all gates passed')
    for w in warn:
        print(f'  warning: {w}')
    return warn


if __name__ == '__main__':
    try:
        run(sys.argv[1] if len(sys.argv) > 1 else 'tools/domestic-traffic/data')
    except Failure as e:
        print(f'VALIDATION FAILED: {e}', file=sys.stderr)
        raise SystemExit(1)
