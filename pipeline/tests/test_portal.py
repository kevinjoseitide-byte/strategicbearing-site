"""Discovery, against the shape the portal actually answers with.

This file exists because discovery failed twice in production on things an
archive of past URLs could not reveal.

The first failure: the paths are relative, not absolute URLs. The second: the
listing page is a shell, and the months arrive from one XHR to scan? whose
reply is JSON wrapping escaped HTML, where the links are `data-url` and not
`href` — the page's own JavaScript rewrites them on render. Reading the
browser's DOM showed href and hid all of this.

So the fixture is built in the response's real shape: real paths taken from
the live listing, wrapped the way scan? wraps them. A fixture that does not
look like the wire is a fixture that proves nothing.
"""
import json
import pathlib

import pytest

import dgca_portal

FIX = pathlib.Path(__file__).parent / 'fixtures' / 'portal_listing_paths.txt'


def _paths() -> list[str]:
    return [p for p in FIX.read_text(encoding='utf-8').splitlines() if p.strip()]


@pytest.fixture(scope='module')
def scan_response() -> str:
    """What scan? sends: JSON, with the table as an escaped HTML string."""
    rows = ''.join(
        f'<tr>\n\t<td align="" width="">&nbsp;</td>\n\t'
        f'<td width=""><font face=""><a data-url="{p}">month</a></font></td>\n</tr>'
        for p in _paths())
    return json.dumps({
        'ruleBookId': 4264, 'contentId': 4206, 'langId': 2,
        'ruleBookContentDtlsList': [{
            'year': '2020', 'no': '1/2020', 'contentId': 4206,
            'contentIdentifier': 'Air Traffic', 'contentName': 'Air Traffic',
            'contentText': f'<table border="0">{rows}</table>'}],
        'responseCode': 0})


@pytest.fixture(scope='module')
def listing_shell() -> str:
    """What the listing page sends: a shell with no reports in it."""
    return ('<!doctype html><html><body><form id="hiddenForm">'
            '<input type="hidden" name="ruleBookId" value="4264">'
            '</form><div id="content"></div></body></html>')


def test_reports_are_found_in_the_scan_reply(scan_response):
    found = dgca_portal.harvest(scan_response)
    assert len(found) > 40, 'data-url links inside escaped JSON were not picked up'
    assert all(u.startswith(f'https://{dgca_portal.BUCKET}/') for u in found.values())


def test_the_listing_page_alone_yields_nothing(listing_shell):
    """Documents the trap: the page is a shell. Discovery that only fetches
    it gets HTTP 200 and no reports, which reads like success."""
    assert dgca_portal.harvest(listing_shell) == {}


def test_every_month_in_the_site_data_is_discoverable(scan_response, data_dir):
    """Discovery must rebuild exactly the URLs already proven to download."""
    known = json.loads(
        (data_dir / 'dgca_domestic.json').read_text(encoding='utf-8'))['reports']
    found = dgca_portal.harvest(scan_response)
    missing = sorted(set(known) - set(found))
    assert not missing, f'listing did not yield {missing}'
    wrong = {p: (known[p], found[p]) for p in known if found[p] != known[p]}
    assert not wrong, f'URL built differently from the one that works: {wrong}'


def test_latest_month_is_the_newest_report(scan_response, latest):
    assert max(dgca_portal.harvest(scan_response)) == latest


def test_scan_fields_carry_what_the_server_requires(scan_response):
    """Sending only ruleBookId, contentId and serviceName gets HTTP 200 with a
    4 KB body and no reports. These four are what make the difference."""
    for k in ('screenId', 'actionVal', 'requestType', 'langType'):
        assert dgca_portal.SCAN_FIELDS.get(k), f'{k} missing from SCAN_FIELDS'
    assert dgca_portal.SCAN_FIELDS['actionVal'] == 'viewStaticData'
    assert dgca_portal.SCAN_FIELDS['requestType'] == 'ApplicationRH'


def test_unrelated_pdfs_are_ignored():
    """The reply carries other PDFs, one under a different path that also
    contains 'airTraffic'."""
    noise = ('<a data-url="jsp/dgca/topHeader/aboutDGCA/Ranking of FTOs-April 2026.pdf">x</a>'
             '<a data-url="jsp/dgca/InventoryList/personal/license/airTraffic/ATCOs.pdf">y</a>'
             '<a data-url="jsp/dgca/topHeader/contactUs/DirectoryHindi.pdf">z</a>')
    assert dgca_portal.harvest(noise) == {}


def test_undated_archive_files_are_skipped(scan_response):
    """Reports before 2015 are filed as Traffic_Rep0914.pdf, with no month
    name to read. They must be ignored rather than guessed at."""
    assert not [p for p in dgca_portal.harvest(scan_response) if p < '2015-01']


def test_absolute_urls_still_work():
    """Kept as a fallback in case the portal ever serves full URLs."""
    u = (f'https://{dgca_portal.BUCKET}/InventoryList/dataReports/'
         'aviationDataStatistics/airTransport/domestic/airTraffic/'
         'traffic%20Data%20Sep%2026.pdf')
    assert dgca_portal.harvest(f'<a href="{u}">x</a>') == {'2026-09': u}


def test_s3_url_encodes_spaces():
    u = dgca_portal.s3_url('jsp/dgca/InventoryList/dataReports/aviationDataStatistics/'
                           'airTransport/domestic/airTraffic/traffic Data Sep 26.pdf')
    assert u == ('https://public-prd-dgca.s3.ap-south-1.amazonaws.com/InventoryList/'
                 'dataReports/aviationDataStatistics/airTransport/domestic/airTraffic/'
                 'traffic%20Data%20Sep%2026.pdf')
