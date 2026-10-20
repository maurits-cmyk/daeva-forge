# Daeva Forge

Unofficial fan site: expected crafting profit for AION 2 at your mastery, from current market prices. Free, no paywall.
Not affiliated with, endorsed or sponsored by NCSOFT.

## How it works

- `app/index.html` is the whole page; `app/data.json` holds recipes, success chances, supply requests and vendor prices.
- `hosting.py build` + `hosting.py prices` assemble `dist/`; GitHub Actions runs them every hour (about 10 minutes
  after Aion2Market captures its prices) and deploys `dist/` to a Cloudflare Worker (`wrangler.jsonc`).
- `hosting.py speeds` recomputes sale speeds once a day into `site/speeds/`.
- Servers fetched: `site/servers.txt`.
- `worker.js` handles the feedback form (POST /api/feedback) and emails it via Cloudflare Email Routing; everything else is static.

## Local use

```
python serve.py              # http://localhost:8642, live prices for any server
python build_data.py         # rebuild app/data.json (recipes, success tables, snapshot)
```

## Data

Recipes and vendor prices: [AION2 Hub](https://aion2hub.com). Success chances: [NC's probability disclosure](https://probability.plaync.com/aion2/index)
and [GameWith](https://gamewith.ai/aion2/en). Supply requests: [wikily](https://wikily.gg/aion-2). Prices: [Aion2Market](https://aion2.exchange/).

AION, AION 2 and NCSOFT are trademarks of NCSOFT Corporation.
