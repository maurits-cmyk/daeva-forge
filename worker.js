// Daeva Forge on Cloudflare: the files in dist/ are served as static assets (they never reach this code);
// the one dynamic route, POST /api/feedback, emails a visitor's message to the maintainer. A cron trigger
// starts the hourly price run on GitHub right after Aion2Market's capture.
import { EmailMessage } from 'cloudflare:email';

const FROM = 'feedback@daevaforge.com';       // Email Routing must be on for daevaforge.com
const SHOWN_TO = 'mawreez@daevaforge.com';     // the To header Gmail sees, so it replies from this address
const KINDS = ['Bug', 'Idea', 'Other'];
const REPO = 'maurits-cmyk/daeva-forge';

// The inbox is the Worker secret FEEDBACK_TO (kept out of this public repo); it must be a verified
// Email Routing destination address, the only kind the send_email binding can deliver to.
export default {
  async fetch(req, env) {
    if (new URL(req.url).pathname === '/api/feedback') {
      return req.method === 'POST' ? feedback(req, env) : json({error: 'Use POST.'}, 405);
    }
    return env.ASSETS.fetch(req);
  },
  // GH_DISPATCH: a fine-grained GitHub token for this repository only, with Actions read and write
  async scheduled(event, env) {
    try { await staleAlarm(env) } catch (e) { console.log('staleness check failed: ' + e) }
    if (!env.GH_DISPATCH) throw new Error("GH_DISPATCH is not set: the hourly price run waits for GitHub's late schedule");
    const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/prices.yml/dispatches`, {
      method: 'POST', body: JSON.stringify({ref: 'main'}),
      headers: {Authorization: `Bearer ${env.GH_DISPATCH}`, Accept: 'application/vnd.github+json', 'User-Agent': 'daeva-forge-worker'},
    });
    if (!res.ok) throw new Error(`GitHub answered ${res.status}: ${await res.text()}`);  // shows in the Worker's logs
  },
};

async function feedback(req, env) {
  if (+req.headers.get('content-length') > 20000) return json({error: 'Too long.'}, 413);
  let f;
  try { f = await req.json() } catch { return json({error: 'Bad request.'}, 400) }
  const text = (v, max) => String(v ?? '').trim().slice(0, max);
  const msg = text(f.message, 4000), name = text(f.name, 80), email = text(f.email, 200);
  const kind = KINDS.includes(f.kind) ? f.kind : 'Other', server = text(f.server, 120), ua = text(req.headers.get('user-agent'), 300);
  if (!env.FEEDBACK_TO) return json({error: 'Feedback is not set up yet.'}, 503);
  if (f.website) return json({ok: true});  // honeypot: only bots fill the hidden field
  if (msg.length < 3) return json({error: 'Write a message first.'}, 400);
  const replyTo = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(email) ? email : '';

  // one message per visitor per minute (per Cloudflare location; enough to stop accidental repeats and casual floods)
  const ip = req.headers.get('cf-connecting-ip') || 'unknown', key = new Request('https://feedback-limit.invalid/' + encodeURIComponent(ip));
  if (await caches.default.match(key)) return json({error: 'Please wait a minute before sending another message.'}, 429);
  await caches.default.put(key, new Response('1', {headers: {'Cache-Control': 'max-age=60'}}));

  const body = [msg, '', '---', `From: ${name || '(no name)'}${replyTo ? ' <' + replyTo + '>' : ''}`, `Server: ${server || '(unknown)'}`, `Browser: ${ua}`].join('\n');
  try {
    await mail(env, `[Daeva Forge] ${kind}: ${msg.slice(0, 60)}`, body, replyTo, 'Daeva Forge feedback');
  } catch (e) {
    return json({error: 'Sending failed. Please try again later.'}, 502);
  }
  return json({ok: true});
}

// The prices' age is Aion2Market's newest capture among all servers (prices/index.json, written by hosting.py).
// The cron runs hourly, so mailing in the hour the prices turn 3 hours old, then every 12 hours, sends one
// message when they go stale and a reminder twice a day while they stay that way, with no state to keep.
const STALE_HOURS = 3, REMIND_HOURS = 12;
async function staleAlarm(env) {
  if (!env.FEEDBACK_TO) return;
  const res = await env.ASSETS.fetch(new Request('https://daevaforge.com/prices/index.json'));
  if (!res.ok) throw new Error(`prices/index.json: ${res.status}`);
  const idx = await res.json(), at = idx.captured || idx.fetched;
  const hours = Math.floor((Date.now() - new Date(at).getTime()) / 36e5);
  if (hours < STALE_HOURS || (hours - STALE_HOURS) % REMIND_HOURS) return;
  await mail(env, `[Daeva Forge] Prices are ${hours} hours old`, [
    `The newest prices on daevaforge.com were captured ${hours} hours ago (${at}).`,
    `Last price run: ${idx.fetched}; ${(idx.kept || []).length} of ${idx.servers.length} servers kept their previous prices.`,
    '',
    'Things to check:',
    `- GitHub Actions, the "prices" workflow: https://github.com/${REPO}/actions/workflows/prices.yml`,
    '- the Worker\'s logs in Cloudflare (a GH_DISPATCH error means the token stopped working)',
    '- whether aion2.exchange itself has new prices',
    '',
    `This repeats every ${REMIND_HOURS} hours while the prices stay old.`,
  ].join('\n'));
}

// Mail to the maintainer (the FEEDBACK_TO secret); the To header shows SHOWN_TO, so Gmail replies from it
async function mail(env, subject, body, replyTo = '', sender = 'Daeva Forge') {
  const one = s => s.replace(/[\r\n]+/g, ' ');  // no header injection
  const raw = [
    `From: ${sender} <${FROM}>`,
    `To: <${SHOWN_TO}>`,
    replyTo ? `Reply-To: <${one(replyTo)}>` : null,
    `Subject: ${mimeWord(one(subject))}`,
    `Message-ID: <${crypto.randomUUID()}@daevaforge.com>`,
    `Date: ${new Date().toUTCString()}`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=utf-8',
    'Content-Transfer-Encoding: base64',
    '',
    b64(body).replace(/.{76}/g, '$&\r\n'),
  ].filter(l => l !== null).join('\r\n');
  await env.FEEDBACK.send(new EmailMessage(FROM, env.FEEDBACK_TO, raw));
}

function b64(s) {
  let bin = '';
  for (const byte of new TextEncoder().encode(s)) bin += String.fromCharCode(byte);
  return btoa(bin);
}
const mimeWord = s => `=?UTF-8?B?${b64(s)}?=`;
const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
