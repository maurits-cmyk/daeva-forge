"""Official crafting success tables from NC's probability disclosure (probability.plaync.com/aion2).

NC publishes the success chance of every recipe for each proficiency level difference (0-120),
to six decimals, as the in-game "Expected Probability" tab shows. The disclosure is the Korean
service, keyed by Korean item name, so each Global recipe product is matched through its Korean
name (NC's item API) plus faction and yield. Writes data/official_rates.json; Korean names are
cached in data/kr_names.json.

Usage: python fetch_official_rates.py
"""
import json, sys, time, urllib.request
from pathlib import Path

DATA = Path(__file__).parent / 'data'
UA = {'User-Agent': 'Mozilla/5.0 (personal crafting calculator)'}
API = 'https://probability.plaync.com/api/aion2'
CRAFT_CATEGORY = '6a5f25e59bb1696f4bf77317'  # 제작 (crafting)


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf8'))


def official_tables():
    version = get(f'{API}/versions')[0]['version']
    token = get(f'{API}/contents/{CRAFT_CATEGORY}?version={version}')[0]['resourceToken']
    records, page = [], 1
    while True:
        d = get(f'{API}/resources?version={version}&page={page}', {'Resource-Token': token})
        records += d['records']
        if page >= d['pageNavigation']['lastPage']:
            break
        page += 1
    tables = {}
    for r in records:
        for e in r.get('@entries') or [r]:
            if e.get('콤보여부') != '일반':  # the "basic" success row (the other row is "콤보")
                continue
            vals = []
            for i in range(0, 121):
                v = e.get(f'레벨 차이 {i}')
                if v is None:
                    break
                vals.append(round(float(v.rstrip('%')) / 100, 8))
            race = {'천족': 'Light', '마족': 'Dark'}.get(r['종족'], r['종족'])
            tables[f"{r['아이템 이름']}|{race}|{r['제작 결과 수량']}"] = vals
    return version, tables


def kr_names(keys):
    cache_file = DATA / 'kr_names.json'
    cache = json.load(open(cache_file, encoding='utf8')) if cache_file.exists() else {}
    todo = [k for k in keys if k not in cache]
    for n, k in enumerate(todo, 1):
        try:
            cache[k] = get(f'https://aion2.plaync.com/api/gameconst/item?id={k}&enchantLevel=0&lang=ko').get('name')
        except Exception:
            cache[k] = None
        if n % 50 == 0:
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf8')
            print(f'names {n}/{len(todo)}', flush=True)
        time.sleep(0.2)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf8')
    return cache


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    hub = json.load(open(DATA / 'recipes.json', encoding='utf8'))
    items = hub['items']
    key = lambda code: str(items[code]['i']) if code in items and items[code].get('i') else None  # noqa: E731
    version, tables = official_tables()
    products = {key(r['p']) for r in hub['recipes']} - {None}
    names = kr_names(sorted(products))
    out, missing = {}, 0
    for r in hub['recipes']:
        k = key(r['p'])
        t = tables.get(f"{names.get(k)}|{r['race']}|{r['y']}") if k else None
        if t:  # keyed by recipe: one product can have several recipes (e.g. ×1 and ×10 batches)
            out[str(r['id'])] = {'from': 0, 'r': t}
        else:
            missing += 1
    (DATA / 'official_rates.json').write_text(json.dumps({'version': version, 'rates': out}, ensure_ascii=False), encoding='utf8')
    print(f'disclosure {version}: {len(tables)} tables; matched {len(out)} recipes, {missing} unmatched')


if __name__ == '__main__':
    main()
