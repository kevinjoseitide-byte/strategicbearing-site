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
# the "Air Transport / Domestic / Air Traffic" listing. It is a plain GET:
# the page is a JavaScript app, but the year/month picker is rendered server
# side, so every report back to 2014 is already in the HTML when it arrives.
RULEBOOK_ID = '4264'
CONTENT_ID = '4206'
LISTING = f'{PORTAL}/?page={RULEBOOK_ID}/{CONTENT_ID}/servicename'
BUCKET = 'public-prd-dgca.s3.ap-south-1.amazonaws.com'
PATH_HINT = 'airTransport/domestic/airTraffic'
# What the page actually carries. Not an absolute URL — a path relative to
# the portal, which the site rewrites to the S3 bucket by dropping jsp/dgca/.
HREF_RE = re.compile(
    r'jsp/dgca/(InventoryList/dataReports/aviationDataStatistics/'
    r'airTransport/domestic/airTraffic/[^"\'<>]+?\.pdf)', re.I)

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


def s3_url(path: str) -> str:
    """Portal path -> the bucket URL that actually serves the file."""
    rest = path.split('jsp/dgca/', 1)[-1].lstrip('/')
    return f'https://{BUCKET}/' + urllib.parse.quote(rest, safe='/')


def harvest(body: str) -> dict[str, str]:
    """Pull monthly report links out of the listing HTML.

    These are relative hrefs, not absolute URLs. Looking only for http(s)
    links finds nothing here — which is exactly how the first live run
    failed. Absolute URLs are still accepted in case the portal changes.
    """
    body = html.unescape(body).replace('\\/', '/').replace('\\"', '"')
    out: dict[str, str] = {}
    for rel in HREF_RE.findall(body):
        p = month_from_filename(rel)
        if p:
            out.setdefault(p, s3_url(rel))
    for u in re.findall(r'https?://[^\s"\'<>\\]+?\.pdf', body, re.I):
        if BUCKET in u and PATH_HINT in u:
            p = month_from_filename(u)
            if p:
                out.setdefault(p, u)
    return out


def list_reports(session: requests.Session | None = None,
                 verbose: bool = False) -> dict[str, str]:
    """Return {'YYYY-MM': url} for every monthly domestic traffic report listed."""
    s = session or _session()
    report: list[str] = []
    for label, url in (('listing page', LISTING), ('portal home', f'{PORTAL}/')):
        try:
            r = s.get(url, timeout=TIMEOUT)
            found = harvest(r.text) if r.ok else {}
            report.append(f'  {label} ({url}): HTTP {r.status_code}, '
                          f'{len(r.text):,} bytes, {len(found)} report link(s)')
            if verbose:
                report.append('      ' + ' '.join(r.text.split())[:400])
            if found:
                if verbose:
                    print('\n'.join(report))
                return found
        except requests.RequestException as e:
            report.append(f'  {label}: {type(e).__name__}: {str(e)[:200]}')

    raise DiscoveryError(
        'could not find the monthly traffic listing on the DGCA portal.\n'
        + '\n'.join(report) +
        '\n\nHow to read this. A connection error or timeout on every line means '
        'DGCA is refusing the request rather than that the listing moved — '
        'government sites do block cloud datacentre ranges, and GitHub runners '
        'are US-based. HTTP 200 with plenty of bytes but no links means the '
        'page no longer carries the report paths; check that an href still '
        f'looks like jsp/dgca/.../{PATH_HINT}/<file>.pdf. '
        'Run `python pipeline/dgca_portal.py --diagnose` from an ordinary '
        'connection to see which it is.')
    return out


def head(url: str, session: requests.Session | None = None) -> dict:
    """Last-Modified and size, so an unchanged file costs one cheap request."""
    s = session or _session()
    r = s.head(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return {'last_modified': r.headers.get('Last-Modified'),
            'length': int(r.headers.get('Content-Length', 0))}


if __name__ == '__main__':
    v = '--diagnose' in sys.argv
    try:
        reps = list_reports(verbose=v)
    except DiscoveryError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1) from None
    for p in sorted(reps)[-6:]:
        print(f'{p}  {urllib.parse.unquote(reps[p].rsplit("/", 1)[-1])}')
    print(f'\n{len(reps)} monthly reports listed, latest {max(reps)}', file=sys.stderr)
