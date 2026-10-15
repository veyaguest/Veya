process.env.PLAYWRIGHT_BROWSERS_PATH = '/Users/mac/veya-video-tools/browsers';
const { chromium } = require('/Users/mac/veya-video-tools/node_modules/playwright');
const fs = require('fs'); const path = require('path');
const OUT = process.argv[2]; const mode = process.argv[3] || 'full'; const FPS = 30, DUR = 24.0;
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch({ headless: true, args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  p.on('pageerror', (e) => console.error('PAGEERR', e.message));
  await p.goto('file://' + path.resolve(__dirname, 'film.html'));
  await p.evaluate(() => window.ready);
  const times = mode === 'full' ? [...Array(Math.round(DUR * FPS)).keys()].map((i) => i / FPS) : mode.split(',').map(Number);
  for (let i = 0; i < times.length; i++) {
    await p.evaluate((t) => window.renderAt(t), times[i]);
    const name = mode === 'full' ? String(i).padStart(5, '0') + '.jpg' : `t_${times[i].toFixed(2)}.jpg`;
    await p.screenshot({ path: path.join(OUT, name), type: 'jpeg', quality: 93 });
    if (mode === 'full' && i % 120 === 0) console.log('frame', i, '/', times.length);
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
