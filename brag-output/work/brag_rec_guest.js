// REC B again: guest confirms on the phone. No pointer overlay; a 1px invisible heartbeat keeps the screencast at a steady frame rate.
const c = require('./brag_common'); const fs = require('fs');
const CAP = '/Users/mac/veya-video-tools/brag/cap', REC = '/Users/mac/veya-video-tools/brag/rec';
const TOK = process.argv[2];
(async () => {
  const g = await c.open(c.MOB, { token: null });
  await g.page.addInitScript(() => { addEventListener('DOMContentLoaded', () => { const h = document.createElement('div');
    Object.assign(h.style, { position: 'fixed', left: '0', top: '0', width: '1px', height: '1px', opacity: '0.004', background: '#000', zIndex: 2147483647, pointerEvents: 'none' });
    document.documentElement.appendChild(h); let k = 0; const f = () => { h.style.transform = `translateX(${(k++ % 2)}px)`; requestAnimationFrame(f); }; f(); }); });
  await g.page.goto(c.BASE + '/confirm/' + TOK); await c.settle(g.page, 2000);
  const rec = await c.startRecording(g.page, 'B_guest_confirms', REC);
  await g.page.waitForTimeout(1600);
  const yes = g.page.getByRole('button', { name: /מגיעים/ }).first(); const bb = await yes.boundingBox();
  fs.writeFileSync(`${CAP}/B_taps.json`, JSON.stringify({ yes: bb }));
  await yes.tap(); await g.page.waitForTimeout(1500);
  const send = g.page.getByRole('button', { name: 'שליחת אישור' }); const sb = await send.boundingBox();
  await send.scrollIntoViewIfNeeded(); const sb2 = await send.boundingBox();
  fs.writeFileSync(`${CAP}/B_taps.json`, JSON.stringify({ yes: bb, send: sb2 }));
  await g.page.waitForTimeout(500);
  await send.tap(); await c.settle(g.page, 1200); await g.page.waitForTimeout(2200);
  console.log(await rec.stop(30), fs.readFileSync(`${CAP}/B_taps.json`, 'utf8'));
  await g.b.close();
})().catch((e) => { console.error(e); process.exit(1); });
