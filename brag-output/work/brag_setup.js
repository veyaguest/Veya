// /brag-slim launch film — fresh demo account + event in the ISOLATED video env only (:5210 → :8050 → env/video.db).
const c = require('./common');
const fs = require('fs'); const path = require('path'); const crypto = require('crypto');
const ENV = '/Users/mac/veya-video-tools/env'; const CAP = '/Users/mac/veya-video-tools/brag/cap';
(async () => {
  let token;
  const tf = `${ENV}/film05.token`;
  if (fs.existsSync(tf)) token = fs.readFileSync(tf, 'utf8').trim();
  else {
    const pw = 'Film05-' + crypto.randomBytes(12).toString('base64url');
    const r = await fetch(`${c.API}/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'film05@veya.local', password: pw, display_name: 'תמר', phone: '0500000995', accepted_terms: true }) });
    const d = await r.json(); if (!r.ok) throw new Error(JSON.stringify(d));
    token = d.access_token; fs.writeFileSync(tf, token); fs.writeFileSync(`${ENV}/film05_register.json`, JSON.stringify(d, null, 1));
    fs.appendFileSync(`${ENV}/test_account.txt`, `film05@veya.local\t${pw}\n`);
    console.log('registered user', d.user.id);
  }
  const b = await c.launch();
  const ctx = await c.newContext(b, c.DESKTOP, { auth: false });
  await ctx.addInitScript((t) => { localStorage.setItem('veya_token', t); localStorage.removeItem('veya_event_id'); }, token);
  const page = await ctx.newPage();
  await page.goto(c.BASE + '/app'); await c.settle(page, 1800);
  await c.shot(page, `${CAP}/setup_0.png`);
  // screencast resolution probe
  const cdp = await ctx.newCDPSession(page); let probe = null;
  cdp.on('Page.screencastFrame', async (f) => { if (!probe) probe = Buffer.from(f.data, 'base64'); try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {} });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 3200, maxHeight: 2000, everyNthFrame: 1 });
  await page.mouse.move(300, 300); await page.waitForTimeout(800); await cdp.send('Page.stopScreencast');
  if (probe) fs.writeFileSync(`${CAP}/probe.jpg`, probe);
  console.log(await page.evaluate(() => [...document.querySelectorAll('input')].map((i) => i.placeholder || i.type).join(' | ')));
  console.log(await page.evaluate(() => [...document.querySelectorAll('button')].map((x) => x.innerText.trim()).filter(Boolean).slice(0, 30).join(' | ')));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
