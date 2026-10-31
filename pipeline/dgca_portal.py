#!/usr/bin/env python3
"""Find DGCA's monthly domestic traffic reports.

Never build these URLs by pattern. Across 45 consecutive months DGCA has
filed the same report as Jan2023.pdf, Traffic report Oct 23.pdf, traffic
Data Mar 24_240415_193719.pdf, TrafficReportApril2026.pdf and traffic Data
Sep 26.pdf. There is no convention to extrapolate, and the S3 bucket blocks
directory listing, so the only honest way to find next month's file is to
read the portal's own listing.

The portal is a JavaScript app, but the listing behind it is one form POST
that returns JSON with an HTML fragment in it. No cookies, no captcha, no
browser needed.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sys
import urllib.parse

import requests

PORTAL = 'https://www.dgca.gov.in/digigov-portal'
SCAN = f'{PORTAL}/scan?'
# the "Air Transport / Domestic / Air Traffic" listing
RULEBOOK_ID = '4264'
CONTENT_ID = '4206'
BUCKET = 'public-prd-dgca.s3.ap-south-1.amazonaws.com'
PATH_HINT = 'airTransport/domestic/airTraffic'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0 Safari/537.36')
TIMEOUT = 45

MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7,
    'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12,
    'december': 12,
}
_MONTH_RE = re.compile(
    r'(january|february|september|december|november|october|august|'
    r'march|april|june|july|sept|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
    re.I)


class DiscoveryError(RuntimeError):
    pass


def month_from_filename(name: str) -> str | None:
    """Map a DGCA report filename to 'YYYY-MM', or None if it is not one.

    Handles every shape seen since January 2023: full or abbreviated month
    names, two- or four-digit years, with or without separators, and the
    _YYMMDD_HHMMSS export suffix DGCA sometimes leaves on.
    """
    base = urllib.parse.unquote(name).rsplit('/', 1)[-1]
    base = re.sub(r'\.pdf$', '', base, flags=re.I)
    # strip a trailing export stamp (_240415_193719) before looking for a year
    base = re.sub(r'_\d{6}_\d{6}$', '', base)

    m = _MONTH_RE.search(base)
    if not m:
        return None
    mon = MONTHS[m.group(1).lower()]

    # the year is the number nearest the month token, on either side
    tail, head = base[m.end():], base[:m.start()]
    y = re.search(r'(\d{4}|\d{2})', tail) or re.search(r'(\d{4}|\d{2})(?!.*\d)', head)
    if not y:
        return None
    yr = int(y.group(1))
    if yr < 100:
        yr += 2000
    if not (2000 <= yr <= dt.date.today().year + 1):
        return None
    return f'{yr:04d}-{mon:02d}'


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({'User-Agent': UA,
                      'Accept': 'application/json, text/javascript, */*; q=0.01',
                      'X-Requested-With': 'XMLHttpRequest'})
    return s


def list_reports(session: requests.Session | None = None) -> dict[str, str]:
    """Return {'YYYY-MM': url} for every monthly domestic traffic report listed."""
    s = session or _session()
    try:
        s.get(f'{PORTAL}/', timeout=TIMEOUT)          # pick up any cookie the app sets
        r = s.post(SCAN, timeout=TIMEOUT, data={
            'ruleBookId': RULEBOOK_ID,
            'contentId': CONTENT_ID,
            'serviceName': 'getParentData',
        })
        r.raise_for_status()
        body = r.text
    except requests.RequestException as e:
        raise DiscoveryError(f'could not reach the DGCA portal: {e}') from e

    # the JSON carries an HTML fragment; the links are what we are after,
    # so pull them out of the raw text rather than guessing the JSON shape
    body = html.unescape(body).replace('\\/', '/').replace('\\"', '"')
    urls = re.findall(r'https?://[^\s"\'<>\\]+?\.pdf', body, re.I)

    out: dict[str, str] = {}
    for u in urls:
        if BUCKET not in u or PATH_HINT not in u:
            continue
        p = month_from_filename(u)
        if p:
            out.setdefault(p, u)                      # first listed wins; newest is listed first
    if not out:
        raise DiscoveryError(
            f'the portal answered ({len(body):,} bytes) but no monthly traffic '
            f'PDF links were found. The listing has probably moved — check '
            f'ruleBookId={RULEBOOK_ID} contentId={CONTENT_ID}.')
    return out


def head(url: str, session: requests.Session | None = None) -> dict:
    """Last-Modified and size, so an unchanged file costs one cheap request."""
    s = session or _session()
    r = s.head(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return {'last_modified': r.headers.get('Last-Modified'),
            'length': int(r.headers.get('Content-Length', 0))}


if __name__ == '__main__':
    reps = list_reports()
    for p in sorted(reps)[-6:]:
        print(f'{p}  {urllib.parse.unquote(reps[p].rsplit("/", 1)[-1])}')
    print(f'\n{len(reps)} monthly reports listed, latest {max(reps)}', file=sys.stderr)
