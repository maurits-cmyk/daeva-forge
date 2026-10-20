// Daeva Forge on Cloudflare: the files in dist/ are served as static assets (they never reach this code);
// the one dynamic route, POST /api/feedback, emails a visitor's message to the maintainer.
import { EmailMessage } from 'cloudflare:email';

const FROM = 'feedback@daevaforge.com';       // Email Routing must be on for daevaforge.com
const SHOWN_TO = 'mawreez@daevaforge.com';     // the To header Gmail sees, so it replies from this address
const KINDS = ['Bug', 'Idea', 'Other'];

// The inbox is the Worker secret FEEDBACK_TO (kept out of this public repo); it must be a verified
// Email Routing destination address, the only kind the send_email binding can deliver to.
export default {
  async fetch(req, env) {
    if (new URL(req.url).pathname === '/api/feedback') {
      return req.method === 'POST' ? feedback(req, env) : json({error: 'Use POST.'}, 405);
    }
    return env.ASSETS.fetch(req);
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
  const one = s => s.replace(/[\r\n]+/g, ' ');  // no header injection
  const raw = [
    `From: Daeva Forge feedback <${FROM}>`,
    `To: <${SHOWN_TO}>`,
    replyTo ? `Reply-To: <${one(replyTo)}>` : null,
    `Subject: ${mimeWord(one(`[Daeva Forge] ${kind}: ${msg.slice(0, 60)}`))}`,
    `Message-ID: <${crypto.randomUUID()}@daevaforge.com>`,
    `Date: ${new Date().toUTCString()}`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=utf-8',
    'Content-Transfer-Encoding: base64',
    '',
    b64(body).replace(/.{76}/g, '$&\r\n'),
  ].filter(l => l !== null).join('\r\n');
  try {
    await env.FEEDBACK.send(new EmailMessage(FROM, env.FEEDBACK_TO, raw));
  } catch (e) {
    return json({error: 'Sending failed. Please try again later.'}, 502);
  }
  return json({ok: true});
}

function b64(s) {
  let bin = '';
  for (const byte of new TextEncoder().encode(s)) bin += String.fromCharCode(byte);
  return btoa(bin);
}
const mimeWord = s => `=?UTF-8?B?${b64(s)}?=`;
const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
