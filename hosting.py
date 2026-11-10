"""Build the hosted site (Cloudflare Workers static assets) and its price files.

  python hosting.py build    # assemble dist/: the two pages, a page per item, data.json, icons, sale speeds, robots.txt, sitemap
  python hosting.py prices   # current asks for the servers in site/servers.txt -> dist/prices/ (hourly; or give ids)
  python hosting.py speeds   # sale speeds for today's seventh of the servers -> site/speeds/ (daily; committed)
  python hosting.py due      # exit 0 if the live prices predate this hour's capture (the fallback run is needed)
  python hosting.py changed  # before deploying: list the pages that differ from the live site -> changed.txt
  python hosting.py indexnow # after deploying: tell Bing, Yandex and the other IndexNow engines about changed.txt

GitHub Actions runs `build` + `prices` and deploys dist/ every hour, started at :15 by the Worker's cron trigger
(Aion2Market captures at about :07-:11), with GitHub's own late schedule as a fallback; `speeds` runs once a day, so every server's sale speeds refresh weekly. Recipes, success
tables and supply requests change rarely: rebuild app/data.json locally with build_data.py and commit it.

Aion2Market hasn't answered our request (2026-10-20), so we keep our load on it low and identifiable: one
request per server per hour, spaced out, and a User-Agent saying who we are and how to reach us.
"""
import html, json, re, shutil, sys, time
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
INDEXNOW_KEY = 'b34f89a544390568f2f0177559c9fc92'  # not a secret: the engines check it against /<key>.txt on the site
SANE_SHARE = 0.5  # a server answering with fewer than half the prices of its last run keeps the last run's

