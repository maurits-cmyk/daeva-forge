"""Build the hosted site (Cloudflare Workers static assets) and its price files.

  python hosting.py build    # assemble dist/: the two pages, data.json, icons, sale speeds, robots.txt, sitemap
  python hosting.py prices   # current asks for the servers in site/servers.txt -> dist/prices/ (hourly; or give ids)
  python hosting.py speeds   # sale speeds for today's seventh of the servers -> site/speeds/ (daily; committed)
  python hosting.py due      # exit 0 if the live prices predate this hour's capture (the fallback run is needed)

GitHub Actions runs `build` + `prices` and deploys dist/ every hour, started at :15 by the Worker's cron trigger
(Aion2Market captures at about :07-:11), with GitHub's own late schedule as a fallback; `speeds` runs once a day, so every server's sale speeds refresh weekly. Recipes, success
tables and supply requests change rarely: rebuild app/data.json locally with build_data.py and commit it.

Aion2Market hasn't answered our request (2026-10-20), so we keep our load on it low and identifiable: one
request per server per hour, spaced out, and a User-Agent saying who we are and how to reach us.
"""
import html, json, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
APP, SITE, DIST = ROOT / 'app', ROOT / 'site', ROOT / 'dist'
API = 'https://aion2.exchange/api'
SITE_URL = 'https://daevaforge.com'
UA = {'User-Agent': 'DaevaForge/0.2 (+https://daevaforge.com; mawreez@daevaforge.com) hourly price snapshot'}
GAP = 4.0          # seconds between servers in the hourly run (about 12 minutes for 106 servers)
BUDGET = 20 * 60   # stop fetching after this; the rest keep their last published prices, so a slow hour still deploys
SPEED_GAP = 0.5    # seconds between item requests in the daily sale-speed run

# Two pages, one app: the address picks the mode (app/index.html reads location.pathname)
PAGES = {
    'single': {'file': 'index.html', 'path': '/', 'tagline': 'AION 2 crafting calculator',
               'title': 'AION 2 Crafting Calculator with Market Prices – Daeva Forge (unofficial)',
               'description': "Free AION 2 crafting calculator: what any item really costs in Kina at your server's market prices, "
                              "with NC's success chances, Combo upgrades and the materials you already own."},
    'profit': {'file': 'profit.html', 'path': '/profit', 'tagline': 'AION 2 crafting for profit',
               'title': 'AION 2 Crafting for Profit: Best Recipes per Server – Daeva Forge (unofficial)',
               'description': "Find the most profitable AION 2 crafts on your server: expected profit per attempt from hourly "
                              "market prices, NC's success chances, sale speeds and bad-luck risk. Free."},
}


def get(url, tries=5, timeout=60):
    import urllib.error, urllib.request
    for n in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())
        except urllib.error.HTTPError as e:  # Aion2Market answers 503 now and then; back off and retry
            if e.code < 500 or n == tries - 1:
                raise
            time.sleep(5 * (n + 1))


