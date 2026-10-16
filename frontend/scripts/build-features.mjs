/**
 * עמודי ה-Feature: /features/rsvp · /features/calls · /features/guests · /features/seating
 *
 * כולם נבנים מהמעטפת המשותפת (`site-shell.mjs`) ומהרכיבים שכבר קיימים
 * בדף הבית: `.why`, `.features` + `.supporting-grid`, `.flow-steps`,
 * `.numcard`/`.numrow`, `.tl-list`/`.tl-item`, `.sc-shot`, `.note-chips`,
 * `.callout`, `.band`. **לא נוצר כאן אף רכיב ויזואלי חדש.**
 *
 * כל טענה בעמודים האלה נבדקה מול הקוד. במיוחד:
 *  · אין הבטחת שליחת WhatsApp — `WHATSAPP_MODE=mock` בייצור.
 *  · אין אזכור של מתנות באשראי.
 *  · "ניהול מוזמנים" אינו מסך נפרד יותר: הרשימה חיה בתוך מרחב ההושבה
 *    (`App.tsx: navItemsFor`), ולכן העמוד מתאר שכבת נתונים ולא פריט ניווט.
 */
import { page, pageHero, heroShot, faqHtml, esc, SITE, CTA_PRIMARY } from './site-shell.mjs'

const CTA_TIMELINE =
  '<a href="/calculators/rsvp-timeline/" class="btn btn-ghost">לראות את לוח הזמנים</a>'

const ic = (p, w = 20) =>
  `<svg width="${w}" height="${w}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`

const P = {
  users: '<circle cx="9" cy="8" r="3"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 6.5a3 3 0 0 1 0 5.8"/><path d="M20.5 20a5.5 5.5 0 0 0-4-5.3"/>',
  chat: '<path d="M4 5h16v11H8l-4 3z"/><path d="m9 10 2 2 4-4"/>',
  chart: '<path d="M4 19V5M4 19h16M8 19v-6M13 19V9M18 19v-9"/>',
  coin: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M14.5 9.8c-.6-.8-1.6-1.2-2.6-1.2-1.4 0-2.4.8-2.4 1.9 0 2.6 5 1.4 5 4 0 1.2-1.1 2-2.6 2-1.1 0-2.1-.4-2.7-1.2"/>',
  table: '<circle cx="7" cy="8" r="2.4"/><circle cx="17" cy="8" r="2.4"/><circle cx="12" cy="17" r="2.4"/><path d="M4 20h16"/>',
  phone: '<path d="M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.5 5.7 2 2 0 0 1 6.5 3.5z"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  note: '<path d="M5.5 3.5h9L19 8v12.5H5.5z"/><path d="M14.5 3.5V8H19"/><path d="M8.5 12.5h7M8.5 16h4.5"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
  up: '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 19h16"/>',
  shield: '<path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.7 7 8.9 4.1-1.2 7-4.7 7-8.9V6z"/><path d="m9 12 2 2 4-4"/>',
  undo: '<path d="M4 9h11a5 5 0 0 1 0 10h-4"/><path d="m8 5-4 4 4 4"/>',
}

/** רצף שלבים אנכי — אותו רכיב `.flow-steps` של דף הבית. */
const flowSteps = (steps) => `          <ol class="flow-steps">
${steps
  .map(
    (s, i) => `            <li class="flow-step${i === steps.length - 1 ? ' flow-step-last' : ''}">
              <span class="flow-dot" aria-hidden="true">${s.icon}</span>
              <div>
                <h3>${esc(s.h)}</h3>
                <p>${esc(s.p)}</p>
              </div>
            </li>`,
  )
  .join('\n')}
          </ol>`

// צילום דסקטופ — תמיד בתוך חלון הדפדפן המשותף (.mk-browser ב-brand layer),
// אותו מוקאפ כמו בדף הבית.
const shot = (src, alt, w = 1600, h = 1000) => `          <div class="sc-shot mk-browser">
            <div class="mk-browser-bar" aria-hidden="true">
              <span class="mk-browser-lights"><i></i><i></i><i></i></span>
              <span class="mk-browser-nav"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3 5 8l5 5" /></svg><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m6 3 5 5-5 5" /></svg></span>
              <span class="mk-browser-url"><svg viewBox="0 0 10 12" fill="currentColor"><path d="M2 5V3.6a3 3 0 0 1 6 0V5h.4c.6 0 1.1.5 1.1 1.1v4.8c0 .6-.5 1.1-1.1 1.1H1.6C1 12 .5 11.5.5 10.9V6.1C.5 5.5 1 5 1.6 5H2Zm1.3 0h3.4V3.6a1.7 1.7 0 0 0-3.4 0V5Z" /></svg><span>veyaguest.co.il/app</span></span>
              <span class="mk-browser-tools"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10V1.8M5.2 4.4 8 1.6l2.8 2.8M5.5 6.5H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1h-1.5" /></svg><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M8 2.5v11M2.5 8h11" /></svg><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><rect x="2" y="4.5" width="9.5" height="9.5" rx="1.6" /><path d="M4.5 2h8a1.5 1.5 0 0 1 1.5 1.5v8" /></svg></span>
            </div>
            <div class="mk-browser-view">
              <img src="${src}" alt="${esc(alt)}" width="${w}" height="${h}" loading="lazy" decoding="async" onerror="veyaRetryImage(this)" />
            </div>
          </div>`

// צילום לאורך — פאנל צר מתוך המוצר, בלי מסגרת דפדפן (.shot-tall).
const shotTall = (src, alt, caption, w, h) => `          <figure class="shot-tall">
            <img src="${src}" alt="${esc(alt)}" width="${w}" height="${h}" loading="lazy" decoding="async" onerror="veyaRetryImage(this)" />
            <figcaption>${esc(caption)}</figcaption>
          </figure>`

/* ════════════════════════════════════════════════════════════════════
   /features/rsvp
   ════════════════════════════════════════════════════════════════════ */