# Two pages, one app: the address picks the mode (app/index.html reads location.pathname)
PAGES = {
    'single': {'file': 'index.html', 'path': '/', 'tagline': 'AION 2 crafting calculator',
               'title': 'AION 2 Crafting Calculator with Market Prices – Daeva Forge (unofficial)',
               'description': "Free AION 2 crafting calculator: what any item really costs in Kina at your server's market prices, "
                              "with NC's success chances, Combo upgrades and the materials you already own."},
    'profit': {'file': 'profit.html', 'path': '/profit', 'tagline': 'AION 2 crafting for profit',
               'title': 'AION 2 Crafting for Profit: Best Recipes per Server – Daeva Forge (unofficial)',
               'description': "Find the most profitable AION 2 crafts on your server: expected profit per attempt from current "
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


def page(p, card=''):
    """One hosted page: its own title, description, canonical address, link-preview card and structured data.
    An item page (card given) has the item card above the calculator, and the item's name as its h1."""
    e = lambda s: html.escape(s, quote=True)
    body = (APP / 'index.html').read_text(encoding='utf8')
    # the body starts with the artifact's <title> and icon links; the hosted page puts its own in <head>
    start = body.index('<link rel="apple-touch-icon"'); start = body.index('>', start) + 1
    body = body[start:].replace('<small id="tagline">AION 2 crafting calculator</small>', f'<small id="tagline">{e(p["tagline"])}</small>')
    if card:
        h = body.index('<h1>'); body = body[:h] + '<p class="h1">' + body[h + 4:].replace('</h1>', '</p>', 1)
        anchor = '<section class="settings foldcard" aria-label="General settings">'
        assert anchor in body
        body = body.replace(anchor, card + '\n\n  ' + anchor, 1)
    url = SITE_URL + p['path']
    ld = [{'@context': 'https://schema.org', '@type': 'WebApplication', 'name': 'Daeva Forge', 'url': url,
           'applicationCategory': 'GameApplication', 'operatingSystem': 'Any', 'description': p['description'],
           'inLanguage': 'en', 'isAccessibleForFree': True, 'about': {'@type': 'VideoGame', 'name': 'AION 2'},
           'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'}}]
    if card:
        ld = [{'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Daeva Forge', 'item': SITE_URL + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': p['name'], 'item': url}]}]
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


# Item pages: /item/<name> for every item the calculator opens in "specific items" mode (app/index.html's slugOf
# and indexRecipes filter must match). Static facts only (recipes, what uses it); the calculator below adds prices.
QUEST_TOOL = re.compile(r'^(Novice|Professional) .+ \(Bound\)$')   # as in app/index.html
PROF_LABEL = {'Tailoring': 'Armorsmithing', 'Jewelcrafting': 'Handicrafting'}
FACTION = {'Light': 'Elyos', 'Dark': 'Asmodian'}
MAX_USES = 24


def slug_of(name):
    return re.sub(r'[^a-z0-9]+', '-', re.sub(r"['’]", '', name.lower())).strip('-')


def item_pages(data):
    """{slug: page fields, with the card's html} for every craftable item."""
    e = lambda s: html.escape(s, quote=True)
    name = lambda k: data['items'].get(str(k), [str(k)])[0]
    recs = [r for r in data['recipes'] if (r['ml'] > 0 or r.get('tr') or r.get('g')) and not QUEST_TOOL.match(name(r['p']))]
    by = {}
    for r in recs:
        by.setdefault(slug_of(name(r['p'])), []).append(r)
    link = lambda k: f'<a href="/item/{slug_of(name(k))}">{e(name(k))}</a>' if slug_of(name(k)) in by else e(name(k))
    uses, combos = {}, {}   # material -> products made from it; Combo product -> what Combos into it
    for r in recs:
        if r.get('g'):
            continue
        for k, _ in r['c']:
            uses.setdefault(slug_of(name(k)), set()).add(r['p'])
        if r['combo']:
            if r['combo']['p'] != r['p']:   # some Combos just make extra of the same item
                combos.setdefault(slug_of(name(r['combo']['p'])), set()).add(r['p'])
    out = {}
    for slug, rs in sorted(by.items()):
        first = min(rs, key=lambda r: (bool(r.get('g')), r['ml']))
        nm, grade = name(first['p']), data['items'].get(str(first['p']), ['', ''])[1] or 'Common'
        races = {r['race'] for r in rs}
        # one line per distinct recipe: the two factions' versions usually match and share a line
        lines = {}
        for r in sorted((r for r in rs if not r.get('g')), key=lambda r: (r['ml'], r['prof'], r['race'])):
            key = (r['prof'], r['ml'], r.get('tr'), r['y'], tuple(sorted((name(k), q) for k, q in r['c'])),
                   (name(r['combo']['p']), r['combo']['pct']) if r['combo'] else None)
            lines.setdefault(key, [r, set()])[1].add(r['race'])
        items = []
        for (prof, ml, tr, y, _, _), (r, rr) in lines.items():
            head = f'{PROF_LABEL.get(prof, prof)} {"transfer crafting" if tr else "Lv " + str(ml)}'
            who = f' ({FACTION[next(iter(rr))]})' if len(rr) < len(races) else ''
            mats = ', '.join(f'{q} × {link(k)}' for k, q in r['c'])
            extra = (f'; makes {y}' if y > 1 else '') + ('; always succeeds' if tr else
                     f'; Combo {r["combo"]["pct"]}%: {link(r["combo"]["p"])}' if r['combo'] else '')
            items.append(f'<li><b>{e(head)}</b>{who}: {mats}{extra}</li>')
        notes = []
        if any(r.get('g') for r in rs):
            notes.append(f'Since the Nov 4 patch it also has a <a href="/item/{slug}?guaranteed=1">guaranteed recipe</a>: '
                         'same materials, always succeeds, never Combos, makes Bound gear.')
        if slug in combos:
            notes.append('Also comes from a Combo when crafting ' + ', '.join(link(k) for k in sorted(combos[slug], key=name)) + '.')
        used = sorted({slug_of(name(k)): k for k in uses.get(slug, ())}.values(), key=name)
        if used:
            more = f' and {len(used) - MAX_USES} more' if len(used) > MAX_USES else ''
            notes.append('<b>Used to make</b>: ' + ', '.join(link(k) for k in used[:MAX_USES]) + more + '.')
        only = f' {FACTION[next(iter(races))]} only.' if len(races) == 1 else ''
        card = (f'<section class="settings itempage" id="itemCard" aria-label="{e(nm)}">\n'
                f'    <h1 class="card-title"><span><span class="g-{e(grade)}">{e(nm)}</span>: crafting cost</span></h1>\n'
                f'    <p>What one {e(nm)} costs to craft in AION 2 on your server, failed attempts included.{only} '
                'The calculator below opens it with current market prices: set your server and mastery levels.</p>\n'
                '    <p class="itemcost" id="itemCost" hidden></p>\n'
                f'    <p><b>Recipe{"s" if len(items) > 1 else ""}</b> (materials per attempt):</p>\n'
                f'    <ul>{"".join(items)}</ul>\n'
                + ''.join(f'    <p>{n}</p>\n' for n in notes)
                + '  </section>')
        prof = PROF_LABEL.get(first['prof'], first['prof'])
        level = 'transfer crafting' if first.get('tr') else f'Lv {first["ml"]}'
        out[slug] = {'file': f'item/{slug}.html', 'path': f'/item/{slug}', 'name': nm, 'tagline': 'AION 2 crafting calculator',
                     'title': f'{nm}: AION 2 Crafting Cost and Materials – Daeva Forge',
                     'description': f"What {'an' if nm[0] in 'AEIOU' else 'a'} {nm} costs to craft in AION 2 at your server's market prices: {prof} {level}, "
                                    'its materials, success chance and Combo, failed attempts included. Free calculator.',
                     'card': card, 'grade': grade, 'races': races,
                     # for the all-items page: each profession that makes it, at its lowest level (transfer steps last)
                     'profs': {PROF_LABEL.get(r['prof'], r['prof']): ('transfer', 1000 + r['tr']) if r.get('tr') else (f'Lv {r["ml"]}', r['ml'])
                               for r in sorted(rs, key=lambda r: -r['ml']) if not r.get('g')}}
    return out


def items_page(items):
    """/items: every item page, by profession, so people and crawlers can find them from the home page."""
    e = lambda s: html.escape(s, quote=True)
    app = (APP / 'index.html').read_text(encoding='utf8')
    style = app[app.index('<link rel="preconnect"'):app.index('</style>') + 8]   # the fonts and the stylesheet
    header = app[app.index('<header>'):app.index('</header>') + 9]
    header = re.sub(r'<div class="status".*?</div>', '', header).replace('<h1>', '<a class="h1 home" href="/">').replace('</h1>', '</a>')
    footer = app[app.index('<footer>'):app.index('</footer>') + 9].replace('<p id="dataInfo"></p>', '')
    sections = []
    for prof in ('Blacksmithing', 'Armorsmithing', 'Handicrafting', 'Alchemy', 'Cooking'):
        rows = sorted(((p['profs'][prof], slug, p) for slug, p in items.items() if prof in p['profs']), key=lambda x: (-x[0][1], x[2]['name']))
        lis = ''.join((f'<li data-f="{FACTION[next(iter(p["races"]))]}">' if len(p['races']) == 1 else '<li>')
                      + f'<a class="g-{e(p["grade"])}" href="{p["path"]}">{e(p["name"])}</a><span class="lv">{lv}'
                      + (f' · {FACTION[next(iter(p["races"]))]}' if len(p['races']) == 1 else '') + '</span></li>'
                      for (lv, _), slug, p in rows)
        sections.append(f'<section class="settings allitems" aria-label="{prof}"><h2 class="card-title">{prof} <span class="n">{len(rows)}</span></h2>'
                        f'<ul>{lis}</ul></section>')
    css = ('<style>.home{color:inherit;text-decoration:none}.allitems{display:block}.allitems ul{columns:3 240px;column-gap:28px;margin:12px 0;padding:0;list-style:none}'
           '.allitems li{break-inside:avoid;padding:3px 0;font-size:14px}.allitems a{text-decoration:none}.allitems a:hover{text-decoration:underline}'
           '.allitems .lv{display:block;font-size:11.5px;color:var(--muted)}'
           '[data-show=Elyos] li[data-f=Asmodian],[data-show=Asmodian] li[data-f=Elyos]{display:none}.intro .seg{margin:4px 0 12px}.card-title .n{margin-left:auto;color:var(--muted);font-weight:500}'
           '.intro p{margin:10px 0;max-width:80ch;line-height:1.5}.intro a{color:var(--accent)}</style>')
    body = (f'{style}{css}<div class="wrap">{header}'
            '<section class="settings intro allitems"><h1 class="card-title">All craftable items</h1>'
            f'<p>Every item Daeva Forge can price, {len(items)} in all, by profession, highest level first. Each page shows the recipe '
            'and what one costs to craft on your server. Or go back to the <a href="/">calculator</a>.</p>'
            '<div class="seg" role="group" aria-label="Faction"><button type="button" data-v="Elyos">Elyos</button>'
            '<button type="button" data-v="Asmodian">Asmodian</button><button type="button" data-v="">Both</button></div></section>'
            + ''.join(sections) + f'{footer}</div>'
            # the faction switch starts on your server's (the calculator's saved server: 11xxx Elyos, 12xxx Asmodian)
            '<script>(()=>{const get=k=>{try{return JSON.parse(localStorage.getItem("forge:"+k))}catch(e){return null}},'
            'set=v=>{try{localStorage.setItem("forge:itemsFaction",JSON.stringify(v))}catch(e){}},sv=get("server"),'
            'show=v=>{document.body.dataset.show=v;document.querySelectorAll(".seg button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.v===v))};'
            'let v=get("itemsFaction");if(v==null)v=sv?(String(sv)[1]==="1"?"Elyos":"Asmodian"):"";show(v);'
            'document.querySelectorAll(".seg button").forEach(b=>b.addEventListener("click",()=>{show(b.dataset.v);set(b.dataset.v)}))})()</script>')
    p = {'path': '/items', 'title': 'All AION 2 Craftable Items: Recipes and Crafting Costs – Daeva Forge',
         'description': f'Every craftable item in AION 2, {len(items)} in all, by profession: recipes, materials and what each costs to craft on your server.'}
    t = e(p['title']); d = e(p['description'])
    head = (f'<title>{t}</title><meta name="description" content="{d}"><link rel="canonical" href="{SITE_URL}/items">'
            '<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#08090c">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Daeva Forge"><meta property="og:title" content="{t}">'
            f'<meta property="og:description" content="{d}"><meta property="og:url" content="{SITE_URL}/items"><meta property="og:image" content="{SITE_URL}/og.png">'
            '<meta name="twitter:card" content="summary_large_image">')
    return p, wrap_page(body, head)


def servers():
    """Server ids from site/servers.txt; the word 'all' means every server in app/data.json."""
    lines = [line.split('#')[0].strip() for line in (SITE / 'servers.txt').read_text().splitlines()]
    if 'all' in lines:
        return [s[0] for s in json.load(open(APP / 'data.json', encoding='utf8'))['servers']]
    return [int(x) for x in lines if x]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def headers():
    """dist/_headers: security headers for every page (Cloudflare applies them to the static files). The policy
    allows only our own inline scripts (by hash, so a change to one updates the policy on the next build), Google
    Fonts and Cloudflare's Web Analytics beacon."""
    import base64, hashlib
    scripts = {m.group(1) for f in DIST.rglob('*.html') for m in re.finditer(r'<script>(.*?)</script>', f.read_text(encoding='utf8'), re.S)}
    hashes = ' '.join(sorted("'sha256-" + base64.b64encode(hashlib.sha256(s.encode('utf8')).digest()).decode() + "'" for s in scripts))
    csp = '; '.join([
        "default-src 'self'", f"script-src 'self' {hashes} https://static.cloudflareinsights.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", "font-src https://fonts.gstatic.com",
        "img-src 'self' data:", "connect-src 'self' https://cloudflareinsights.com", "frame-ancestors 'none'",
        "base-uri 'none'", "form-action 'self'", "object-src 'none'"])
    return ('/*\n'
            f'  Content-Security-Policy: {csp}\n'
            '  Strict-Transport-Security: max-age=31536000; includeSubDomains\n'
            '  X-Content-Type-Options: nosniff\n'
            '  X-Frame-Options: DENY\n'
            '  Referrer-Policy: strict-origin-when-cross-origin\n'
            '  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()\n')


def build():
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    for p in PAGES.values():
        (DIST / p['file']).write_text(page(p), encoding='utf8')
    items = item_pages(json.load(open(APP / 'data.json', encoding='utf8')))
    (DIST / 'item').mkdir()
    for p in items.values():
        (DIST / p['file']).write_text(page(p, p['card']), encoding='utf8')
    index, doc = items_page(items)
    (DIST / 'items.html').write_text(doc, encoding='utf8')
    for f in ('data.json', 'favicon.svg', 'favicon.ico', 'apple-touch-icon.png', 'og.png', 'BingSiteAuth.xml'):  # last: Bing Webmaster Tools verification
        shutil.copy(APP / f, DIST / f)
    if (SITE / 'speeds').exists():
        shutil.copytree(SITE / 'speeds', DIST / 'speeds')
    # /api/feedback is the feedback form's endpoint, not a page (Search Console listed it as a 405)
    (DIST / 'robots.txt').write_text(f'User-agent: *\nDisallow: /api/\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n')
    day = datetime.now(timezone.utc).date().isoformat()
    (DIST / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + ''.join(f'  <url><loc>{SITE_URL}{p["path"]}</loc><lastmod>{day}</lastmod></url>\n' for p in [*PAGES.values(), index])
                                      + ''.join(f'  <url><loc>{SITE_URL}{p["path"]}</loc></url>\n' for p in items.values())
                                      + '</urlset>\n')
    (DIST / '_headers').write_text(headers(), encoding='utf8')
    # IndexNow: the key file, and a fingerprint of every page so the next deploy can tell which ones changed
    (DIST / f'{INDEXNOW_KEY}.txt').write_text(INDEXNOW_KEY)
    import hashlib
    pages = [*PAGES.values(), index, *items.values()]
    (DIST / 'pages.json').write_text(json.dumps({p['path']: hashlib.sha1((DIST / (p.get('file') or 'items.html')).read_bytes()).hexdigest()[:16]
                                                 for p in pages}, separators=(',', ':')), encoding='utf8')
    print(f'{len(items)} item pages; dist/ ready ({sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) // 1024} KB)')


def changed():
    """Pages whose content differs from the live site (all of them if it has no fingerprints yet) -> changed.txt"""
    new = json.loads((DIST / 'pages.json').read_text(encoding='utf8'))
    try:
        old = json.loads(published('pages.json'))
    except Exception:
        old = {}
    urls = [SITE_URL + path for path, h in new.items() if old.get(path) != h]
    (ROOT / 'changed.txt').write_text('\n'.join(urls))
    print(f'{len(urls)} of {len(new)} pages changed')


def indexnow():
    """Submit changed.txt to IndexNow (api.indexnow.org passes it on to Bing, Yandex, Seznam, Naver...)."""
    import urllib.request
    f = ROOT / 'changed.txt'
    urls = f.read_text().split() if f.exists() else []
    if not urls:
        return print('nothing to submit')
    body = json.dumps({'host': SITE_URL.split('//')[1], 'key': INDEXNOW_KEY, 'keyLocation': f'{SITE_URL}/{INDEXNOW_KEY}.txt',
                       'urlList': urls[:10000]}).encode()
    req = urllib.request.Request('https://api.indexnow.org/indexnow', data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8', **UA})
    try:
        print(f'IndexNow: {urllib.request.urlopen(req, timeout=30).status} for {len(urls)} pages')
    except Exception as e:  # never fail the deploy over it
        print(f'IndexNow: {e}')


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
    done, kept, caps, start = [], [], [], time.time()
    for n, sid in enumerate([int(x) for x in sys.argv[2:]] or servers()):   # server ids on the command line: just those
        if n: time.sleep(GAP)
        try:
            last = json.loads(published(f'prices/{sid}.json'))
        except Exception:
            last = None
        try:
            if time.time() - start > BUDGET:
                raise TimeoutError('out of time this hour')
            items = market(sid, keys, tries=3)   # an item without sellers has no price but keeps its last one
            # a half-empty answer (Aion2Market mid-update, say) would wipe out good prices: keep the last copy instead
            had = len(last['prices']) if last else 0
            if len(items) < SANE_SHARE * had:
                raise ValueError(f'only {len(items)} prices, the last run had {had}')
        except Exception as e:  # keep the last published copy so the server doesn't vanish for an hour
            print(f'{sid}: {e}')
            if last:
                (out / f'{sid}.json').write_text(json.dumps(last, separators=(',', ':')), encoding='utf8')
                done.append(sid); kept.append(sid); caps.append(last.get('captured'))
            continue
        captured = max((m['captured_at'] for m in items if m.get('captured_at')), default=None)
        data = {'server': sid, 'fetched': now(), 'captured': captured,
                'prices': {str(m['item_key']): [m['price'], m['listings'], m['last_price'], m['last_seen_at']] for m in items}}
        (out / f'{sid}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf8')
        done.append(sid); caps.append(captured)
    have_speeds = sorted(int(f.stem) for f in (DIST / 'speeds').glob('*.json'))
    # captured: Aion2Market's newest capture among all servers (the Worker's staleness alarm reads it)
    (out / 'index.json').write_text(json.dumps({'servers': done, 'speeds': have_speeds, 'fetched': now(), 'kept': kept,
                                                'captured': max(filter(None, caps), default=None)}), encoding='utf8')
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
    {'build': build, 'prices': prices, 'speeds': speeds, 'due': due, 'changed': changed, 'indexnow': indexnow}.get(cmd, lambda: sys.exit(__doc__))()
