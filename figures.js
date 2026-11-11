// Typical crafting cost per item page, with the calculator's own maths: app/index.html's script runs here with a
// stand-in for the browser, once per server, at proficiency 100 in every profession and nothing owned. Per item:
// the median over the servers that price it (its faction's), for the cheapest regular recipe and the guaranteed one.
//
//   node figures.js <dist folder>     # needs dist/data.json and dist/prices/<server>.json; prints JSON
//
// hosting.py figures runs it once a day and writes the result into the item pages.
const fs = require('fs'), path = require('path'), vm = require('vm');
const DIST = process.argv[2] || 'dist';
const html = fs.readFileSync(path.join(__dirname, 'app', 'index.html'), 'utf8');
const code = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>')).replace(/\bboot\(\);\s*$/, '');

// a do-nothing element: any property, call or loop on it works and does nothing
const stub = new Proxy(function(){}, {
  get: (t, k) => k === Symbol.iterator ? function*(){} : k === Symbol.toPrimitive ? () => '' : k === 'length' ? 0 : stub,
  apply: () => stub, construct: () => stub, set: () => true,
});
const ctx = vm.createContext({
  window: {FORGE_LOCAL: false}, document: stub, localStorage: {getItem: () => null, setItem(){}},
  location: {pathname: '/', search: '', href: 'https://daevaforge.com/'}, history: stub, navigator: stub,
  matchMedia: () => ({matches: true, addEventListener(){}}), setTimeout: () => 0, clearTimeout(){}, setInterval: () => 0,
  requestAnimationFrame: () => 0, fetch: () => new Promise(() => {}), CSS: {escape: s => s}, URL, URLSearchParams, console,
});
vm.runInContext(code, ctx);

const read = f => JSON.parse(fs.readFileSync(path.join(DIST, f), 'utf8'));
const data = read('data.json');
const servers = fs.readdirSync(path.join(DIST, 'prices')).filter(f => /^\d+\.json$/.test(f)).map(f => +f.slice(0, -5));
ctx.data = data;
ctx.speeds = {};
const costs = {};  // slug -> {old: [per server], g: [per server]}
for(const id of servers){
  const s = data.servers.find(x => x[0] === id); if(!s) continue;
  let p, v = null;
  try{ p = read(`prices/${id}.json`) }catch(e){ continue }
  try{ v = read(`speeds/${id}.json`) }catch(e){}
  ctx.run = {id, s, prices: p.prices, velocity: v ? v.v : {}};
  const out = vm.runInContext(`(() => {
    S.data = data; S.data.velocity = run.velocity; S.prices = run.prices; S.mode = 'single';
    S.server = {id: run.id, name: run.s[1], region: run.s[2], faction: run.s[3]};
    S.mastery = Object.fromEntries(PROFS.map(p => [p, MAX_MASTERY]));
    S.owned = {}; S.manual = {}; S.src = {}; S.sourcing = 'cheapest';
    indexRecipes(); memo = new Map();
    const by = {};
    for(const r of RECIPES) (by[slugOf(item(r.p)[0])] ||= []).push(r);
    const best = es => es.map(costOfOne).filter(c => c != null && isFinite(c)).sort((a, b) => a - b)[0];
    const res = {};
    for(const [slug, rs] of Object.entries(by)){
      const es = rs.map(evaluate);
      res[slug] = {old: best(es.filter(e => !e.r.g)), g: best(es.filter(e => e.r.g))};
    }
    return JSON.stringify(res);
  })()`, ctx);
  for(const [slug, c] of Object.entries(JSON.parse(out))){
    const o = costs[slug] ||= {old: [], g: []};
    if(c.old != null) o.old.push(c.old);
    if(c.g != null) o.g.push(c.g);
  }
}
const median = a => { if(!a.length) return null; a.sort((x, y) => x - y); const m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2 };
const items = {};
for(const [slug, c] of Object.entries(costs)){
  const old = median(c.old), g = median(c.g);
  if(old == null && g == null) continue;
  items[slug] = {cost: Math.round(old ?? g), ...(old != null && g != null ? {g: Math.round(g)} : {}), n: Math.max(c.old.length, c.g.length)};
}
process.stdout.write(JSON.stringify({servers: servers.length, mastery: vm.runInContext('MAX_MASTERY', ctx), items}));
