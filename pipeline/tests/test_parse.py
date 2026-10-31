"""The parser, against a DGCA-shaped PDF holding the real figures."""
import pandas as pd
import pytest

import dgca_parse
import dgca_portal


@pytest.fixture(scope='module')
def parsed(fake_report, latest):
    return dgca_parse.parse(fake_report, latest)


def test_every_month_column_found(parsed, latest):
    assert parsed['months'][-1] == latest
    assert len(parsed['months']) == int(latest[5:])


def test_passenger_figures_recovered(parsed, data_dir, latest):
    car = pd.read_csv(data_dir / 'market_share_by_carrier.csv')
    car = car[car.period.str.startswith(latest[:4])]
    for r in car.itertuples():
        got = parsed['share'].get(r.airline_raw, {}).get(r.period)
        assert got == pytest.approx(r.pax_lakh, abs=0.005), \
            f'{r.airline_raw} {r.period}'


def test_load_factors_recovered(parsed, data_dir, latest):
    plf = pd.read_csv(data_dir / 'plf_by_carrier.csv')
    plf = plf[plf.period.str.startswith(latest[:4])]
    for r in plf.itertuples():
        got = parsed['plf'].get(r.airline_raw, {}).get(r.period)
        assert got == pytest.approx(r.plf_pct, abs=0.05), f'{r.airline_raw} {r.period}'


def test_total_row(parsed, data_dir, latest):
    nat = pd.read_csv(data_dir / 'national_monthly_domestic.csv')
    want = float(nat[nat.period == latest].pax_lakh.iloc[0])
    assert parsed['share']['TOTAL'][latest] == pytest.approx(want, abs=0.02)


def test_printed_share_table_found(parsed):
    assert parsed['share_pct_source'] == 'dgca'
    assert parsed['share_pct']


def test_ytd_headline_sentence(parsed):
    assert parsed['ytd'] and parsed['ytd']['pax'] > 0
    assert parsed['ytd']['scope'] == 'ytd'


def test_footnotes(parsed):
    assert len(parsed['footnotes']) >= 2


def test_wrong_year_is_rejected(fake_report, latest):
    """The column headers are bare month names, so the year comes from the
    filename. A report filed under the wrong year would otherwise produce
    rows that look perfectly consistent and are a year out."""
    y, m = int(latest[:4]), int(latest[5:])
    with pytest.raises(dgca_parse.ParseError, match='never names that month'):
        dgca_parse.parse(fake_report, f'{y - 1}-{m:02d}')


def test_wrong_month_is_rejected(fake_report, latest):
    """A file that does not reach the month it is claimed to cover must stop
    the run, not quietly produce rows for the wrong period."""
    y = int(latest[:4])
    with pytest.raises(dgca_parse.ParseError, match='supposed to cover'):
        dgca_parse.parse(fake_report, f'{y}-12')


# ---- the filename rule, against every real DGCA report ------------------
def test_every_real_filename_maps(data_dir):
    import json
    reports = json.loads(
        (data_dir / 'dgca_domestic.json').read_text(encoding='utf-8'))['reports']
    assert len(reports) >= 45
    for period, url in reports.items():
        assert dgca_portal.month_from_filename(url) == period, url


@pytest.mark.parametrize('name,want', [
    ('Traffic Report Oct 2026.pdf', '2026-10'),
    ('trafficdataoctober26.pdf', '2026-10'),
    ('Traffic Data Report October 2026.pdf', '2026-10'),
    ('traffic Data Oct 26_261128_101500.pdf', '2026-10'),
    ('TrafficDataOct26.pdf', '2026-10'),
    ('traffic report Sept 26.pdf', '2026-09'),
    ('Traffic report Jan 27.pdf', '2027-01'),
    ('annual report 2025.pdf', None),
    ('handbook-2024-25.pdf', None),
])
def test_filename_shapes_not_yet_seen(name, want):
    assert dgca_portal.month_from_filename(name) == want
