"""End to end: roll the data back a month, feed the report back through the
refresh, and check it lands exactly where it started."""
import io
import json
import pathlib
import re
import subprocess
import sys

import pandas as pd
import pytest

PIPELINE = pathlib.Path(__file__).resolve().parents[1]
S3 = ('https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/dataReports/'
      'aviationDataStatistics/airTransport/domestic/airTraffic/')

# DGCA prints a per-month growth figure that the synthetic report does not
# carry, so the refresh falls back to computing it. The two agree to a
# hundredth of a point; anything else in the file must match exactly.
FIXTURE_ONLY = {'month_yoy_pct_reported'}


@pytest.fixture(scope='module')
def replayed(tmp_path_factory, fake_report, latest):
    src = PIPELINE.parent / 'tools' / 'domestic-traffic' / 'data'
    work = tmp_path_factory.mktemp('replay') / 'data'
    import shutil
    shutil.copytree(src, work)
    before = {f.name: f.read_text(encoding='utf-8') for f in work.glob('*.csv')}
    before_json = json.loads((work / 'dgca_domestic.json').read_text(encoding='utf-8'))

    for f in work.glob('*.csv'):                     # roll back one month
        df = pd.read_csv(f)
        if 'period' in df.columns:
            df[df.period != latest].to_csv(f, index=False)

    r = subprocess.run(
        [sys.executable, str(PIPELINE / 'refresh.py'), '--pdf', str(fake_report),
         '--period', latest, '--data', str(work)],
        capture_output=True, text=True)
    assert r.returncode == 10, f'refresh exited {r.returncode}\n{r.stdout}\n{r.stderr}'
    return work, before, before_json, r.stdout


def _norm(t: str, fake: str) -> str:
    return re.sub(re.escape(fake), 'URL', re.sub(re.escape(S3) + r'[^,\n]*', 'URL', t))


@pytest.mark.parametrize('name', ['market_share_by_carrier.csv',
                                  'market_share_grouped.csv',
                                  'plf_by_carrier.csv',
                                  'implied_capacity.csv'])
def test_csv_reproduced_exactly(replayed, fake_report, name):
    work, before, _, _ = replayed
    fake = f'file://{fake_report}'
    got = _norm((work / name).read_text(encoding='utf-8'), fake)
    want = _norm(before[name], fake)
    assert got == want


def test_national_csv_reproduced(replayed, fake_report):
    work, before, _, _ = replayed
    fake = f'file://{fake_report}'
    a = pd.read_csv(io.StringIO(_norm(before['national_monthly_domestic.csv'], fake)))
    b = pd.read_csv(io.StringIO(
        _norm((work / 'national_monthly_domestic.csv').read_text(encoding='utf-8'), fake)))
    assert len(a) == len(b)
    for col in a.columns:
        if col in FIXTURE_ONLY:
            assert (a[col] - b[col]).abs().max() <= 0.011, col
        else:
            assert a[col].astype(str).equals(b[col].astype(str)), col


@pytest.mark.parametrize('key', ['as_of', 'as_of_label', 'share', 'share_raw',
                                 'plf', 'capacity', 'reports'])
def test_json_section_reproduced(replayed, key):
    work, _, before_json, _ = replayed
    got = json.loads((work / 'dgca_domestic.json').read_text(encoding='utf-8'))
    if key == 'reports':                             # the fixture's url is local
        assert set(got[key]) == set(before_json[key])
        return
    assert got[key] == before_json[key]


def test_run_reports_the_new_month(replayed, latest):
    _, _, _, out = replayed
    assert f'UPDATED to {latest}' in out
    assert 'all gates passed' in out
