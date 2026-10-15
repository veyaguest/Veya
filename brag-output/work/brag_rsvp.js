// REC B (guest phone confirms) + RSVP states after each wave (owner phone) + REC C (dashboard gauge).
// All answers go through the REAL public confirm endpoint of the isolated video backend.
const c = require('./brag_common'); const fs = require('fs'); const path = require('path');
const { execFileSync } = require('child_process');
const CAP = '/Users/mac/veya-video-tools/brag/cap', REC = '/Users/mac/veya-video-tools/brag/rec', ST = '/Users/mac/veya-video-tools/brag/states';
fs.mkdirSync(ST, { recursive: true });
const EV = 21566, DB = '/Users/mac/veya-video-tools/env/video.db';
const rows = execFileSync('sqlite3', ['-separator', '\t', DB, `select guest_token, full_name, party_size from guests where event_id=${EV} order by id`]).toString().trim().split('\n').map((l) => { const [t, n, p] = l.split('\t'); return { t, n, p: +p }; });
let seed = 1119; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
for (const g of rows) { const r = rnd(); g.final = r < .70 ? 'confirmed' : r < .77 ? 'declined' : r < .83 ? 'maybe' : 'pending'; }
const star = rows.find((g) => g.n === 'נועה שלום'); star.final = 'confirmed';
const answer = rows.filter((g) => g.final !== 'pending' && g !== star).sort(() => rnd() - .5);
const SIZES = [12, 20, 26, 30, 32, 30, 28, 26];
const waves = []; let i = 0; for (const s of SIZES) { waves.push(answer.slice(i, i + s)); i += s; } waves[waves.length - 1].push(...answer.slice(i));
async function confirm(g) {
  const body = g.final === 'confirmed' ? { coming: true, count: g.p } : g.final === 'maybe' ? { coming: false, maybe: true } : { coming: false };
  const r = await fetch(`${c.API}/confirm/${encodeURIComponent(g.t)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`confirm ${r.status} ${await r.text()}`);
}
async function stats() {
  const r = await fetch(`${c.API}/stats`, { headers: { Authorization: `Bearer ${c.TOKEN}`, 'X-Event-Id': String(EV) } }); const d = await r.json();
  return { people: d.total_people, confirmed: d.confirmed_people, pending: d.pending_people, maybe: d.maybe_people, declined: d.declined_people };
}
async function smoothScroll(page, dy, ms = 1200) {
  await page.evaluate(async ({ dy, ms }) => { const s = scrollY, t0 = performance.now();
    await new Promise((res) => { const f = (t) => { const k = Math.min(1, (t - t0) / ms); const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      scrollTo(0, s + dy * e); k < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); }); }, { dy, ms });
}
const step = process.argv[2] || 'all';
(async () => {
  const log = [];
  // owner phone (stills @3x)
  const own = await c.open({ ...c.MOB, ws: '390,844' }, { eventId: EV });
  async function snap(k) {
    await own.page.goto(c.BASE + '/app/rsvp'); await c.settle(own.page, 1500);
    await c.shot(own.page, path.join(ST, `rsvp_${String(k).padStart(2, '0')}.png`));
    const s = await stats(); log.push({ state: k, ...s }); console.log(JSON.stringify(log[log.length - 1]));
  }
  await snap(0);
  // REC B — guest confirms on the phone (no pointer overlay; tap positions saved for the edit)
  const gst = await c.open(c.MOB, { token: null });
  await gst.page.goto(c.BASE + '/confirm/' + star.t); await c.settle(gst.page, 2000);
  const recB = await c.startRecording(gst.page, 'B_guest_confirms', REC);
  await gst.page.waitForTimeout(1600);
  const yes = gst.page.getByRole('button', { name: /מגיעים/ }).first(); const yb = await yes.boundingBox();
  await yes.tap(); await gst.page.waitForTimeout(1500);
  const send = gst.page.getByRole('button', { name: 'שליחת אישור' }); await send.scrollIntoViewIfNeeded(); const sb = await send.boundingBox();
  await gst.page.waitForTimeout(500);
  await send.tap(); await c.settle(gst.page, 1200); await gst.page.waitForTimeout(2200);
  console.log('B', await recB.stop(30));
  fs.writeFileSync(`${CAP}/B_taps.json`, JSON.stringify({ yes: yb, send: sb }));
  await gst.b.close();
  await snap(1);
  for (let w = 0; w < waves.length; w++) { for (const g of waves[w]) await confirm(g); await snap(w + 2); }
  fs.writeFileSync(path.join(ST, 'states.json'), JSON.stringify(log, null, 1));
  await own.b.close();
  // REC C — the couple opens "תמונת מצב" on the phone after the waves
  const dash = await c.open(c.MOB, { eventId: EV });
  const recC = await c.startRecording(dash.page, 'C_dashboard', REC);
  await dash.page.goto(c.BASE + '/app'); await c.settle(dash.page, 2200); await dash.page.waitForTimeout(1500);
  await smoothScroll(dash.page, 380, 1500); await dash.page.waitForTimeout(1200);
  console.log('C', await recC.stop(30));
  await dash.b.close();
})().catch((e) => { console.error(e); process.exit(1); });
