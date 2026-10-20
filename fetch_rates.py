"""Collect per-recipe crafting success tables from GameWith item pages.

Each GameWith item page lists, per faction, the success rate of the recipe that makes the
item for every level difference (your mastery minus the recipe's mastery level).
Results are cached in data/rates.json, keyed by item id; already-fetched ids are skipped.

Usage: python fetch_rates.py data/recipes.json [--delay 0.4]
"""
import html, json, re, sys, time, urllib.request
from pathlib import Path

OUT = Path(__file__).parent / 'data' / 'rates.json'
UA = {'User-Agent': 'Mozilla/5.0 (personal crafting calculator; low rate)'}


def parse(page):
    m = re.search(r'<section id="crafting".*?</section>', page, re.S)
    if not m:
        return None
    sec = m.group(0)
    # split per faction block: a block starts with an optional faction note, then tables
    blocks = re.split(r'(?=<p class="items-note">(?:Elyos only|Asmodians? only|Elyos/Asmodians?)</p>)', sec)
    result = {}
    for b in blocks:
        note = re.search(r'<p class="items-note">([^<]*only|Elyos/Asmodians?)</p>', b)
        faction = note.group(1) if note else 'both'
        combo = re.search(r'Combo chance: ([\d.]+)%', b)
        rates = {}
        for t in re.findall(r'<table class="dbs-rate-table">(.*?)</table>', b, re.S):
            heads = [html.unescape(x) for x in re.findall(r'<th>(.*?)</th>', t)][1:]
            rows = re.findall(r'<tr><td>(.*?)</td>(.*?)</tr>', t, re.S)
            for label, cells in rows:
                vals = re.findall(r'<td>([\d.]+)%</td>', cells)
                if label.startswith('Success'):
                    for h, v in zip(heads, vals):
                        rates[int(h)] = float(v) / 100
        if rates:
            key = 'light' if faction.startswith('Elyos only') else 'dark' if faction.startswith('Asmod') else 'both'
            result[key] = {'combo': float(combo.group(1)) / 100 if combo else None,
                           'rates': [rates[k] for k in sorted(rates)], 'from': min(rates)}
    return result or None


def main():
    recipes = json.load(open(sys.argv[1], encoding='utf8'))
    delay = float(sys.argv[sys.argv.index('--delay') + 1]) if '--delay' in sys.argv else 0.4
    ids = sorted({recipes['items'][r['p']]['i'] for r in recipes['recipes'] if r['p'] in recipes['items']})
    cache = json.load(open(OUT, encoding='utf8')) if OUT.exists() else {}
    todo = [i for i in ids if str(i) not in cache]
    print(f'{len(ids)} products, {len(todo)} to fetch', flush=True)
    for n, i in enumerate(todo, 1):
        try:
            req = urllib.request.Request(f'https://gamewith.ai/aion2/en/items/{i}', headers=UA)
            page = urllib.request.urlopen(req, timeout=20).read().decode('utf8', 'replace')
            cache[str(i)] = parse(page)
        except Exception as e:  # 404s etc: remember as missing, retry later by deleting the key
            cache[str(i)] = {'error': str(e)[:80]}
        if n % 25 == 0:
            OUT.write_text(json.dumps(cache), encoding='utf8')
            print(f'{n}/{len(todo)}', flush=True)
        time.sleep(delay)
    OUT.write_text(json.dumps(cache), encoding='utf8')
    ok = sum(1 for v in cache.values() if v and 'error' not in v)
    print(f'done: {ok} with tables, {len(cache) - ok} without', flush=True)


if __name__ == '__main__':
    main()