// העיצוב של /features/rsvp בלבד. רעיון אחד מוביל את העמוד: תשובה אחת
// שעוברת דרך כל השרשרת. כל סקשן בפריסה משלו, וכל טענה יושבת ליד הצילום
// האמיתי שמוכיח אותה — בלי אריחי אייקון ובלי כרטיס לבן.
const RSVP_CSS = `    <style>
      .page-hero .hero-media { max-width: 580px; }

      .rv-head { max-width: 640px; margin: 0 0 clamp(40px, 5vw, 64px); }
      .rv-head .section-title { margin-bottom: 14px; }
      .rv-head-wide { max-width: 820px; }
      .rv-sub { color: var(--muted); font-size: var(--t-lead); line-height: 1.65; max-width: 46ch; margin: 0; }
      .rv-fine { font-size: var(--t-small); line-height: 1.7; color: var(--muted); max-width: 60ch; margin: 16px 0 0; }
      .rv-fine a { text-underline-offset: 3px; }
      .rv-shot { margin: 0; }
      .rv-shot img { display: block; width: 100%; height: auto; object-fit: cover; object-position: top; border-radius: 12px; box-shadow: 0 0 0 1px rgba(23, 19, 13, 0.12); }
      .rv-shot figcaption { margin-top: 12px; font-size: var(--t-small); line-height: 1.6; color: var(--muted); }

      /* פתיחה: הרגע הממורכז היחיד בעמוד */
      .rv-open { background: var(--ivory-2); text-align: center; padding: clamp(80px, 10vw, 152px) 0; }
      .rv-open-title {
        font-family: var(--f-display); font-weight: 500; font-size: clamp(2.375rem, 6vw, 5.25rem);
        line-height: 1.04; letter-spacing: -0.02em; color: var(--charcoal);
        max-width: 14ch; margin: 0 auto clamp(28px, 3.4vw, 44px);
      }
      .rv-open-text { font-size: var(--t-lead); line-height: 1.75; max-width: 44ch; margin: 0 auto; }
      .rv-open .rv-open-punch { margin-top: clamp(32px, 4vw, 48px); text-align: center; }

      /* השרשרת: מסילה אחת שהתשובה עוברת בה, ליד הרשימה האמיתית */
      .rv-chain { background: var(--ivory); }
      .rv-chain-body { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); column-gap: var(--col-gap); align-items: start; }
      .rv-rail { list-style: none; margin: 0; padding: 0; }
      .rv-rail li { position: relative; padding: 0 40px 36px 0; }
      .rv-rail li:last-child { padding-bottom: 0; }
      .rv-rail li::before {
        content: ""; position: absolute; right: 0; top: 0.6em; z-index: 1;
        width: 11px; height: 11px; box-sizing: border-box; border-radius: 50%;
        border: 1.5px solid var(--gold); background: var(--ivory);
      }
      .rv-rail li::after {
        content: ""; position: absolute; right: 5px; top: calc(0.6em + 11px); bottom: -0.6em;
        width: 1px; background: color-mix(in oklab, var(--gold) 55%, var(--line));
      }
      .rv-rail li:last-child::after { display: none; }
      .rv-rail li:last-child::before { background: var(--gold); }
      .rv-rail h3 { font-family: var(--f-display); font-weight: 500; font-size: clamp(1.375rem, 2.1vw, 1.75rem); line-height: 1.25; color: var(--charcoal); margin: 0 0 6px; }
      .rv-rail p { margin: 0; max-width: 44ch; }
      .rv-chain .rv-chain-punch { margin: 48px 40px 0 0; }
      .rv-shot-list { position: sticky; top: 104px; justify-self: end; width: 100%; max-width: 400px; }
      .rv-shot-list img { aspect-ratio: 674 / 940; }

      /* ארבעת הסטטוסים: רצועה כהה, הטלפון האמיתי מול הפנקס */
      .rv-status { background: var(--ink); color: var(--on-ink-2); }
      .rv-status .wrap { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 7fr); column-gap: var(--col-gap); align-items: center; }
      .rv-shot-phone { justify-self: start; width: 100%; max-width: 330px; }
      .rv-shot-phone img { aspect-ratio: 780 / 1290; border-radius: 28px; box-shadow: 0 0 0 1px rgba(245, 239, 226, 0.16); }
      .rv-status .rv-shot figcaption { color: var(--on-ink-3); }
      .rv-status .section-title { color: var(--on-ink); margin-bottom: 14px; }
      .rv-status .rv-sub { color: var(--on-ink-2); }
      .rv-ledger { max-width: 620px; margin-top: clamp(32px, 4vw, 44px); border-top: 2px solid var(--on-ink); }
      .rv-ledger-head, .rv-ledger dl > div {
        display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
        border-bottom: 1px solid rgba(245, 239, 226, 0.16);
      }
      .rv-ledger-head { padding: 14px 0; }
      .rv-ledger-head h3 { margin: 0; font-size: 1rem; font-weight: 600; color: var(--on-ink); }
      .rv-ledger-head span { font-size: var(--t-small); color: var(--on-ink-3); }
      .rv-ledger dl { margin: 0; }
      .rv-ledger dl > div { padding: 16px 0; }
      .rv-ledger dt { font-family: var(--f-display); font-size: clamp(1.25rem, 1.8vw, 1.5rem); line-height: 1.3; color: var(--on-ink); }
      .rv-ledger dd { margin: 0; font-weight: 600; color: var(--on-ink-3); }
      .rv-ledger .is-key { position: relative; border-bottom: 0; padding-bottom: 22px; }
      .rv-ledger .is-key::after {
        content: ""; position: absolute; inset-inline: 0; bottom: 0; height: 5px;
        border-top: 1px solid var(--gold); border-bottom: 1px solid var(--gold);
      }
      .rv-ledger .is-key dt, .rv-ledger .is-key dd { color: var(--gold-light); }
      .rv-status-note { max-width: 56ch; margin: 26px 0 0; color: var(--on-ink-2); }
      .rv-status-note b { font-weight: 600; color: var(--on-ink); }
      .rv-status .rv-fine { color: var(--on-ink-3); }
      .rv-status a { color: var(--gold-light); }

      /* לוח הזמנים: המסלול האמיתי מול ארבעת הכללים, ואז מסך ההודעות ברוחב מלא */
      .rv-route { background: var(--ivory); }
      .rv-route-body { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); column-gap: var(--col-gap); align-items: start; }
      .rv-shot-route { order: 2; justify-self: end; width: 100%; max-width: 420px; }
      .rv-shot-route img { aspect-ratio: 1062 / 1300; }
      .rv-rules { margin: 0; border-top: 2px solid var(--charcoal); }
      .rv-rules > div { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); column-gap: 28px; padding: 26px 0; border-bottom: 1px solid var(--line); }
      .rv-rules dt { font-family: var(--f-display); font-weight: 500; font-size: clamp(1.25rem, 1.8vw, 1.5rem); line-height: 1.3; color: var(--charcoal); }
      .rv-rules dd { margin: 0; }
      .rv-wide { margin: clamp(64px, 8vw, 112px) 0 0; }
      .rv-wide .sc-shot { margin: 0; }
      .rv-wide figcaption { margin-top: 14px; font-size: var(--t-small); line-height: 1.6; color: var(--muted); max-width: 70ch; }
      .rv-route-foot { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); column-gap: var(--col-gap); align-items: end; margin-top: clamp(40px, 5vw, 56px); }
      .rv-route-foot .rv-fine { margin: 0; }
      .rv-cta { display: grid; justify-items: end; gap: 10px; }
      .rv-cta .cta-hint { font-size: var(--t-small); color: var(--muted); }

      /* הכסף: פנקס עם שורת סיכום — הקו הכפול יושב מתחת לשורה התחתונה */
      .rv-money { background: var(--ivory-2); }
      .rv-money .rv-money-title { font-size: clamp(2rem, 4.4vw, 3.75rem); line-height: 1.08; max-width: 16ch; margin: 0 0 clamp(40px, 5vw, 64px); }
      .rv-sum { max-width: 980px; margin: 0; }
      .rv-sum > div { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); column-gap: var(--col-gap); align-items: baseline; padding: 22px 0; border-bottom: 1px solid var(--line); }
      .rv-sum > div:first-child { border-top: 1px solid var(--line); }
      .rv-sum dt { font-family: var(--f-display); font-weight: 500; font-size: clamp(1.75rem, 3.2vw, 2.75rem); line-height: 1.1; color: var(--charcoal); }
      .rv-sum dd { margin: 0; font-size: var(--t-lead); line-height: 1.6; }
      .rv-sum .is-total { margin-top: -1px; padding-top: 30px; border-top: 1.5px solid var(--charcoal); border-bottom: 0; }
      .rv-sum .is-total .dbl { margin: 0; padding-bottom: 14px; font-size: inherit; line-height: inherit; }
      .rv-next { margin-top: clamp(44px, 5vw, 64px); }
      .rv-next p { margin: 0 0 8px; color: var(--muted); }
      .rv-next a {
        font-family: var(--f-display); font-size: clamp(1.25rem, 1.9vw, 1.5rem); color: var(--charcoal);
        text-decoration: underline; text-decoration-color: var(--gold); text-decoration-thickness: 1px; text-underline-offset: 7px;
        transition: color 160ms var(--ease-out);
      }
      .rv-next a:hover { color: var(--gold-deep); }

      .faq-wrap { background: var(--ivory); }

      @media (max-width: 900px) {
        .rv-chain-body, .rv-status .wrap, .rv-route-body, .rv-route-foot,
        .rv-rules > div, .rv-sum > div { grid-template-columns: minmax(0, 1fr); }
        .rv-shot-list { position: static; justify-self: stretch; max-width: 440px; margin-top: 56px; }
        .rv-shot-list img { aspect-ratio: 674 / 760; }
        .rv-shot-phone { justify-self: center; max-width: 280px; margin-bottom: 56px; }
        .rv-shot-route { order: 0; justify-self: stretch; max-width: 440px; margin-bottom: 40px; }
        .rv-shot-route img { aspect-ratio: 1062 / 1080; }
        .rv-rules dd, .rv-sum dd { margin-top: 6px; }
        .rv-cta { justify-items: start; margin-top: 28px; }
      }
    </style>
`

