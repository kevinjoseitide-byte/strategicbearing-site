"""The page's JSON is a projection of the CSVs, so rebuilding it from them
must reproduce the shipped file section for section."""
import json

import export_site


def test_round_trip(data_dir):
    shipped = json.loads((data_dir / 'dgca_domestic.json').read_text(encoding='utf-8'))
    built = export_site.build(data_dir)
    shipped.pop('capacity', None)          # added afterwards by build_capacity
    shipped.pop('generated')
    built.pop('generated')
    assert sorted(shipped) == sorted(built)
    for k in shipped:
        assert built[k] == shipped[k], k


def test_tiny_shares_keep_their_precision(data_dir):
    """DGCA prints two decimals where a share is under a tenth of a point.
    Rounding those to one decimal turns a real carrier into a zero."""
    built = export_site.build(data_dir)
    small = [r for r in built['share_raw'] if r['s'] is not None and 0 < r['s'] < 0.1]
    assert small, 'expected at least one sub-0.1% carrier in the series'
    assert all(r['s'] > 0 for r in small)
