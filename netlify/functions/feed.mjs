// Server-side proxy for the Strategic Bearing Substack feed.
// The browser cannot fetch substack.com directly (no CORS headers), so this
// runs on Netlify, fetches the RSS, and hands back clean JSON.
//
// 30 Oct 2026: the function was returning {"items":[]} while the same feed in a
// browser carried the post. The fetch succeeded, so this was not a network or
// status problem — Substack was answering the old 'strategicbearing.in feed
// reader' agent with something that held no <item> elements. It now sends a
// normal browser user-agent and an Accept header asking for RSS, and when it
// parses zero items it reports what it actually received instead of failing
// silently, so the next failure is diagnosable from the endpoint itself.

const FEED = 'https://strategicbearing.substack.com/feed';
const MAX_ITEMS = 6;
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const strip = (s) =>
  s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
   .replace(/<[^>]+>/g, ' ')
   .replace(/&nbsp;/g, ' ')
   .replace(/&amp;/g, '&')
   .replace(/&lt;/g, '<')
   .replace(/&gt;/g, '>')
   .replace(/&quot;/g, '"')
   .replace(/&#39;/g, "'")
   .replace(/\s+/g, ' ')
   .trim();

const tag = (block, name) => {
  const m = block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)</${name}>`));
  return m ? strip(m[1]) : '';
};

// trim on a word boundary rather than mid-word
const clamp = (s, n) => {
  if (s.length <= n) return s;
  const cut = s.slice(0, n);
  const sp = cut.lastIndexOf(' ');
  return (sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:.–-]+$/, '') + '…';
};

const reply = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      // 10 min at the edge, serve stale for an hour if Substack is slow
      'cache-control': 'public, max-age=300',
      'netlify-cdn-cache-control':
        'public, max-age=600, stale-while-revalidate=3600',
    },
  });

export default async () => {
  try {
    const res = await fetch(FEED, {
      headers: {
        'user-agent': UA,
        accept: 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5',
        'accept-language': 'en-GB,en;q=0.9',
      },
      redirect: 'follow',
    });
    if (!res.ok) return reply({ items: [], error: `upstream ${res.status}` });

    const xml = await res.text();
    const blocks = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)];

    if (!blocks.length) {
      // Say what came back. Lengths and content type only, never the body.
      return reply({
        items: [],
        error: 'no items parsed',
        upstream: {
          status: res.status,
          type: res.headers.get('content-type') || '',
          bytes: xml.length,
          looksLikeRss: /<rss[\s>]|<feed[\s>]/i.test(xml),
          finalUrl: res.url || FEED,
        },
      });
    }

    const items = blocks
      .slice(0, MAX_ITEMS)
      .map(([, block]) => {
        const categories = [...block.matchAll(/<category(?:\s[^>]*)?>([\s\S]*?)<\/category>/g)]
          .map((c) => strip(c[1]))
          .filter(Boolean);
        return {
          title: tag(block, 'title'),
          link: tag(block, 'link'),
          date: tag(block, 'pubDate'),
          blurb: clamp(tag(block, 'description'), 180),
          categories,
        };
      })
      .filter((i) => i.title && i.link);

    return reply({ items });
  } catch (err) {
    return reply({ items: [], error: String(err) });
  }
};