// צילום עם כיתוב, בלי מסגרת דפדפן — לפיסות מסך לאורך.
const fig = (cls, src, alt, caption, w, h) => `            <figure class="${cls}">
              <img src="${src}" alt="${esc(alt)}" width="${w}" height="${h}" loading="lazy" decoding="async" onerror="veyaRetryImage(this)" />
              <figcaption>${esc(caption)}</figcaption>
            </figure>`

export function featureRsvp() {
  const faq = [
    {
      q: 'האם "אולי" נספר כמי שמגיע?',
      a: 'לא. רק מוזמן שמסומן "מגיע" נספר כתופס מקום, גם בסידור ההושבה וגם בחישוב העלות. "אולי", "ממתין לתשובה" ו"לא מגיע" נספרים כאפס, כדי שהמספר שתמסרו לאולם לא ינפח את עצמו.',
    },
    {
      q: 'מה קורה למוזמן שאישר ואז ביטל?',
      a: 'הסטטוס מתעדכן והוא מפסיק להיספר. אם הוא כבר שובץ לשולחן הוא נשאר שם, אבל לא נספר כתופס מקום. אם יסמנו אותו "מגיע" שוב, זה חוזר מעצמו.',
    },
    {
      q: 'אפשר לעדכן סטטוס במקום המוזמן?',
      a: 'כן. אפשר לעדכן כל סטטוס ידנית מתוך הרשימה, למשל אחרי שיחה או הודעה שהגיעה בערוץ אחר.',
    },
    {
      q: 'איך יודעים מתי להתחיל?',
      a: 'לוח הזמנים נבנה לאחור מהיום האחרון לאישורי הגעה. זה היום שבו צריך למסור לאולם מספר סופי. אפשר לראות את התאריכים במחשבון לוח הזמנים, בלי להירשם.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'אישורי הגעה',
    h1: 'אישורי הגעה, עד המספר שאפשר לסגור עליו',
    lead: 'כל תשובה נרשמת על המוזמן, וממשיכה משם לבד: לספירה, לסידור ההושבה ולחשבון. ומי שלא ענה מקבל תזכורת, ואם צריך גם טלפון.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'אישורי הגעה' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_TIMELINE}`,
    media: heroShot('/product/rsvp-counts.jpg', 'מסך אישורי ההגעה ב־VEYA: 256 אישרו הגעה, 274 ממתינים לתשובה, 45 לא החליטו ו־69 לא מגיעים, מתוך 644 אנשים שהוזמנו', 'מסך אישורי ההגעה, מתוך אירוע הדמו של VEYA.', 1170, 612),
  })}

      <section class="rv-open">
        <div class="wrap">
          <h2 class="rv-open-title">ה"כן" של המוזמן הוא רק ההתחלה</h2>
          <p class="rv-open-text">
            בטבלה רגילה, מוזמן שענה מקבל וי וזהו. אבל מהתשובה הזו נגזרות ההחלטות
            היקרות של האירוע: כמה מנות, כמה שולחנות, וכמה זה יעלה.
          </p>
          <p class="dbl rv-open-punch">כמה באמת מגיעים זה כמה שולחנות. וזה גם כמה כסף.</p>
        </div>
      </section>

      <section class="rv-chain">
        <div class="wrap">
          <div class="rv-head">
            <h2 class="section-title">התשובה לא נשארת בעמודה שלה</h2>
            <p class="rv-sub">
              אף מספר לא מוקלד פעמיים. כל שלב לוקח את התשובה מהשלב שלפניו.
            </p>
          </div>
          <div class="rv-chain-body">
            <div class="rv-chain-text">
              <ol class="rv-rail">
                <li><h3>מוזמן עונה</h3><p>התשובה נכנסת לשורת המוזמן שלו, כולל כמה אנשים הוא מביא.</p></li>
                <li><h3>הסטטוס מתעדכן</h3><p>מגיע, לא מגיע, אולי או ממתין לתשובה.</p></li>
                <li><h3>תמונת המצב זזה</h3><p>כמה אישרו, כמה ממתינים, וכמה אנשים זה בפועל.</p></li>
                <li><h3>והעלות זזה איתה</h3><p>סעיף שמחושב לפי מספר המגיעים מתעדכן מעצמו.</p></li>
                <li><h3>וסידור ההושבה יודע כמה מקומות צריך</h3><p>רק מי שמסומן "מגיע" נספר כתופס מקום.</p></li>
              </ol>
              <p class="dbl rv-chain-punch">מספר אחד עובר דרך כל השרשרת. לא ארבעה מספרים בארבעה מקומות.</p>
            </div>
${fig('rv-shot rv-shot-list', '/product/seat-panel.jpg', 'רשימת המוזמנים ב־VEYA, ממוינת כך שמי שאישרו הגעה ראשונים: ליד כל מוזמן הסטטוס שלו, מספר האנשים והשולחן', 'רשימת המוזמנים ב־VEYA: ליד כל שם, אם אישר הגעה, כמה אנשים זה, ובאיזה שולחן.', 674, 1130)}
          </div>
        </div>
      </section>

      <section class="rv-status on-dark">
        <div class="wrap">