def wrap_page(body, head=''):
    """app/index.html is written as a page body (as the artifact publisher expects); give it a document."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            + head + '<style>body{margin:0}[hidden]{display:none!important}</style></head><body>' + body + '</body></html>')


def page(mode):
    """One hosted page: its own title, description, canonical address, link-preview card and structured data."""
    p, e = PAGES[mode], lambda s: html.escape(s, quote=True)
    body = (APP / 'index.html').read_text(encoding='utf8')
    # the body starts with the artifact's <title> and icon links; the hosted page puts its own in <head>
    start = body.index('<link rel="apple-touch-icon"'); start = body.index('>', start) + 1
    body = body[start:].replace('<small id="tagline">AION 2 crafting calculator</small>', f'<small id="tagline">{e(p["tagline"])}</small>')
    url = SITE_URL + p['path']
    ld = [{'@context': 'https://schema.org', '@type': 'WebApplication', 'name': 'Daeva Forge', 'url': url,
           'applicationCategory': 'GameApplication', 'operatingSystem': 'Any', 'description': p['description'],
           'inLanguage': 'en', 'isAccessibleForFree': True, 'about': {'@type': 'VideoGame', 'name': 'AION 2'},
           'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'}}]
    if p['path'] == '/':  # the site's name in Google results
        ld.append({'@context': 'https://schema.org', '@type': 'WebSite', 'name': 'Daeva Forge', 'url': SITE_URL + '/'})
    head = (f'<title>{e(p["title"])}</title><meta name="description" content="{e(p["description"])}">'
            f'<link rel="canonical" href="{url}">'
            '<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#08090c">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Daeva Forge">'
            f'<meta property="og:title" content="{e(p["title"])}"><meta property="og:description" content="{e(p["description"])}">'
            f'<meta property="og:url" content="{url}"><meta property="og:image" content="{SITE_URL}/og.png">'
            '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            '<meta property="og:image:alt" content="Daeva Forge, an AION 2 crafting calculator"><meta property="og:locale" content="en_US">'
            '<meta name="twitter:card" content="summary_large_image">'
            f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    return wrap_page(body, head)


def servers():
    """Server ids from site/servers.txt; the word 'all' means every server in app/data.json."""
    lines = [line.split('#')[0].strip() for line in (SITE / 'servers.txt').read_text().splitlines()]
    if 'all' in lines:
        return [s[0] for s in json.load(open(APP / 'data.json', encoding='utf8'))['servers']]
    return [int(x) for x in lines if x]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def build():
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    for mode, p in PAGES.items():
        (DIST / p['file']).write_text(page(mode), encoding='utf8')
    for f in ('data.json', 'favicon.svg', 'favicon.ico', 'apple-touch-icon.png', 'og.png', 'BingSiteAuth.xml'):  # last: Bing Webmaster Tools verification
        shutil.copy(APP / f, DIST / f)
    if (SITE / 'speeds').exists():
        shutil.copytree(SITE / 'speeds', DIST / 'speeds')
    # /api/feedback is the feedback form's endpoint, not a page (Search Console listed it as a 405)
    (DIST / 'robots.txt').write_text(f'User-agent: *\nDisallow: /api/\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n')
    day = datetime.now(timezone.utc).date().isoformat()
    (DIST / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + ''.join(f'  <url><loc>{SITE_URL}{p["path"]}</loc><lastmod>{day}</lastmod></url>\n' for p in PAGES.values())
                                      + '</urlset>\n')
    print(f'dist/ ready ({sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) // 1024} KB)')


def market(server_id, keys, tries=5):
    items = get(f'{API}/items?server={server_id}&limit=1000', tries=tries, timeout=30)['items']
    return [m for m in items if str(m['item_key']) in keys]


def published(path):
    """The copy of a file currently live on the site (to keep a server's prices when this hour's fetch fails)."""
    import urllib.request
    return urllib.request.urlopen(urllib.request.Request(f'{SITE_URL}/{path}', headers=UA), timeout=30).read()


def prices():
    keys = set(json.load(open(APP / 'data.json', encoding='utf8'))['items'])
    out = DIST / 'prices'
    out.mkdir(parents=True, exist_ok=True)
    done, kept, start = [], [], time.time()
    for n, sid in enumerate([int(x) for x in sys.argv[2:]] or servers()):   # server ids on the command line: just those
        if n: time.sleep(GAP)
        try:
            if time.time() - start > BUDGET:
                raise TimeoutError('out of time this hour')
            items = market(sid, keys, tries=3)   # Aion2Market answers 503 when busy: give up quickly, keep the last copy
        except Exception as e:  # keep the last published copy so the server doesn't vanish for an hour
            print(f'{sid}: {e}')
            try:
                (out / f'{sid}.json').write_bytes(published(f'prices/{sid}.json')); done.append(sid); kept.append(sid)
            except Exception:
                pass
            continue
        captured = max((m['captured_at'] for m in items if m.get('captured_at')), default=None)
        data = {'server': sid, 'fetched': now(), 'captured': captured,
                'prices': {str(m['item_key']): [m['price'], m['listings'], m['last_price'], m['last_seen_at']] for m in items}}
        (out / f'{sid}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf8')
        done.append(sid)
    have_speeds = sorted(int(f.stem) for f in (DIST / 'speeds').glob('*.json'))
    (out / 'index.json').write_text(json.dumps({'servers': done, 'speeds': have_speeds, 'fetched': now()}), encoding='utf8')
    print(f'{len(done)} servers ({len(kept)} kept from the last run)')
    if not done:
        sys.exit('no prices fetched')


def due():
    """The fallback run is needed only when the live prices were fetched before Aion2Market's latest capture
    (about :07-:11 each hour), i.e. the timed run didn't happen this hour."""
    from datetime import timedelta
    try:
        fetched = datetime.fromisoformat(json.loads(published('prices/index.json'))['fetched'])
    except Exception:
        return
    capture = (datetime.now(timezone.utc) - timedelta(minutes=12)).replace(minute=12, second=0, microsecond=0)
    if fetched >= capture:
        sys.exit(f'live prices fetched {fetched:%H:%M}, after the {capture:%H:%M} capture: not needed')


def speeds():
    """Listings that disappeared per day over the last week (sales plus cancellations), crafted products only.
    Each day covers a seventh of the servers, so every server refreshes weekly; pass server ids to run those instead."""
    data = json.load(open(APP / 'data.json', encoding='utf8'))
    products = {str(r['p']) for r in data['recipes']} | {str(r['combo']['p']) for r in data['recipes'] if r['combo']}
    (SITE / 'speeds').mkdir(parents=True, exist_ok=True)
    todo = [int(x) for x in sys.argv[2:]] or [s for n, s in enumerate(servers()) if n % 7 == datetime.now(timezone.utc).toordinal() % 7]
    for sid in todo:
        listed = {str(m['item_key']) for m in market(sid, products)}
        v = {}
        for k in sorted(listed):
            time.sleep(SPEED_GAP)
            try:
                pts = get(f'{API}/items/{k}/prices?server={sid}')['points']
            except Exception:
                continue
            if len(pts) >= 24:
                drops = sum(max(0, a['listings'] - b['listings']) for a, b in zip(pts, pts[1:]))
                v[k] = round(drops / (len(pts) / 24), 2)
        (SITE / 'speeds' / f'{sid}.json').write_text(json.dumps({'at': now(), 'v': v}, separators=(',', ':'), sort_keys=True), encoding='utf8')
        print(f'{sid}: {len(v)} sale speeds')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    {'build': build, 'prices': prices, 'speeds': speeds, 'due': due}.get(cmd, lambda: sys.exit(__doc__))()
