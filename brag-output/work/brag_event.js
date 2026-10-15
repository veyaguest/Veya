const c = require('./brag_common'); const CAP = '/Users/mac/veya-video-tools/brag/cap';
(async () => {
  const { b, page } = await c.open(c.DESK);
  await page.goto(c.BASE + '/app'); await c.settle(page, 1800);
  await page.getByLabel('שם החתן').fill('עידו'); await page.getByLabel('שם הכלה').fill('תמר'); await page.getByLabel('שם האולם').fill('גן האירועים בעמק');
  await page.locator('input[type=date]').first().fill('2026-11-19');
  await page.waitForTimeout(400); await c.shot(page, `${CAP}/wiz_1.png`, { fullPage: true });
  await page.getByRole('button', { name: 'שמירה והמשך' }).click(); await c.settle(page, 1500);
  for (let i = 0; i < 4; i++) {
    await c.shot(page, `${CAP}/wiz_step${i + 2}.png`);
    const btns = await page.evaluate(() => [...document.querySelectorAll('button')].map((x) => x.innerText.trim()).filter(Boolean));
    console.log('step', i + 2, btns.slice(0, 25).join(' | '));
    const skip = page.getByRole('button', { name: /מאוחר יותר|דילוג|אחר כך|לדשבורד|סיום/ }).first();
    if (await skip.count()) { await skip.click(); await c.settle(page, 1400); } else break;
  }
  const ev = await page.evaluate(() => localStorage.getItem('veya_event_id')); console.log('event id', ev, page.url());
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