${fig('rv-shot rv-shot-phone', '/product/dashboard-phone.jpg', 'מסך הבית של VEYA בטלפון: 256 אישרו הגעה, 274 ממתינים לתשובה, 45 לא החליטו ו־69 לא מגיעים, מתוך 644 שהוזמנו', 'תמונת המצב בטלפון, מתוך אירוע הדמו: 256 אישרו הגעה מתוך 644 שהוזמנו.', 780, 1688)}
          <div class="rv-status-text">
            <h2 class="section-title">ארבעה סטטוסים, ומי מהם נספר</h2>
            <p class="rv-sub">נשמע טכני, אבל זה מה שקובע אם המספר שתמסרו לאולם נכון.</p>
            <div class="rv-ledger">
              <div class="rv-ledger-head">
                <h3>מי נספר כתופס מקום</h3>
                <span>בהושבה ובעלות</span>
              </div>
              <dl>
                <div class="is-key"><dt>מגיע</dt><dd>נספר</dd></div>
                <div><dt>אולי</dt><dd>לא נספר</dd></div>
                <div><dt>ממתין לתשובה</dt><dd>לא נספר</dd></div>
                <div><dt>לא מגיע</dt><dd>לא נספר</dd></div>
              </dl>
            </div>
            <p class="rv-status-note">
              <b>"אולי" אינו נספר כמגיע.</b> מוזמן שמתלבט עדיין ברשימת המעקב ועדיין
              אפשר לחזור אליו, אבל הוא לא מנפח את המספר שאתם מוסרים. אם הוא יאשר,
              הוא נכנס לספירה מעצמו.
            </p>
            <p class="rv-fine">
              מוזמן שאישר מביא את מספר האנשים שהוא ציין. אם לא ציין, נספרת הכמות
              שהוזמנה עבורו מלכתחילה, זו שרשומה לו
              <a href="/features/guests/">ברשימת המוזמנים</a>.
            </p>
          </div>
        </div>
      </section>

      <section class="rv-route">
        <div class="wrap">
          <div class="rv-head rv-head-wide">
            <h2 class="section-title">הכול נבנה אחורה מהיום האחרון לאישורי הגעה</h2>
            <p class="rv-sub">
              לא "מתישהו חודש לפני", אלא לאחור מהיום שבו האולם צריך מכם מספר סופי:
              בקשת אישור, שלוש תזכורות ושלושה סבבי מעקב, בלי שישי ושבת.
            </p>
          </div>
          <div class="rv-route-body">
${fig('rv-shot rv-shot-route', '/product/rsvp-route.jpg', 'מסלול אישורי ההגעה ב־VEYA: בקשת אישור, תזכורת, סבב שיחות ראשון ותזכורת שנייה, כל אחד בתאריך שלו', 'מסלול אישורי ההגעה ב־VEYA: כל שלב עם התאריך שלו, ורק למי שעדיין לא אישר.', 1062, 1626)}
            <dl class="rv-rules">
              <div><dt>עוגן אחד</dt><dd>היום האחרון לאישורי הגעה הוא תאריך שאתם קובעים, וכל השלבים נפרסים אחורה ממנו.</dd></div>
              <div><dt>רק למי שעדיין לא ענה</dt><dd>מי שכבר אישר לא מקבל תזכורות. זה מה שמונע מהתהליך להרגיש נודניקי.</dd></div>
              <div><dt>מעקב טלפוני בין השלבים</dt><dd>הסבב האחרון נופל בדיוק ביום האחרון לאישורי הגעה.</dd></div>
              <div><dt>המסלול מתקדם לבד</dt><dd>לא צריך לפתוח מסך כדי שהשלב הבא יקרה. אותו שלב לא חוזר פעמיים לאותו מוזמן, ושלב שהזמן שלו עבר לא מתבצע בדיעבד.</dd></div>
            </dl>
          </div>
          <figure class="rv-wide">
${shot('/product/journey-messages.jpg', 'מסך ההודעות ב-VEYA: כל שלב במסלול הוא הודעה נפרדת, עם תצוגה מקדימה של מה שהמוזמן יראה')}
            <figcaption>
              כל שלב במסלול הוא הודעה נפרדת שאפשר לפתוח, לראות בדיוק איך היא נראית
              אצל המוזמן ולערוך את הנוסח, לפני שהתאריך שלה מגיע.
            </figcaption>
          </figure>
          <div class="rv-route-foot">
            <p class="rv-fine">
              את נוסח ההודעות אפשר לערוך מראש. אם היום האחרון לאישורי הגעה זז, הלוח נבנה
              מחדש מהתאריך החדש, ומה שכבר יצא לא יוצא שוב. בין התזכורות יושבים
              סבבי המעקב הטלפוני: <a href="/features/calls/">מה קורה עם מי שלא ענה</a>.
            </p>
            <div class="rv-cta">
              ${CTA_TIMELINE}
              <span class="cta-hint">מזינים תאריך אירוע ומקבלים את התאריכים בפועל. בלי הרשמה.</span>
            </div>
          </div>
        </div>
      </section>

      <section class="rv-money">
        <div class="wrap">
          <h2 class="section-title rv-money-title">כי מספר המגיעים הוא גם מספר בשקלים</h2>
          <dl class="rv-sum">
            <div><dt>מוזמנים</dt><dd>הרשימה המלאה, כולל כמה אנשים בכל שורה.</dd></div>
            <div><dt>מגיעים</dt><dd>מי שאישר בפועל. זה המספר שממשיך הלאה.</dd></div>
            <div><dt>עלות</dt><dd>כל סעיף שמחושב לפי מספר המגיעים זז עם הרשימה.</dd></div>
            <div class="is-total"><dt><span class="dbl">שורה תחתונה</span></dt><dd>ואחרי האירוע: ההוצאות מול מה שהתקבל.</dd></div>
          </dl>
          <div class="rv-next">
            <p>אחרי שיודעים כמה מגיעים, אפשר לראות מה זה אומר מבחינת העלות.</p>
            <p><a href="/features/finance/">מאזן האירוע: כמה האירוע שלכם באמת עולה <span aria-hidden="true">←</span></a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <h2>בואו נגיע למספר שאפשר לסגור עליו</h2>
            <p class="band-more">
              מתחילים עם רשימת המוזמנים, ומגיעים ליום האחרון לאישורי הגעה עם מספר שאפשר להסביר.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/rsvp/',
    head: RSVP_CSS,
    title: 'אישורי הגעה — מהתשובה עד המספר הסופי | VEYA',
    description:
      'אישורי הגעה ב-VEYA: סטטוס לכל מוזמן, מעקב אחרי מי שלא ענה, ולוח זמנים שנבנה לאחור מהיום האחרון לאישורי הגעה, עד למספר שאפשר למסור לאולם.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'אישורי הגעה' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'אישורי הגעה',
        inLanguage: 'he-IL',
        url: `${SITE}/features/rsvp/`,
        description:
          'ניהול אישורי הגעה: סטטוסים, מעקב אחרי מי שלא ענה, ולוח זמנים שנגזר מהיום האחרון לאישורי הגעה.',
      },
    ],
    body,
  })
}

/* ════════════════════════════════════════════════════════════════════
   /features/calls

   ⚠️ אמת מוצרית: תור השיחות קיים במלואו בקוד (`app/call_center.py`,
   תפקיד `phone_agent`, הקצאת טלפנים בפאנל האדמין), אבל **אין ראיה
   בקוד שהוא נמכר כשירות**. לכן העמוד מתאר מה המערכת מנהלת — ולא
   מבטיח שאנשי VEYA יתקשרו במקומכם ולא מציע שירות בתשלום.
   ════════════════════════════════════════════════════════════════════ */

