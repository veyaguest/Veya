// brag film helpers: sharp recordings via new-headless + explicit window size (screencast then honours DPR).
const c = require('./common');
const { chromium } = require('playwright');
const fs = require('fs');
const TOKEN = fs.readFileSync('/Users/mac/veya-video-tools/env/film05.token', 'utf8').trim();
const DESK = { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, ws: '1280,800' };
const MOB = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, ws: '390,844',
  userAgent: c.MOBILE.userAgent };
async function open(dev, { token = TOKEN, eventId = null } = {}) {
  const { ws, ...d } = dev;
  const b = await chromium.launch({ headless: false, args: ['--headless=new', '--window-size=' + ws] });
  const ctx = await b.newContext({ ...d, locale: 'he-IL', timezoneId: 'Asia/Jerusalem', colorScheme: 'light' });
  await ctx.addInitScript(({ token, eventId }) => {
    try {
      localStorage.setItem('veya_cookie_consent', JSON.stringify({ analytics: false, decidedAt: '2026-10-07T00:00:00Z' }));
      localStorage.setItem('veya_install_dismissed_at', String(Date.now()));
      localStorage.setItem('veya_partner_cta_dismissed', '1');
      if (token) localStorage.setItem('veya_token', token);
      if (eventId) localStorage.setItem('veya_event_id', String(eventId));
    } catch (e) {}
  }, { token, eventId });
  // 1px, near-invisible heartbeat: forces a repaint every frame so the CDP screencast keeps a steady rate.
  await ctx.addInitScript(() => { addEventListener('DOMContentLoaded', () => { const h = document.createElement('div');
    Object.assign(h.style, { position: 'fixed', left: '0', top: '0', width: '1px', height: '1px', opacity: '0.004', background: '#000', zIndex: 2147483647, pointerEvents: 'none' });
    document.documentElement.appendChild(h); let k = 0; const f = () => { h.style.transform = `translateX(${(k++ % 2)}px)`; requestAnimationFrame(f); }; f(); }); });
  const page = await ctx.newPage();
  return { b, ctx, page };
}
module.exports = { ...c, open, DESK, MOB, TOKEN };
