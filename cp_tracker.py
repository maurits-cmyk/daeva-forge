"""Combat Power tracker: records a character's CP and everything that feeds it, from NC's public API.

  python cp_tracker.py                 # take one reading for the configured character
  python cp_tracker.py --set <name>   # pick the character (NA East by default; --region eu|naw|la|asia)

Readings go to data/cp_history.json. A reading is stored only when something changed (CP, gear,
enchants, skills and Stigmas, Daevanion nodes, titles, stats, pet, wings); otherwise only the
"last checked" time moves. serve.py takes a reading on start and every 30 minutes while it runs.
"""
import json, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / 'data'
CONFIG, HISTORY = DATA / 'character.json', DATA / 'cp_history.json'
UA = {'User-Agent': 'Mozilla/5.0 (personal CP tracker)'}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf8'))


def find(name, region='nae', server_id=None):
    q = urllib.parse.urlencode({'keyword': name, 'region': region, 'localeInfo': 'en-US', 'page': 1, 'size': 20})
    hits = _get(f'https://api-search.plaync.com/aion2global/search/v2/character?{q}')['list']
    clean = lambda s: s.replace('<strong>', '').replace('</strong>', '')  # noqa: E731
    hits = [h for h in hits if clean(h['name']).lower() == name.lower() and (server_id is None or h['serverId'] == server_id)]
    hits.sort(key=lambda h: -h['level'])
    if not hits:
        raise SystemExit(f'No character named {name} in region {region}')
    h = hits[0]
    return {'name': clean(h['name']), 'region': region, 'serverId': h['serverId'], 'serverName': h['serverName'],
            'characterId': urllib.parse.unquote(h['characterId'])}


def snapshot(cfg):
    q = urllib.parse.urlencode({'lang': 'en', 'characterId': cfg['characterId'], 'serverId': cfg['serverId'], 'region': cfg['region']})
    info = _get(f'https://aion2.plaync.com/api/character/info?{q}')
    eq = _get(f'https://aion2.plaync.com/api/character/equipment?{q}')
    p = info['profile']
    stats = {s['type']: s['value'] for s in (info.get('stat') or {}).get('statList') or []}
    pw = eq.get('petwing') or {}
    return {
        'cp': p.get('combatPower'), 'level': p.get('characterLevel'), 'itemLevel': stats.pop('ItemLevel', None),
        'name': p.get('characterName'), 'className': p.get('className'), 'server': p.get('serverName'),
        'title': p.get('titleName'), 'portrait': p.get('profileImage'),
        'gear': {g['slotPosName']: [g['id'], g['name'], g['enchantLevel'], g['exceedLevel'], g['grade']]
                 for g in eq['equipment']['equipmentList']},
        'skills': {str(s['id']): [s['name'], s['category'], s['skillLevel'], s['equip']]
                   for s in eq['skill']['skillList'] if s.get('acquired')},
        'boards': {b['name']: [b['openNodeCount'], b['totalNodeCount']] for b in info['daevanion']['boardList']},
        'titles': (info.get('title') or {}).get('ownedCount'),
        'stats': stats,
        'pet': [pw['pet']['id'], pw['pet']['name'], pw['pet']['level']] if pw.get('pet') else None,
        'wing': [pw['wing']['id'], pw['wing']['name'], pw['wing']['enchantLevel']] if pw.get('wing') else None,
    }


TRACKED = ('cp', 'level', 'itemLevel', 'gear', 'skills', 'boards', 'titles', 'stats', 'pet', 'wing')