export function featureCalls() {
  const faq = [
    {
      q: 'מי מתקשר בפועל?',
      a: 'תור המעקב הוא כלי עבודה: הוא בונה את רשימת מי שצריך שיחה, ומי שמבצע אותה מתעד את התוצאה באותה שורת מוזמן. מי מבצע את השיחות בפועל נקבע לפי ההסדר של האירוע שלכם.',
    },
    {
      q: 'למה שלושה סבבים ולא אחד?',
      a: 'כי מי שלא ענה בפעם הראשונה לא בהכרח לא רוצה לענות. הסבבים פרוסים בין התזכורות, והאחרון נופל ביום האחרון לאישורי הגעה, כדי שהניסיון האחרון יקרה לפני שמוסרים מספר.',
    },
    {
      q: 'מה קורה כשמספר טלפון שגוי?',
      a: 'זו לא שיחה שלא הצליחה אלא טעות במספר. המוזמן יוצא מתור השיחות במקום לחזור לסבב הבא עם אותו מספר שגוי, ונפתחת התראה לתיקון המספר ברשימה.',
    },
    {
      q: 'האם השיחה משנה את סטטוס אישור ההגעה?',
      a: 'רק כשיש החלטה. "אישר" ו"לא מגיע" מעדכנים את הסטטוס דרך אותה לוגיקה שרצה כשהמוזמן עונה בעצמו. "לא ענה", "תפוס" ו"ביקש לחזור" לא נוגעים בסטטוס.',
    },
  ]

  const queue = [
    ['דנה כהן', '05X-XXXXXXX', 'ממתין לתשובה', 'סבב שני'],
    ['משפחת לוי', '05X-XXXXXXX', 'ביקש לחזור מאוחר יותר', 'חוזר בתאריך שנבחר'],
    ['אבי מזרחי', '05X-XXXXXXX', 'לא ענה', 'יחזור בסבב הבא'],
    ['רונית שפירא', '05X-XXXXXXX', 'מספר שגוי', 'יצא מהתור · התראה לתיקון'],
    ['יוסי אברהם', '05X-XXXXXXX', 'אישר הגעה', 'ירד מהתור'],
  ]

  const body = `${pageHero({
    eyebrow: 'מעקב אחרי מי שלא ענה',
    h1: 'ומה עם מי שלא ענה?',
    lead: 'יש אנשים שלא עונים להודעות, וזהו. בשבילם יש תור שיחות, על אותה רשימה ועם אותו לוח זמנים.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מעקב טלפוני' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_TIMELINE}`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <h2 class="section-title">בכל רשימה יש קבוצה שפשוט לא עונה</h2>
            <p>
              לא כי הם לא רוצים לבוא. הם ראו את ההודעה, התכוונו לענות אחר כך, ושכחו.
              ככל שמתקרבים למועד שבו צריך למסור מספר, הקבוצה הזו הופכת לפער הגדול
              ביותר בין הרשימה למציאות.
            </p>
            <p class="why-punch">מי שלא ענה לא נעלם. הוא עובר לתור.</p>
          </div>
        </div>
      </section>

      <section class="flow tone-alt">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">הטלפון הוא חלק מהמסלול, לא תוספת</h2>
            <p class="section-sub">
              הוא שלב בתוך אותו תהליך אישורי הגעה, על אותה רשימת מוזמנים.
            </p>
          </div>
${flowSteps([
  { icon: ic(P.chat), h: 'התהליך הדיגיטלי', p: 'בקשת אישור ותזכורות, למי שעדיין לא ענה.' },
  { icon: ic(P.users), h: 'מי שלא השלים תשובה', p: 'נשאר פתוח, בלי סימון של מגיע או לא מגיע.' },
  { icon: ic(P.phone), h: 'תור שיחות', p: 'נגזר מאותו לוח זמנים, בלי רשימה נפרדת.' },
  { icon: ic(P.note), h: 'עדכון סטטוס', p: 'תוצאת השיחה נרשמת על אותה שורת מוזמן.' },
  { icon: ic(P.chart), h: 'מספר סופי', p: 'ביום האחרון לאישורי הגעה, אחרי הסבב האחרון.' },
])}
          <p class="flow-punch">אותה רשימה, אותו לוח זמנים. בלי עוד קובץ של "למי צריך להתקשר".</p>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">מתי מתקשרים</h2>
            <p class="section-sub">
              הסבבים פרוסים בין התזכורות, והאחרון נופל בדיוק
              ביום האחרון לאישורי הגעה.
            </p>
          </div>
          <div class="numcard">
            <div class="numcard-head">
              <h3>מיקום הסבבים בתהליך</h3>
              <span class="numcard-tag">נפרס לאחור</span>
            </div>
            <dl>
              <div class="numrow"><dt>סבב ראשון</dt><dd>אחרי התזכורת הראשונה</dd></div>
              <div class="numrow"><dt>סבב שני</dt><dd>אחרי התזכורת השנייה</dd></div>
              <div class="numrow is-key"><dt>סבב אחרון</dt><dd>ביום האחרון לאישורי הגעה</dd></div>
            </dl>
            <p class="numcard-note">
              כשיש מספיק ימים, כל שלב מקבל יום משלו, ולא מתזמנים שלבים בשישי
              ובשבת. <b>אין סבבים נוספים מעבר לשלושה.</b>
            </p>
          </div>
${shotTall('/product/rsvp-route.jpg', 'מסלול אישורי ההגעה ב־VEYA: בקשת אישור, תזכורת, סבב שיחות ראשון ותזכורת שנייה, כל אחד בתאריך שלו', 'כך זה נראה ב־VEYA: סבב השיחות אינו רשימה נפרדת. הוא שלב בתוך אותו מסלול, עם תאריך משלו.', 1062, 1626)}
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">איך נראית שורה בתור</h2>
            <p class="section-sub">
              רק מי שעדיין פתוח מופיע בתור. מי שאישר, או אמר שלא מגיע, יורד ממנו מעצמו.
            </p>
          </div>
          <div class="numcard" style="max-width:660px">
            <div class="numcard-head">
              <h3>תור מעקב: המחשה</h3>
              <span class="numcard-tag">דוגמה</span>
            </div>
            <ul class="tl-list" style="padding:6px 18px">
${queue
  .map(
    ([name, phone, outcome, effect]) => `              <li class="tl-item">
                <span class="ico" aria-hidden="true">${ic(P.phone, 17)}</span>
                <span class="nm">${esc(name)}<small>${esc(phone)} · ${esc(effect)}</small></span>
                <span class="dt" style="font-size:14px">${esc(outcome)}</span>
              </li>`,
  )
  .join('\n')}
            </ul>
            <p class="numcard-note">
              המספרים בהמחשה מוסתרים בכוונה. תוצאות השיחה האפשריות הן אלה שקיימות
              ב־VEYA: <b>אישר הגעה · לא מגיע · לא ענה · תפוס · מספר שגוי · ביקש לחזור מאוחר יותר</b>.
            </p>
          </div>

          <div class="supporting-grid" style="margin-top:28px">
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.users, 22)}</div>
              <h3>רק מי שפתוח</h3>
              <p>מי שכבר ענה, כן או לא, לא חוזר לתור. לא מתקשרים אליו שוב.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.cal, 22)}</div>
              <h3>"ביקש לחזור" חוזר</h3>
              <p>הוא לא נחשב ניסיון שלא הצליח. הוא חוזר לתור במועד שנבחר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.note, 22)}</div>
              <h3>מספר שגוי הולך לתיקון</h3>
              <p>יוצא מהתור ופותח התראה לתיקון ברשימה, במקום לחזור עם אותו מספר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.chart, 22)}</div>
              <h3>אותה שורת מוזמן</h3>
              <p>תוצאת השיחה מעדכנת את הרשימה מיד. אין קובץ נפרד לעדכן.</p>
            </article>
          </div>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">הטלפון הוא שלב במסלול</p>
            <p>
              הוא נגזר מאותו לוח זמנים של אישורי ההגעה, ומעדכן את אותם סטטוסים.
            </p>
            <p><a href="/features/rsvp/">איך עובדים אישורי ההגעה</a></p>
            <p><a href="/guides/luach-zmanim-ishurey-hagaa/">מתי מתחילים, כמה תזכורות ומה היום האחרון לאישורי הגעה</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <h2>שלא יישאר אף אחד באוויר</h2>
            <p class="band-more">
              מי שלא ענה נשאר על המסך, עם תאריך לסבב הבא, עד שיש תשובה.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/calls/',
    title: 'מעקב אחרי מי שלא אישר הגעה | VEYA',
    description:
      'תור מעקב טלפוני שנגזר מאותו לוח זמנים של אישורי ההגעה: שלושה סבבים, תוצאות שמעדכנות את סטטוס המוזמן, והסבב האחרון ביום האחרון לאישורי הגעה.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מעקב טלפוני' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'מעקב אחרי מי שלא אישר הגעה',
        inLanguage: 'he-IL',
        url: `${SITE}/features/calls/`,
        description: 'תור מעקב טלפוני משולב בתהליך אישורי ההגעה, על אותה רשימת מוזמנים.',
      },
    ],
    body,
  })
}

