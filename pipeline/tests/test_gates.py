"""A gate that never fails is decoration. Corrupt the data each way and
check the matching gate catches it."""
import pandas as pd
import pytest

import validate


def edit(d, fname, fn):
    """Apply a mutation and write it back.

    fn may return a new frame or mutate in place; returning is preferred,
    since the inplace keyword is on its way out of pandas.
    """
    p = d / fname
    df = pd.read_csv(p)
    out = fn(df)
    (df if out is None else out).to_csv(p, index=False)


def test_live_data_passes(data_dir):
    validate.run(data_dir)


def test_major_carrier_row_dropped(work_data):
    edit(work_data, 'market_share_by_carrier.csv',
         lambda x: x.drop(x[(x.period == x.period.max()) &
                            (x.airline == 'IndiGo')].index))
    with pytest.raises(validate.Failure, match='sum to the national total'):
        validate.run(work_data)


def test_decimal_point_slipped(work_data):
    edit(work_data, 'market_share_by_carrier.csv',
         lambda x: x.__setitem__('pax_lakh', x.pax_lakh.mask(
             (x.period == x.period.max()) & (x.airline == 'IndiGo'), x.pax_lakh * 10)))
    with pytest.raises(validate.Failure, match='sum to the national total'):
        validate.run(work_data)


def test_grouped_share_misparsed(work_data):
    edit(work_data, 'market_share_grouped.csv',
         lambda x: x.__setitem__('share_pct_reported',
                                 x.share_pct_reported.mask(x.index == len(x) - 1, 9.9)))
    with pytest.raises(validate.Failure, match='add to 100'):
        validate.run(work_data)


def test_seat_factor_out_of_range(work_data):
    edit(work_data, 'plf_by_carrier.csv',
         lambda x: x.__setitem__('plf_pct',
                                 x.plf_pct.mask(x.index == len(x) - 1, 810.0)))
    with pytest.raises(validate.Failure, match='outside 0..100'):
        validate.run(work_data)


def test_month_missing(work_data):
    edit(work_data, 'national_monthly_domestic.csv',
         lambda x: x.drop(x.index[20]))
    with pytest.raises(validate.Failure, match='gap in the monthly series'):
        validate.run(work_data)


def test_yoy_disagrees_with_dgca(work_data):
    edit(work_data, 'national_monthly_domestic.csv',
         lambda x: x.__setitem__('yoy_pct',
                                 x.yoy_pct.mask(x.index == len(x) - 1, 2.5)))
    with pytest.raises(validate.Failure, match='YoY disagrees'):
        validate.run(work_data)


def test_real_carrier_vanishing_blocks(work_data):
    """The dangerous case the sum gate cannot see.

    DGCA's table carries its own TOTAL row, and when it does, a lost carrier
    shows up as rows not summing to it. But if that TOTAL is ever missing,
    the national figure falls back to the sum of the carriers — the same
    parse that lost the row — and the sum gate becomes self-consistent and
    blind. This reproduces that: drop a carrier and move the national total
    down to match, so only the vanished-carrier gate is left to catch it.
    """
    car = pd.read_csv(work_data / 'market_share_by_carrier.csv')
    nat = pd.read_csv(work_data / 'national_monthly_domestic.csv')
    last = car.period.max()
    victim = car[(car.period == last) & (car.pax_lakh.between(0.3, 5))]
    if victim.empty:
        pytest.skip('no mid-sized carrier in the latest month to drop')
    v = victim.iloc[0]
    car[~((car.period == last) & (car.airline == v.airline))].to_csv(
        work_data / 'market_share_by_carrier.csv', index=False)
    nat['pax_lakh'] = nat.pax_lakh.mask(nat.period == last,
                                        (nat.pax_lakh - v.pax_lakh).round(2))
    nat.to_csv(work_data / 'national_monthly_domestic.csv', index=False)
    with pytest.raises(validate.Failure, match='vanished'):
        validate.run(work_data)


def test_tiny_carrier_vanishing_only_warns(work_data):
    """A carrier flying 0.01 lakh sits below every tolerance. Small operators
    do stop flying, so this warns rather than blocking a whole refresh."""
    df = pd.read_csv(work_data / 'market_share_by_carrier.csv')
    last = df.period.max()
    tiny = df[(df.period == last) & (df.pax_lakh < 0.1)]
    if tiny.empty:
        pytest.skip('no sub-0.1-lakh carrier in the latest month')
    name = tiny.iloc[0].airline
    df[~((df.period == last) & (df.airline == name))].to_csv(
        work_data / 'market_share_by_carrier.csv', index=False)
    warnings = validate.run(work_data)
    assert any('dropped out' in w for w in warnings)
