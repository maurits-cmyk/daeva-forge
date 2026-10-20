"""Collect NPC vendor prices for every recipe ingredient from aion2hub item pages.

aion2hub's "How to Obtain" panel lists "Bought from vendor" entries (NPC, price, currency, zone),
taken from the Global client's shop tables. Results go to data/vendor.json, keyed by item id;
items already fetched are skipped (delete the file to refetch everything).

Usage: python fetch_vendor.py [--delay 0.4]
"""
import html, json, re, sys, time, urllib.request
from pathlib import Path

DATA = Path(__file__).parent / 'data'
OUT = DATA / 'vendor.json'
UA = {'User-Agent': 'Mozilla/5.0 (personal crafting calculator; low rate)'}


def parse(page):
    m = re.search(r'Bought from vendor</span>.*?<ul[^>]*>(.*?)</ul>', page, re.S)
    if not m:
        return []
    out = []
    for li in re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.S):
        text = lambda pat: (lambda r: html.unescape(re.sub(r'<[^>]+>|<!-- -->', '', r.group(1))).strip() if r else None)(re.search(pat, li, re.S))  # noqa: E731
        npc = text(r'<span class="text-gray-200">(.*?)</span>')
        price = re.search(r'tabular-nums[^>]*>([\d,]+)', li)
        cur = text(r'<span class="text-gray-500">(.*?)</span>')
        zone = text(r'<a [^>]*>(.*?)</a>')
        if price:
            out.append({'npc': npc, 'price': int(price.group(1).replace(',', '')), 'currency': cur, 'zone': zone})
    return out


def main():
    delay = float(sys.argv[sys.argv.index('--delay') + 1]) if '--delay' in sys.argv else 0.4
    hub = json.load(open(DATA / 'recipes.json', encoding='utf8'))
    keys = sorted({hub['items'][c['i']]['i'] for r in hub['recipes'] for c in r['c']
                   if c['i'] in hub['items'] and hub['items'][c['i']].get('i')})
    cache = json.load(open(OUT, encoding='utf8')) if OUT.exists() else {}
    todo = [k for k in keys if str(k) not in cache]
    print(f'{len(keys)} ingredients, {len(todo)} to fetch', flush=True)
    for n, k in enumerate(todo, 1):
        try:
            req = urllib.request.Request(f'https://aion2hub.com/database/items/{k}', headers=UA)
            cache[str(k)] = parse(urllib.request.urlopen(req, timeout=20).read().decode('utf8', 'replace'))
        except Exception as e:
            cache[str(k)] = {'error': str(e)[:80]}
        if n % 25 == 0:
            OUT.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf8')
            print(f'{n}/{len(todo)}', flush=True)
        time.sleep(delay)
    OUT.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf8')
    sold = sum(1 for v in cache.values() if isinstance(v, list) and v)
    print(f'done: {sold} of {len(cache)} ingredients sold by a vendor', flush=True)


if __name__ == '__main__':
    main()