/* ════════════════════════════════════════════════════════════════════
   /features/guests

   ⚠️ אמת מוצרית: "ניהול מוזמנים" הוא מסך ניווט עצמאי ומקור האמת לפרטי
   המוזמן (Decision Log 2026-09-14); בסידור ההושבה הרשימה פתוחה לצד המפה
   לקריאה ולהושבה בלבד.
   ════════════════════════════════════════════════════════════════════ */

export function featureGuests() {
  const faq = [
    {
      q: 'איפה מנהלים את הרשימה בפועל?',
      a: 'במסך ניהול המוזמנים: שם מוסיפים, עורכים, מייבאים ומשייכים לקבוצות. בסידור ההושבה אותה רשימה פתוחה לצד המפה, כדי להושיב בלי לקפוץ בין מסכים.',
    },
    {
      q: 'מה ההבדל בין מוזמנים לבין מגיעים?',
      a: 'מוזמנים זו הרשימה. מגיעים זה מי שסימן "מגיע", וזה המספר שנספר בסידור ההושבה ובחישוב העלות. "אולי" ו"ממתין לתשובה" נספרים כאפס.',
    },
    {
      q: 'מה קורה להערה שכותבים על מוזמן?',
      a: 'יש שתי שכבות נפרדות: הערה פנימית שנשארת מידע בלבד, והערת הושבה שמזינה את סידור השולחנות. ההפרדה נועדה כדי שהערה תפעולית לא תתפרש בטעות כאילוץ ישיבה.',
    },
    {
      q: 'הקבוצות זהות בכל סוגי האירועים?',
      a: 'לא. הקבוצות משתנות לפי סוג האירוע: לבר מצווה יש משפחת האב, משפחת האם וכיתה, ולאירוע עסקי יש עובדים, לקוחות, ספקים והנהלה.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'רשימת מוזמנים',
    h1: 'רשימת מוזמנים אחת, שכולם עובדים עליה',
    lead: 'הצד, הקבוצה, כמה אנשים בכל שורה, מי אישר, ומה כתבתם על מי. ומשם הכול ממשיך לאישורי ההגעה, לסידור ההושבה ולחשבון.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'רשימת מוזמנים' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_TIMELINE}`,
    media: heroShot('/product/detail-guests-groups.jpg', 'רשימת המוזמנים ב־VEYA: לכל מוזמן שם מלא, צד וקבוצה, כמו משפחה רחוקה, חברים, עבודה וצבא', 'רשימת המוזמנים: לכל שורה צד וקבוצה. מתוך אירוע הדמו.', 638, 672),
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <h2 class="section-title">אקסל לא נשבר כשהוא גדול. הוא נשבר כשיש ממנו שתי גרסאות.</h2>
            <p>
              ברוב האירועים הרשימה חיה בכמה מקומות במקביל: קובץ אחד אצלכם, קובץ אחר
              אצל ההורים, ותיקונים שנאמרו בטלפון. כל אחד מהם נכון בזמן אחר.
            </p>
            <p class="why-punch">בלי "הגרסה של אמא" ו"הגרסה שלנו".</p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">מוזמן הוא לא רק שם וטלפון</h2>
            <p class="section-sub">
              כל שדה כאן משמש בהמשך: באישורי ההגעה, בסידור ההושבה או בחישוב העלות.
            </p>
          </div>
          <div class="numcard" style="max-width:640px">
            <div class="numcard-head">
              <h3>השדות של כל מוזמן</h3>
              <span class="numcard-tag">מה נשמר</span>
            </div>
            <dl>
              <div class="numrow"><dt>שם וטלפון</dt><dd>הבסיס לפנייה</dd></div>
              <div class="numrow is-key"><dt>כמה אנשים בכל שורה</dt><dd>לא כל מוזמן הוא אדם אחד</dd></div>
              <div class="numrow"><dt>צד וקבוצה</dt><dd>משפיעים על סידור ההושבה ועל הפילוח</dd></div>
              <div class="numrow"><dt>סטטוס אישור הגעה</dt><dd>מגיע · לא מגיע · אולי · ממתין</dd></div>
              <div class="numrow"><dt>סימון ילדים</dt><dd>נבדק בהושבה, לא מנוחש</dd></div>
              <div class="numrow"><dt>הערה פנימית</dt><dd>מידע בלבד</dd></div>
              <div class="numrow"><dt>הערת הושבה</dt><dd>מזינה את סידור השולחנות</dd></div>
            </dl>
            <p class="numcard-note">
              <b>כמה אנשים בכל שורה</b> הוא השדה שהכי קל לפספס: "משפחת כהן" יכולה להיות
              שורה אחת וחמישה מקומות ישיבה. מי שסופר שורות במקום אנשים מוסר לאולם
              מספר לא מדויק.
            </p>
          </div>
${shot('/product/journey-guests.jpg', 'טבלת המוזמנים ב-VEYA: שם, כמות, צד, קבוצה וסטטוס אישור הגעה')}
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">קבוצות שמתאימות לסוג האירוע</h2>
            <p class="section-sub">
              הקבוצות אינן תווית בלבד. הן מזינות את הסינון, את הפילוח ואת סידור ההושבה.
              והן משתנות לפי סוג האירוע, לא נשארות חתונתיות תמיד.
            </p>
          </div>
          <div class="evt-grid" style="max-width:860px;margin:0 auto">
            <a class="evt-card" href="/events/wedding/"><h3>חתונה</h3><p>משפחה קרובה, משפחה רחוקה, חברים, עבודה, צבא, לימודים, שכנים.</p></a>
            <a class="evt-card" href="/events/bar-mitzvah/"><h3>בר / בת מצווה</h3><p>משפחת האב, משפחת האם, כיתה, צוות וחוגים.</p></a>
            <a class="evt-card" href="/events/business/"><h3>אירוע עסקי</h3><p>עובדים, לקוחות, ספקים, הנהלה ושותפים. וגם המילה משתנה ל"משתתפים".</p></a>
          </div>
        </div>
      </section>

      <section class="rsvp-band tone-alt">
        <div class="wrap">
          <div class="rsvp-inner">
            <h2 class="section-title">בין הרשימה לבין המספר יש הפרש</h2>
            <p>
              זה ההפרש שקובע כמה שולחנות לפתוח וכמה מנות למסור לאולם:
            </p>
            <ul class="rsvp-list">
              <li><strong>מוזמנים:</strong> כל מי שברשימה, לפי מספר האנשים בכל שורה.</li>
              <li><strong>ממתינים:</strong> עדיין לא ענו. לא נספרים.</li>
              <li><strong>אולי:</strong> ענו, אבל לא הכריעו. לא נספרים.</li>
              <li><strong>מגיעים:</strong> אלה שנספרים בסידור ההושבה ובעלות.</li>
            </ul>
            <p class="why-punch">רק "מגיע" תופס מקום. כל השאר נשאר ברשימת המעקב.</p>
          </div>
        </div>
      </section>

      <section class="features tone-light">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">ייבוא הרשימה שלכם</h2>
            <p class="section-sub">
              אם כבר יש רשימה, אין סיבה להקליד אותה מחדש.
            </p>
          </div>
          <div class="supporting-grid">
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.up, 22)}</div>
              <h3>מקובץ</h3>
              <p>מעלים את הקובץ, מתאימים את העמודות, ובודקים תצוגה מקדימה לפני שמייבאים.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.note, 22)}</div>
              <h3>מהדבקה</h3>
              <p>מדביקים מהוואטסאפ או מהפתקים, גם אם הרשימה לא מסודרת בכלל.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.users, 22)}</div>
              <h3>מאנשי הקשר</h3>
              <p>בוחרים מתוך אנשי הקשר במכשיר, בלי להעתיק מספרים ביד.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.shield, 22)}</div>
              <h3>בדיקת תקינות</h3>
              <p>מספרים שנראים שגויים וכפילויות עולים כהתראה, לפני שמתחילים לפנות לאנשים.</p>
            </article>
          </div>
