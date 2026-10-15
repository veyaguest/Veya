// REC A (desktop @2x): empty event → paste the WhatsApp list → review → import → full guest list.
const c = require('./brag_common'); const fs = require('fs'); const path = require('path');
const CAP = '/Users/mac/veya-video-tools/brag/cap', REC = '/Users/mac/veya-video-tools/brag/rec';
const LIST = fs.readFileSync('/Users/mac/veya-video-tools/env/paste_list_brag_284.txt', 'utf8');
async function smoothScroll(page, dy, ms = 1200) {
  await page.evaluate(async ({ dy, ms }) => { const s = scrollY, t0 = performance.now();
    await new Promise((res) => { const f = (t) => { const k = Math.min(1, (t - t0) / ms); const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      scrollTo(0, s + dy * e); k < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); }); }, { dy, ms });
}
(async () => {
  const { b, page } = await c.open(c.DESK, { eventId: 21566 });
  await c.installCursor(page);
  await page.goto(c.BASE + '/app/guests'); await c.settle(page, 2000);
  await page.mouse.move(640, 600);
  await c.shot(page, `${CAP}/pA_0.png`);
  const rec = await c.startRecording(page, 'A_paste', REC);
  await page.waitForTimeout(900);
  await c.glideClick(page, page.getByRole('button', { name: 'ייבוא מוזמנים' }).first()); await page.waitForTimeout(700);
  await c.glideClick(page, page.getByText('הדבקה מרשימה קיימת').first()); await page.waitForTimeout(1000);
  await c.glideClick(page, page.locator('textarea').first()); await page.waitForTimeout(500);
  await page.locator('textarea').first().fill(LIST); await page.locator('textarea').first().evaluate((t) => { t.scrollTop = 0; t.setSelectionRange(0, 0); }); await page.waitForTimeout(1800);
  await c.glideClick(page, page.getByRole('button', { name: 'פענוח הרשימה' })); await c.settle(page, 1200);
  await page.waitForTimeout(1500);
  await c.shot(page, `${CAP}/pA_review.png`);
  const importBtn = page.getByRole('button', { name: /^ייבוא \d+ מוזמנים$/ });
  console.log('import button:', await importBtn.innerText());
  await c.glideClick(page, importBtn); await c.settle(page, 1800);
  await page.waitForTimeout(1400);
  await smoothScroll(page, 700, 2600); await page.waitForTimeout(900);
  const res = await rec.stop(30);
  console.log(res);
  await c.shot(page, `${CAP}/pA_after.png`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
