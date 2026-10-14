// Server-side proxy for the Strategic Bearing Substack feed.
// The browser cannot fetch substack.com directly (no CORS headers), so this
// runs on Netlify, fetches the RSS, and hands back clean JSON.

const FEED = 'https://strategicbearing.substack.com/feed';
const MAX_ITEMS = 6;

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
      headers: { 'user-agent': 'strategicbearing.in feed reader' },
    });
    if (!res.ok) return reply({ items: [], error: `upstream ${res.status}` });

    const xml = await res.text();
    const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)]
      .slice(0, MAX_ITEMS)
      .map(([, block]) => {
        const categories = [...block.matchAll(/<category(?:\s[^>]*)?>([\s\S]*?)<\/category>/g)]
          .map((c) => strip(c[1]))
          .filter(Boolean);
        let blurb = tag(block, 'description');
        if (blurb.length > 180) blurb = blurb.slice(0, 177).trimEnd() + '…';
        return {
          title: tag(block, 'title'),
          link: tag(block, 'link'),
          date: tag(block, 'pubDate'),
          blurb,
          categories,
        };
      })
      .filter((i) => i.title && i.link);

    return reply({ items });
  } catch (err) {
    return reply({ items: [], error: String(err) });
  }
};
