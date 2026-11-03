# AdSense: what is in place, and the two steps left

Current state: **the hooks are installed and inert.** Every page carries a
commented-out AdSense block, `ads.txt` is a placeholder, and nothing
third-party is requested. Verified across all 104 pages: zero requests to
`googlesyndication`, `googleads` or `doubleclick`.

Two things must happen together, in one deploy, or ads silently never appear.

## Step 1 — arm the publisher ID

Get the ID from AdSense (Account → Settings → Account information; it is
`pub-` followed by 16 digits), then:

```
python3 build/adsense.py --publisher pub-1234567890123456
```

That fills the ID on every page, uncomments the `<meta>` and the
`adsbygoogle.js` loader, and writes the live `ads.txt` line. It is safe to run
twice. Running `build/adsense.py` with no argument puts it back to inert.

Auto ads are placed from the AdSense dashboard — no per-page ad slots are
needed in the markup, which is why there are none.

## Step 2 — widen the Content-Security-Policy

**This is the step that gets forgotten.** The site currently sends:

```
script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'
```

with no `frame-src`. That blocks `adsbygoogle.js`, the ad iframes, the ad
images and Google's consent message. The ads do not error — they just never
render, which looks like a rejected application.

In `netlify.toml`, replace the `Content-Security-Policy` value with:

```
default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; style-src 'self' 'unsafe-inline' https:; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https:; frame-src https:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests
```

Keep exactly one CSP header. A browser enforces every policy it receives, so a
second, stricter one still blocks the ads.

`frame-ancestors 'none'`, `X-Frame-Options: DENY`, HSTS, `nosniff`,
`Referrer-Policy` and `Permissions-Policy` all stay as they are.

### Why this is left undone for now

It is a real loosening: `script-src … https:` lets any HTTPS origin run
JavaScript on the site, where today none can. That is the price of AdSense and
Google publishes no fixed allowlist to narrow it to. Making the change before
the ads exist buys nothing and gives up the protection in the meantime, so it
waits for the same deploy as step 1.

The documented alternative is a nonce-based strict CSP
(`script-src 'nonce-{RANDOM}' 'strict-dynamic' https:`), which needs a fresh
nonce per response — a Netlify Edge Function — and a `nonce` attribute on
every inline `<script>`. The two calculators carry their application code in
inline blocks, so that is a real piece of work, not a config change.

## What was already done

| | |
|---|---|
| `/privacy/` | Discloses ad cookies, the EEA/UK/Swiss consent message, hosting, Google Fonts, and that the site runs no analytics |
| `/about/` | Plus the disclosure: personal capacity, not the employer's views, sources public, not advice |
| `/contact/` | Email, LinkedIn, newsletter, corrections |
| Footer | About · Contact · Privacy on all 104 pages |
| `ads.txt` | Placeholder, armed by step 1 |
| `sitemap.xml` | 105 URLs including the three new pages |
| `robots.txt` | Already correct — `Allow: /` plus the sitemap line |

## Not done, deliberately

The review package also proposed deleting 6 posts, rewriting 42 headlines,
9 factual edits, 77 content edits and 185 alt texts. None of that is applied.
It is a content decision, not an AdSense one, and it overlaps the review
clusters still open.
