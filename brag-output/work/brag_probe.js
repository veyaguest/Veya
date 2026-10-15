const c = require('./brag_common'); const CAP = '/Users/mac/veya-video-tools/brag/cap';
(async () => {
  const { b, page } = await c.open(c.DESK);
  await page.goto(c.BASE + '/app'); await c.settle(page, 1800);
  await c.shot(page, `${CAP}/wiz_0.png`);
  console.log(await page.evaluate(() => [...document.querySelectorAll('input')].map((i) => i.placeholder || i.type).join(' | ')));
  console.log(await page.evaluate(() => [...document.querySelectorAll('button,[role=radio]')].map((x) => x.innerText.trim()).filter(Boolean).slice(0, 40).join(' | ')));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
