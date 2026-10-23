"""Build the crafting calculator's data: app/data.json (recipes, success tables, supply requests, vendor prices;
committed, the site is built from it) and app/snapshot.json (one server's prices and sale speeds for local use;
not committed, the site has hourly prices and weekly sale speeds of its own).

  python build_data.py                     # Israphel (NA East, Asmodian), reuse cached recipes
  python build_data.py --server 12101      # any aion2.exchange server id (see /api/servers)
  python build_data.py --refresh-recipes   # re-extract recipes from aion2hub's crafting calculator
  python build_data.py --refresh-speeds    # refetch sale speeds now (otherwise cached for 12 h)

Sources: recipes and vendor prices from aion2hub.com (Global client data), supply request groups
from wikily.gg, success tables from NC's probability disclosure (fetch_official_rates.py) and
gamewith.ai (fetch_rates.py -> data/rates.json), prices from aion2.exchange (hourly asks).
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA, APP = ROOT / 'data', ROOT / 'app'
UA = {'User-Agent': 'Mozilla/5.0 (personal crafting calculator)'}


def get(url, as_json=True, tries=5):
    for n in range(tries):
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf8')
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:  # aion2.exchange answers 503 now and then; back off and retry
            if e.code < 500 or n == tries - 1:
                raise
            time.sleep(5 * (n + 1))


def refresh_recipes():
    """aion2hub embeds the recipe set as a JSON.parse('...') literal in one calculator chunk."""
    import subprocess
    page = get('https://aion2hub.com/tools/crafting-calculator', as_json=False)
    for chunk in sorted(set(re.findall(r'/_next/static/chunks/[a-z0-9_-]+\.js', page))):
        js = get('https://aion2hub.com' + chunk, as_json=False)
        if '"byProduct"' in js and '"recipes"' in js and "JSON.parse('" in js:
            tmp = DATA / 'hub_chunk.js'
            tmp.write_text(js, encoding='utf8')
            subprocess.run([sys.executable, '-I', str(ROOT / 'extract_hub.py'), str(tmp), str(DATA / 'recipes.json')], check=True)
            return
    raise SystemExit('recipe chunk not found on aion2hub; the site layout changed')


def main():
    args = sys.argv[1:]
    server_id = int(args[args.index('--server') + 1]) if '--server' in args else 12101
    if '--refresh-recipes' in args or not (DATA / 'recipes.json').exists():
        refresh_recipes()
    hub = json.load(open(DATA / 'recipes.json', encoding='utf8'))
    rates_raw = json.load(open(DATA / 'rates.json', encoding='utf8')) if (DATA / 'rates.json').exists() else {}

    items = hub['items']
    key = lambda code: items[code]['i'] if code in items and items[code].get('i') else code  # noqa: E731
    used, recipes = set(), []
    for r in hub['recipes']:
        if r['p'] not in items:
            continue
        rec = {'id': r['id'], 'p': key(r['p']), 'y': r['y'], 'prof': r['prof'], 'ml': r['ml'],
               'race': r['race'], 'fee': r['fee'],
               'combo': {'p': key(r['combo']['p']), 'pct': r['combo']['pct']} if r.get('combo') else None,
               'c': [[key(c['i']), c['q']] for c in r['c']]}
        recipes.append(rec)
        used.update([rec['p']] + [c[0] for c in rec['c']] + ([rec['combo']['p']] if rec['combo'] else []))
    by_key = {v['i']: v for v in items.values() if v.get('i')}
    item_out = {}
    for k in used:
        v = by_key.get(k) or items.get(k) or {'n': str(k), 'g': None}
        item_out[str(k)] = [v.get('n') or str(k), v.get('g')]

    rates = {}
    for k, v in rates_raw.items():
        if v and 'error' not in v:
            rates[k] = {f: {'from': t['from'], 'r': [round(x, 4) for x in t['rates']]} for f, t in v.items()}
    # NC's official disclosure (fetch_official_rates.py) covers every real recipe at 6 decimals and
    # agrees with GameWith wherever both exist; it wins, GameWith fills any gap
    off_file = DATA / 'official_rates.json'
    if '--refresh-recipes' in args or not off_file.exists():
        import subprocess
        subprocess.run([sys.executable, '-I', str(ROOT / 'fetch_official_rates.py')], check=False)
    official = {}
    if off_file.exists():
        official = {rid: {'from': t['from'], 'r': [round(x, 6) for x in t['r']]}
                    for rid, t in json.load(open(off_file, encoding='utf8'))['rates'].items()}

    # NPC vendor prices (fetch_vendor.py): keep the cheapest offer paid in Kina
    vendor_raw = json.load(open(DATA / 'vendor.json', encoding='utf8')) if (DATA / 'vendor.json').exists() else {}
    vendor = {}
    for k, offers in vendor_raw.items():
        kina = [o for o in offers if isinstance(offers, list) and 'Kina' in (o.get('currency') or '')] if isinstance(offers, list) else []
        if kina and k in item_out:
            o = min(kina, key=lambda o: o['price'])
            vendor[k] = [o['price'], o['npc'], o['zone']]

    # Crafting supply requests (wikily.gg): NPCs take any item of a group, so buyers pick the cheapest one
    sup_file = DATA / 'supply_requests.json'
    if '--refresh-recipes' in args or not sup_file.exists():
        rows, off = [], 0
        while True:
            page = get(f'https://wikily.gg/api/wikis/aion-2/datasets/supply-requests/list?limit=120&offset={off}')
            rows += [r['data'] for r in page['rows']]
            off += len(page['rows'])
            if not page['rows'] or off >= page['totalCount']:
                break
        sup_file.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf8')
    by_name = {}
    for k, (name, _) in item_out.items():
        by_name.setdefault(name.lower(), []).append(int(k) if k.isdigit() else k)
    groups = []
    for s in json.load(open(sup_file, encoding='utf8')):
        members = sorted({k for it in s['items'] for k in by_name.get(it['title'].lower(), [])}, key=str)
        names = {it['title'].lower() for it in s['items'] if it['title'].lower() in by_name}
        if len(names) > 1:  # single-item requests don't change which item a buyer picks
            tabs = re.findall(r'(\d+) (?:of the listed items )?in the ([A-Za-z: ]+?) tab', s.get('lead', ''))
            groups.append({'name': s['name'], 'faction': s.get('faction'), 'members': members,
                           'deliver': ', '.join(f'{n} {t}' for n, t in tabs)})

    # Gear doesn't stack: each item takes one of the 10 sale slots
    gear = sorted({k for code, v in items.items() if code.startswith('equip_') and str(v.get('i')) in item_out for k in [str(v['i'])]})

    # Crafting EXP per successful craft: measured values (data/exp_measured.json) where known, otherwise an
    # estimate from grade and recipe level. Rough anchors: base materials 20 (batch x10/x30: 112),
    # Common gear 74 + 3 x level (Orichalcum Cloak, Lv 10 = 104, measured), Expert's 240, Artisan's 600
    # (KR community figures), Dragon Lord tier and refined materials extrapolated.
    measured = json.load(open(DATA / 'exp_measured.json', encoding='utf8'))['entries'] if (DATA / 'exp_measured.json').exists() else []
    meas = {(m['name'].lower(), m['y']): m['exp'] for m in measured}
    gear_codes = {code for code in items if code.startswith('equip_')}
    exp = {}
    for r in hub['recipes']:
        if r['p'] not in items:
            continue
        name, grade, ml, y = items[r['p']].get('n', ''), items[r['p']].get('g'), r['ml'], r['y']
        if (name.lower(), y) in meas:
            exp[str(r['id'])] = [meas[(name.lower(), y)], 'm']
            continue
        if r['p'] in gear_codes:
            single = {'Common': 74 + 3 * ml, 'Rare': 240, 'Epic': 600, 'Unique': 1500}.get(grade, 74 + 3 * ml)
        elif ml >= 51:
            single = 383 + 11 * (ml - 51)          # refined Balaur materials (KR examples 383-868)
        else:
            single = 20 if grade in (None, 'Common') else 20 + 2 * ml
        if y >= 10:
            single = single * 5.6                  # batch recipes: 112 vs 20 measured
        exp[str(r['id'])] = [round(single), 'e']

    servers = get('https://aion2.exchange/api/servers')['servers']
    srv = next(s for s in servers if s['server_id'] == server_id)
    market = get(f'https://aion2.exchange/api/items?server={server_id}&limit=1000')['items']
    prices = {str(m['item_key']): [m['price'], m['listings'], m['last_price'], m['last_seen_at']]
              for m in market if str(m['item_key']) in item_out}

    # Sale speed of crafted products: listings that disappeared per day over the last week, from the
    # hourly snapshots (sales plus cancellations; hourly sampling misses churn inside an hour)
    products = {str(r['p']) for r in recipes} | {str(r['combo']['p']) for r in recipes if r['combo']}
    # cached per server for 12 h (one request per item is slow when aion2.exchange throttles)
    vel_file = DATA / f'velocity_{server_id}.json'
    cache = json.load(open(vel_file, encoding='utf8')) if vel_file.exists() else {}
    if not cache and (APP / 'snapshot.json').exists():  # seed from the last snapshot of this server
        old = json.load(open(APP / 'snapshot.json', encoding='utf8'))
        if old.get('server', {}).get('id') == server_id and old.get('velocity'):
            cache = {'at': time.time() - 6 * 3600, 'v': old['velocity']}
    fresh = cache and time.time() - cache.get('at', 0) < 12 * 3600 and '--refresh-speeds' not in args
    velocity = dict(cache.get('v', {})) if fresh else {}
    for k in ([] if fresh else sorted(products & set(prices))):
        try:
            pts = get(f'https://aion2.exchange/api/items/{k}/prices?server={server_id}')['points']
        except Exception:
            continue
        if len(pts) >= 24:
            drops = sum(max(0, a['listings'] - b['listings']) for a, b in zip(pts, pts[1:]))
            velocity[k] = round(drops / (len(pts) / 24), 2)
        time.sleep(0.25)
    if not fresh:
        vel_file.write_text(json.dumps({'at': time.time(), 'v': velocity}), encoding='utf8')

    server = {'id': srv['server_id'], 'name': srv['name'], 'region': srv['region_name'], 'faction': srv['faction']}
    out = {'recipesBuilt': hub.get('builtAt'), 'server': server,  # server: the one shown first
           'servers': [[s['server_id'], s['name'], s['region'], s['faction']] for s in servers],
           'items': item_out, 'recipes': recipes, 'rates': rates, 'official': official, 'vendor': vendor, 'groups': groups, 'gear': gear, 'exp': exp}
    snap = {'built': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'server': server, 'prices': prices, 'velocity': velocity}
    APP.mkdir(exist_ok=True)
    (APP / 'data.json').write_text(json.dumps(out, separators=(',', ':'), ensure_ascii=False), encoding='utf8')
    (APP / 'snapshot.json').write_text(json.dumps(snap, separators=(',', ':'), ensure_ascii=False), encoding='utf8')
    print(f"{len(recipes)} recipes, {len(item_out)} items, {len(official)} official + {len(rates)} GameWith success tables, {len(vendor)} vendor prices, {len(groups)} supply request groups, {len(velocity)} sale speeds, {sum(1 for v in exp.values() if v[1] == 'm')} measured EXP values, "
          f"{len(prices)} priced items on {srv['name']} ({srv['region_name']}, {srv['faction']}) -> app/snapshot.json "
          f"({(APP / 'data.json').stat().st_size // 1024} KB)")


if __name__ == '__main__':
    main()