def changes(a, b):
    """Human-readable differences from reading a to reading b."""
    out = []
    if a['level'] != b['level']:
        out.append(f"Level {a['level']} → {b['level']}")
    for slot in sorted(set(a['gear']) | set(b['gear'])):
        x, y = a['gear'].get(slot), b['gear'].get(slot)
        if x == y:
            continue
        if not x:
            out.append(f"{slot}: equipped {y[1]} +{y[2]}")
        elif not y:
            out.append(f"{slot}: removed {x[1]}")
        elif x[0] != y[0]:
            out.append(f"{slot}: {x[1]} +{x[2]} → {y[1]} +{y[2]}")
        else:
            bits = []
            if x[2] != y[2]:
                bits.append(f"+{x[2]} → +{y[2]}")
            if x[3] != y[3]:
                bits.append(f"exceed {x[3]} → {y[3]}")
            out.append(f"{y[1]} {', '.join(bits)}")
    for sid in sorted(set(a['skills']) | set(b['skills'])):
        x, y = a['skills'].get(sid), b['skills'].get(sid)
        if x == y:
            continue
        kind = 'Stigma' if (y or x)[1] == 'Dp' else 'Skill'
        if not x:
            out.append(f"{kind} learned: {y[0]} Lv {y[2]}")
        elif not y:
            out.append(f"{kind} gone: {x[0]}")
        else:
            if x[2] != y[2]:
                out.append(f"{kind} {y[0]} Lv {x[2]} → {y[2]}")
            if x[3] != y[3]:
                out.append(f"{kind} {y[0]} {'equipped' if y[3] else 'unequipped'}")
    for name in sorted(set(a['boards']) | set(b['boards'])):
        x, y = a['boards'].get(name, [0, 0]), b['boards'].get(name, [0, 0])
        if x[0] != y[0]:
            out.append(f"Daevanion {name}: {x[0]} → {y[0]} nodes")
    if a['titles'] != b['titles']:
        out.append(f"Titles owned {a['titles']} → {b['titles']}")
    if a['pet'] != b['pet'] and b['pet']:
        out.append(f"Pet: {b['pet'][1]} Lv {b['pet'][2]}")
    if a['wing'] != b['wing'] and b['wing']:
        out.append(f"Wings: {b['wing'][1]} +{b['wing'][2]}")
    stat_moves = [f"{k} {a['stats'].get(k, 0)} → {v}" for k, v in b['stats'].items() if a['stats'].get(k) != v]
    if stat_moves and not out:
        out.append('Stats: ' + ', '.join(stat_moves))
    if a['itemLevel'] != b['itemLevel']:
        out.append(f"Item level {a['itemLevel']} → {b['itemLevel']}")
    return out


def load():
    cfg = json.loads(CONFIG.read_text(encoding='utf8')) if CONFIG.exists() else None
    hist = json.loads(HISTORY.read_text(encoding='utf8')) if HISTORY.exists() else {'readings': [], 'checked': None}
    return cfg, hist


def record():
    """Take a reading; store it if anything tracked changed. Returns the history."""
    cfg, hist = load()
    if not cfg:
        raise RuntimeError('No character set. Run: python cp_tracker.py --set <name>')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    snap = snapshot(cfg)
    last = hist['readings'][-1] if hist['readings'] else None
    if not last or any(last[k] != snap[k] for k in TRACKED):
        snap['t'] = now
        snap['changes'] = changes(last, snap) if last else ['First reading']
        hist['readings'].append(snap)
    else:  # keep display fields (title, portrait) current without adding a reading
        last.update({k: snap[k] for k in ('title', 'portrait', 'name', 'server', 'className')})
    hist['checked'] = now
    DATA.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False), encoding='utf8')
    return hist


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    args = sys.argv[1:]
    if '--set' in args:
        region = args[args.index('--region') + 1] if '--region' in args else 'nae'
        cfg = find(args[args.index('--set') + 1], region)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf8')
        print(f"Tracking {cfg['name']} on {cfg['serverName']} ({region})")
    h = record()
    r = h['readings'][-1]
    print(f"{r['name']}: {r['cp']:,} CP, item level {r['itemLevel']}; {len(h['readings'])} reading(s), last change: {'; '.join(r['changes'])}")