${shot('/product/paste-review.jpg', 'מסך ייבוא מהדבקה ב-VEYA: כל שורה מפוצלת לשם, טלפון, צד, קבוצה וכמות אנשים, עם סימון אילו שורות לייבא', 1682, 1328)}
          <p class="fineprint">
            בהדבקה אין צורך בטבלה מסודרת: השורות מפוצלות לשדות, מה שלא זוהה נשאר
            ריק לתיקון, ואתם מסמנים אילו שורות באמת נכנסות. הייבוא מזהה גם את
            הקבוצות של סוג האירוע שבחרתם: "עובדים" באירוע עסקי, "משפחת האב"
            בבר מצווה.
          </p>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">ומהרשימה ממשיכים לשולחנות</p>
            <p>הקבוצות, הכמויות והערות ההושבה שסידרתם כאן הם בדיוק מה שסידור ההושבה קורא.</p>
            <p><a href="/features/seating/">סידור הושבה: מהרשימה לשולחנות</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <h2>יש לכם רשימה? זה כל מה שצריך כדי להתחיל</h2>
            <p class="band-more">
              מעלים את הרשימה הקיימת וממשיכים משם לאישורי ההגעה, לסידור ההושבה ולחישוב האירוע.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/guests/',
    title: 'ניהול רשימת מוזמנים לאירוע | VEYA',
    description:
      'רשימת המוזמנים כמקור אחד לכל האירוע: כמות אנשים בכל שורה, קבוצות לפי סוג האירוע, סטטוס אישור הגעה, הערות הושבה וייבוא רשימה קיימת.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'רשימת מוזמנים' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'ניהול רשימת מוזמנים',
        inLanguage: 'he-IL',
        url: `${SITE}/features/guests/`,
        description: 'רשימת מוזמנים כשכבת הנתונים של האירוע: קבוצות, כמויות, סטטוסים והערות.',
      },
    ],
    body,
  })
}

/* ════════════════════════════════════════════════════════════════════
   /features/seating

   כל טענה כאן נגזרת מ-`backend/app/seating.py` ומ-`routers/seating.py`:
   חוקים קשיחים/רכים, אזורים, דוח תקינות, ו-undo מבוסס snapshot בשרת.
   ════════════════════════════════════════════════════════════════════ */

