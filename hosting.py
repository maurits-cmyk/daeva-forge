"""Build the hosted site (Cloudflare Workers static assets) and its price files.

  python hosting.py build    # assemble dist/: the page, data.json, icons and sale speeds
  python hosting.py prices   # current asks for the servers in site/servers.txt -> dist/prices/ (hourly)
  python hosting.py speeds   # sale speeds for those servers -> site/speeds/ (daily; committed to the repo)

GitHub Actions runs `build` + `prices` and deploys dist/ every hour, about 10 minutes after Aion2Market
captures its prices; `speeds` runs once a day. Recipes, success tables and supply requests change rarely:
rebuild app/data.json locally with build_data.py and commit it.
"""
import json, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
APP, SITE, DIST = ROOT / 'app', ROOT / 'site', ROOT / 'dist'
API = 'https://aion2.exchange/api'
UA = {'User-Agent': 'DaevaForge/0.1 (unofficial AION 2 crafting calculator; hourly price snapshot)'}


def get(url, tries=5):
    import urllib.error, urllib.request
    for n in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        except urllib.error.HTTPError as e:  # Aion2Market answers 503 now and then; back off and retry
            if e.code < 500 or n == tries - 1:
                raise
            time.sleep(5 * (n + 1))


def wrap_page(body):
    """app/index.html is written as a page body (as the artifact publisher expects); give it a document."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>body{margin:0}[hidden]{display:none!important}</style></head><body>' + body + '</body></html>')


def servers():
    return [int(line.split('#')[0]) for line in (SITE / 'servers.txt').read_text().splitlines() if line.split('#')[0].strip()]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def build():
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    (DIST / 'index.html').write_text(wrap_page((APP / 'index.html').read_text(encoding='utf8')), encoding='utf8')
    for f in ('data.json', 'favicon.svg', 'favicon.ico', 'apple-touch-icon.png'):
        shutil.copy(APP / f, DIST / f)
    if (SITE / 'speeds').exists():
        shutil.copytree(SITE / 'speeds', DIST / 'speeds')
    print(f'dist/ ready ({sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) // 1024} KB)')


def market(server_id, keys):
    items = get(f'{API}/items?server={server_id}&limit=1000')['items']
    return [m for m in items if str(m['item_key']) in keys]


def prices():
    keys = set(json.load(open(APP / 'data.json', encoding='utf8'))['items'])
    out = DIST / 'prices'
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for sid in servers():
        try:
            items = market(sid, keys)
        except Exception as e:  # leave this server out of this hour's index; the page keeps its last copy
            print(f'{sid}: {e}')
            continue
        captured = max((m['captured_at'] for m in items if m.get('captured_at')), default=None)
        data = {'server': sid, 'fetched': now(), 'captured': captured,
                'prices': {str(m['item_key']): [m['price'], m['listings'], m['last_price'], m['last_seen_at']] for m in items}}
        (out / f'{sid}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf8')
        done.append(sid)
        print(f'{sid}: {len(items)} items, captured {captured}')
    have_speeds = sorted(int(f.stem) for f in (DIST / 'speeds').glob('*.json'))
    (out / 'index.json').write_text(json.dumps({'servers': done, 'speeds': have_speeds, 'fetched': now()}), encoding='utf8')
    if not done:
        sys.exit('no prices fetched')


def speeds():
    """Listings that disappeared per day over the last week (sales plus cancellations), crafted products only."""
    data = json.load(open(APP / 'data.json', encoding='utf8'))
    products = {str(r['p']) for r in data['recipes']} | {str(r['combo']['p']) for r in data['recipes'] if r['combo']}
    (SITE / 'speeds').mkdir(parents=True, exist_ok=True)
    for sid in servers():
        listed = {str(m['item_key']) for m in market(sid, products)}
        v = {}
        for k in sorted(listed):
            try:
                pts = get(f'{API}/items/{k}/prices?server={sid}')['points']
            except Exception:
                continue
            if len(pts) >= 24:
                drops = sum(max(0, a['listings'] - b['listings']) for a, b in zip(pts, pts[1:]))
                v[k] = round(drops / (len(pts) / 24), 2)
            time.sleep(0.25)
        (SITE / 'speeds' / f'{sid}.json').write_text(json.dumps({'at': now(), 'v': v}, separators=(',', ':'), sort_keys=True), encoding='utf8')
        print(f'{sid}: {len(v)} sale speeds')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    {'build': build, 'prices': prices, 'speeds': speeds}.get(cmd, lambda: sys.exit(__doc__))()
