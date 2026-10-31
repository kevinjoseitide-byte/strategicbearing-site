#!/usr/bin/env python3
"""Derive implied seats from the DGCA set and fold them into the page data.

DGCA publishes passengers and a seat factor, but never seats. Seat factor is
passengers as a share of seats, so seats = passengers / seat factor. Doing that
per carrier and summing keeps the mix honest: a system-wide average applied to
the total would quietly assume every airline flies the same load.

Two things this is not. It is not DGCA data, and it is not independent of the
other charts: the gap between passenger growth and implied-seat growth is the
change in seat factor, near enough by construction. What it buys is a reframing
a reader can act on. "Seat factor fell four points" is a statistic. "The
industry held capacity while demand fell six per cent" is a decision.

Usage: build_capacity.py <site/data dir>
"""
import json
import pathlib
import sys

import pandas as pd

MIN_PLF = 5.0           # below this a carrier is not really operating


def build(data_dir):
    D = pathlib.Path(data_dir)
    car = pd.read_csv(D / 'market_share_by_carrier.csv')
    plf = pd.read_csv(D / 'plf_by_carrier.csv')

    m = car.merge(plf[['period', 'airline', 'plf_pct']], on=['period', 'airline'], how='left')
    dropped = m[(m.plf_pct.isna()) | (m.plf_pct <= MIN_PLF)]
    m = m[(m.plf_pct > MIN_PLF) & m.plf_pct.notna()].copy()
    m['seats_lakh'] = m.pax_lakh / (m.plf_pct / 100.0)

    nat = m.groupby('period').agg(pax=('pax_lakh', 'sum'), seats=('seats_lakh', 'sum'))
    nat['plf'] = nat.pax / nat.seats * 100
    nat['pax_yoy'] = (nat.pax / nat.pax.shift(12) - 1) * 100
    nat['seat_yoy'] = (nat.seats / nat.seats.shift(12) - 1) * 100
    nat['plf_chg'] = nat.plf - nat.plf.shift(12)

    rows = []
    for p, r in nat.iterrows():
        rows.append({
            'p': p,
            'pax': round(float(r.pax), 2),
            'seats': round(float(r.seats), 2),
            'plf': round(float(r.plf), 1),
            'pax_yoy': None if pd.isna(r.pax_yoy) else round(float(r.pax_yoy), 2),
            'seat_yoy': None if pd.isna(r.seat_yoy) else round(float(r.seat_yoy), 2),
            'plf_chg': None if pd.isna(r.plf_chg) else round(float(r.plf_chg), 2),
        })

    # per-carrier capacity change, latest month against a year earlier
    periods = list(nat.index)
    a, b = periods[-13], periods[-1]
    pc = m[m.period.isin([a, b])].pivot_table(index='airline', columns='period',
                                              values=['pax_lakh', 'seats_lakh', 'plf_pct'])
    carriers = []
    for air in pc.index:
        try:
            p0, p1 = pc[('pax_lakh', a)][air], pc[('pax_lakh', b)][air]
            s0, s1 = pc[('seats_lakh', a)][air], pc[('seats_lakh', b)][air]
            l0, l1 = pc[('plf_pct', a)][air], pc[('plf_pct', b)][air]
        except KeyError:
            continue
        if pd.isna(p0) or pd.isna(p1) or pd.isna(s0) or pd.isna(s1):
            continue
        carriers.append({'a': air,
                         'pax_pct': round((p1 / p0 - 1) * 100, 1),
                         'seat_pct': round((s1 / s0 - 1) * 100, 1),
                         'plf_chg': round(l1 - l0, 1)})
    carriers.sort(key=lambda r: r['seat_pct'])

    cap = {'from': a, 'to': b, 'national': rows, 'carriers': carriers,
           'min_plf': MIN_PLF,
           'excluded': sorted(set(dropped.airline.dropna()))}

    jp = D / 'dgca_domestic.json'
    doc = json.loads(jp.read_text(encoding='utf-8'))
    doc['capacity'] = cap
    jp.write_text(json.dumps(doc, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

    out = pd.DataFrame(rows).rename(columns={
        'p': 'period', 'pax': 'pax_lakh', 'seats': 'implied_seats_lakh',
        'plf': 'implied_system_seat_factor_pct', 'pax_yoy': 'pax_yoy_pct',
        'seat_yoy': 'implied_seats_yoy_pct', 'plf_chg': 'seat_factor_change_pp'})
    out.to_csv(D / 'implied_capacity.csv', index=False)

    print(f'capacity series: {len(rows)} months, {periods[0]} .. {periods[-1]}')
    print(f'carriers compared {a} -> {b}: {len(carriers)}')
    print(f'excluded (seat factor <= {MIN_PLF}% or missing): {cap["excluded"]}')
    print(f'latest: pax {rows[-1]["pax_yoy"]:+.2f}%  seats {rows[-1]["seat_yoy"]:+.2f}%  '
          f'seat factor {rows[-1]["plf"]:.1f}% ({rows[-1]["plf_chg"]:+.2f}pp)')
    print(f'wrote {jp.name} (+capacity) and implied_capacity.csv')


    return cap


if __name__ == '__main__':
    build(sys.argv[1])