export function featureSeating() {
  const faq = [
    {
      q: 'האם VEYA מסדרת את ההושבה במקומי?',
      a: 'היא נותנת נקודת פתיחה. הסידור נבנה לפי מה שסימנתם (קבוצות, צדדים, הערות ואילוצים), ואתם מזיזים ומשנים אותו עד שהוא נראה לכם נכון. המנוע לא "מבין אנשים", הוא עובד לפי מה שאמרתם לו.',
    },
    {
      q: 'מה קורה אם אילוץ לא מסתדר?',
      a: 'אחרי כל הרצה נבדקת התוצאה בפועל: קיבולת שולחנות, זוגות שאסור להושיב יחד, ומי נשאר בלי שולחן. אם יש הפרה של חוק קשיח, שום דבר לא נשמר ואתם מקבלים פירוט מדויק של מה לא הסתדר.',
    },
    {
      q: 'מה בדיוק אומר "לא ליד"?',
      a: 'שהשניים לא יישבו באותו שולחן. שולחן סמוך אינו נחסם. זו הכרעה מכוונת, כי חסימה של שולחנות סמוכים הופכת כמעט כל אולם לבלתי פתיר.',
    },
    {
      q: 'אפשר לבטל סידור שלא אהבתי?',
      a: 'כן. לפני כל הרצה נשמר תצלום של המצב הקודם בשרת, ואפשר לחזור אליו, גם אחרי רענון הדף או מעבר למכשיר אחר.',
    },
    {
      q: 'מי נכנס לסידור?',
      a: 'רק מי שמסומן "מגיע". מוזמן שממתין לתשובה, מתלבט או ביטל אינו נכנס אוטומטית לשולחנות.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'סידור הושבה',
    h1: 'מהרשימה לשולחנות',
    lead: 'אתם יודעים מי לא יושב ליד מי. VEYA זוכרת את זה, ומושיבה בהתאם.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'סידור הושבה' }],
    cta: `${CTA_PRIMARY}\n            <a href="/features/guests/" class="btn btn-ghost">להתחיל מהרשימה</a>`,
    media: heroShot('/product/hall-map.jpg', 'מפת האולם ב־VEYA: שולחנות ממוספרים, ולכל אחד כמה יושבים בו מתוך כמה מקומות', 'מפת האולם באירוע הדמו: לכל שולחן כמה יושבים מתוך כמה מקומות.', 968, 1612, { tall: true }),
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <h2 class="section-title">ההושבה לא קשה כי יש הרבה אנשים. היא קשה כי יש כללים.</h2>
            <p>
              מי יושב עם מי, מי לא יכול לשבת ליד מי, מי צריך להיות רחוק מהרמקול ומי
              ליד הכניסה. את הכללים האלה אתם כבר יודעים. הם פשוט מפוזרים בין פתקים, הודעות
              והזיכרון של מישהו במשפחה.
            </p>
            <p class="why-punch">כותבים את זה פעם אחת, בהערה על המוזמן. משם זה כלל.</p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">הסקיצה שקיבלתם הופכת למפה שאפשר לעבוד עליה</h2>
            <p class="section-sub">
              מעלים את הסקיצה של האולם, מסדרים עליה את השולחנות ומסמנים את האזורים:
              רחבה, בר, כניסה ועמדת התקליטן.
            </p>
          </div>
${shot('/product/journey-seating.jpg', 'עורך מפת האולם ב-VEYA: שולחנות מסודרים על סקיצת האולם ומוזמנים משובצים', 1600, 1215)}
          <p class="fineprint">
            המפה היא לא ציור: VEYA יודעת איפה כל שולחן עומד, אז "רחוק מהרעש"
            ו"ליד הכניסה" הן בקשות שאפשר באמת למלא.
          </p>
          <p class="fineprint">
            לצד המפה פתוחה רשימת המוזמנים שכבר נמצאים אצלכם, עם אישור ההגעה של כל
            אחד. בוחרים מוזמן ומושיבים אותו בשולחן.
          </p>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">"לא ליד עומר", ומה VEYA עושה עם זה</h2>
            <p class="section-sub">
              כותבים כמו שאומרים, בהערת ההושבה של המוזמן. אלה הבקשות ש־VEYA
              מבינה:
            </p>
          </div>

          <div class="note-chips" style="justify-content:center;margin-bottom:26px">
            <span class="note-chip">לא ליד עומר</span>
            <span class="note-chip">לשבת עם משפחת לוי</span>
            <span class="note-chip">רחוק מהרעש</span>
            <span class="note-chip">ליד הכניסה</span>
            <span class="note-chip">ליד הבר</span>
          </div>

          <div class="numcard">
            <div class="numcard-head">
              <h3>מה נשמר בכל מצב</h3>
              <span class="numcard-tag">חוקים</span>
            </div>
            <dl>
              <div class="numrow is-key"><dt>לא לשבת יחד</dt><dd>לעולם לא מופר</dd></div>
              <div class="numrow is-key"><dt>קיבולת השולחן</dt><dd>לעולם לא מופרת</dd></div>
              <div class="numrow"><dt>לשבת עם מישהו מסוים</dt><dd>משקל גבוה</dd></div>
              <div class="numrow"><dt>העדפת אזור</dt><dd>נלקחת בחשבון</dd></div>
              <div class="numrow"><dt>אותה קבוצה / אותו צד</dt><dd>נלקחים בחשבון</dd></div>
            </dl>
            <p class="numcard-note">
              שתי השורות הראשונות הן <b>חוקים קשיחים</b>: אם אי אפשר לקיים אותן, הסידור
              לא נשמר בכלל. השאר הן העדפות ש־VEYA מנסה לכבד כמה שאפשר, ולפעמים הן מתנגשות זו בזו.
            </p>
          </div>
          <p class="fineprint">
            משפחה נשארת יחד: שורת מוזמן אחת יושבת תמיד באותו שולחן, ולא מתפצלת בין שניים.
          </p>
        </div>
      </section>

      <section class="rsvp-band tone-alt">
        <div class="wrap">
          <div class="rsvp-inner">
            <h2 class="section-title">רק מי שמסומן "מגיע" נספר לשולחנות</h2>
            <p>
              זה נשמע מובן מאליו, וזה המקום שבו סידורי הושבה נשברים: אם סופרים גם את
              מי שעדיין לא ענה, פותחים שולחנות שיישארו ריקים. הסטטוס עצמו מגיע
              מ<a href="/features/rsvp/">אישורי ההגעה</a>, באותה רשימה.
            </p>
            <ul class="rsvp-list">
              <li><strong>מגיע:</strong> נכנס לסידור, ותופס את מספר המקומות שהוא הביא.</li>
              <li><strong>ממתין לתשובה:</strong> לא נכנס אוטומטית.</li>
              <li><strong>אולי:</strong> לא נכנס אוטומטית.</li>
              <li><strong>לא מגיע:</strong> לא נכנס.</li>
            </ul>
            <p class="why-punch">אותו מספר בדיוק שמזין את חישוב העלות.</p>
          </div>
        </div>
      </section>

      <section class="features tone-light">
        <div class="wrap">
          <div class="section-head">
            <h2 class="section-title">הסידור נבדק אחרי שנוצר, לא רק לפני</h2>
          </div>
          <div class="supporting-grid">
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.shield, 22)}</div>
              <h3>דוח תקינות</h3>
              <p>סורק את התוצאה בפועל: קיבולת, זוגות אסורים באותו שולחן, ומי נשאר בלי שולחן.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.note, 22)}</div>
              <h3>הפרה = לא נשמר</h3>
              <p>אם חוק קשיח הופר, שום דבר לא נכתב ואתם מקבלים פירוט של מה לא הסתדר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.undo, 22)}</div>
              <h3>חזרה לסידור הקודם</h3>
              <p>תצלום המצב נשמר בשרת לפני כל הרצה, ושורד רענון דף ומעבר מכשיר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.table, 22)}</div>
              <h3>השלמה בלבד</h3>
              <p>אפשר לשבץ רק את מי שעדיין בלי שולחן, בלי לגעת במה שכבר סידרתם.</p>
            </article>
          </div>
          <p class="fineprint">
            אין כאן הבטחה לסידור מושלם. יש הבטחה אחת: מה שסימנתם כחוק קשיח לא ייפרץ
            בשקט. אם אי אפשר לקיים אותו, תדעו על זה.
          </p>
          <p class="fineprint">
            מי שמאשר אחרי שהסידור כבר מוכן נכנס דרך ההשלמה, למקום פנוי בשולחן קיים,
            ולכן כדאי להחליט מראש <a href="/guides/rezerva-be-erua/">כמה רזרבה להשאיר, ואיפה</a>.
          </p>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">המוזמנים מנוהלים במקום אחד, סידור ההושבה במקום אחר, והכול מחובר.</p>
            <p>
              הוספה, עריכה, פרטי קשר וקבוצות נשארים בניהול המוזמנים. בסידור ההושבה
              עובדים עם הרשימה הזו כמו שהיא, ומה שמשתנה בה מופיע כאן מיד.
            </p>
            <p><a href="/features/guests/">ניהול רשימת המוזמנים</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <h2>לא להתחיל את ההושבה שבוע לפני</h2>
            <p class="band-more">
              את החלוקה לקבוצות ואת האילוצים אפשר לסדר הרבה קודם. מה שנשאר לסוף
              זה תיקונים קטנים.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/seating/',
    title: 'סידור הושבה לאירוע — מהרשימה לשולחנות | VEYA',
    description:
      'סידור הושבה שמכיר את הקבוצות, האילוצים ומיקום השולחנות באולם: חוקים קשיחים שלא נפרצים, דוח תקינות אחרי כל הרצה, וחזרה לסידור הקודם.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'סידור הושבה' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'סידור הושבה',
        inLanguage: 'he-IL',
        url: `${SITE}/features/seating/`,
        description: 'סידור הושבה לפי קבוצות, אילוצים ומיקום שולחנות, עם דוח תקינות וביטול.',
      },
    ],
    body,
  })
}
