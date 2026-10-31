"""Discovery, against the DGCA listing page as it really is.

The fixture is the set of report paths captured from the live portal. It
exists because the first live run failed on exactly this: the page carries
relative hrefs, not absolute URLs, so a regex looking for https://...pdf
matched nothing and discovery reported an empty listing. A fixture taken
from the real page is the only thing that would have caught it.
"""
import json
import pathlib

import pytest

import dgca_portal

FIX = pathlib.Path(__file__).parent / 'fixtures' / 'portal_listing_paths.txt'


@pytest.fixture(scope='module')
def listing_html() -> str:
    """The paths wrapped in anchors, the way the portal serves them."""
    paths = [p for p in FIX.read_text(encoding='utf-8').splitlines() if p.strip()]
    rows = '\n'.join(f'<li><a target="_blank" href="{p}">report</a></li>' for p in paths)
    return f'<!doctype html><html><body><ul>{rows}</ul></body></html>'


def test_harvest_finds_relative_hrefs(listing_html):
    found = dgca_portal.harvest(listing_html)
    assert len(found) > 40, 'relative hrefs were not picked up'
    assert all(u.startswith(f'https://{dgca_portal.BUCKET}/') for u in found.values())


def test_every_month_in_the_site_data_is_discoverable(listing_html, data_dir):
    """Discovery must produce exactly the URLs already proven to work."""
    known = json.loads(
        (data_dir / 'dgca_domestic.json').read_text(encoding='utf-8'))['reports']
    found = dgca_portal.harvest(listing_html)
    missing = sorted(set(known) - set(found))
    assert not missing, f'listing did not yield {missing}'
    wrong = {p: (known[p], found[p]) for p in known if found[p] != known[p]}
    assert not wrong, f'URL built differently from the one that works: {wrong}'


def test_latest_month_is_the_newest_report(listing_html, latest):
    found = dgca_portal.harvest(listing_html)
    assert max(found) == latest


def test_unrelated_pdfs_are_ignored():
    """The portal home carries hundreds of other PDFs, including one under a
    different path that also contains 'airTraffic'."""
    noise = ('<a href="jsp/dgca/topHeader/aboutDGCA/Ranking of FTOs-April 2026.pdf">x</a>'
             '<a href="jsp/dgca/InventoryList/personal/license/airTraffic/ATCOs.pdf">y</a>'
             '<a href="jsp/dgca/topHeader/contactUs/DirectoryHindi.pdf">z</a>')
    assert dgca_portal.harvest(noise) == {}


def test_undated_archive_files_are_skipped(listing_html):
    """Reports before 2015 are filed as Traffic_Rep0914.pdf, with no month
    name to read. They must be ignored rather than guessed at."""
    found = dgca_portal.harvest(listing_html)
    assert not [p for p in found if p < '2015-01']


def test_s3_url_encodes_spaces():
    u = dgca_portal.s3_url('jsp/dgca/InventoryList/dataReports/aviationDataStatistics/'
                           'airTransport/domestic/airTraffic/traffic Data Sep 26.pdf')
    assert u == ('https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/'
                 'dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/'
                 'traffic%20Data%20Sep%2026.pdf')
