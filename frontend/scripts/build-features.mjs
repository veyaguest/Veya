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
import { page, pageHero, faqHtml, esc, SITE, CTA_PRIMARY } from './site-shell.mjs'

const CTA_TIMELINE =
  '<a href="/calculators/rsvp-timeline/" class="btn btn-ghost">לראות את לוח הזמנים</a>'
const CTA_COMMIT =
  '<a href="/calculators/venue-commitment/" class="btn btn-ghost">לחשב את ההתחייבות</a>'

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

const shot = (src, alt) => `          <div class="sc-shot">
            <img src="${src}" alt="${esc(alt)}" width="1400" height="875" loading="lazy" decoding="async" onerror="this.closest('.sc-shot').remove()" />
          </div>`

/* ════════════════════════════════════════════════════════════════════
   /features/rsvp
   ════════════════════════════════════════════════════════════════════ */

export function featureRsvp() {
  const faq = [
    {
      q: 'האם "אולי" נספר כמי שמגיע?',
      a: 'לא. רק מוזמן שמסומן "מגיע" נספר כתופס מקום — בהושבה ובחישוב העלות כאחד. "אולי", "ממתין לתשובה" ו"לא מגיע" נספרים כאפס, כדי שהמספר שתמסרו לאולם לא ינפח את עצמו.',
    },
    {
      q: 'מה קורה למוזמן שאישר ואז ביטל?',
      a: 'הסטטוס מתעדכן והוא מפסיק להיספר. אם הוא כבר שובץ לשולחן הוא נשאר שם, אבל לא נספר כתופס מקום — ואם יסמנו אותו "מגיע" שוב, זה חוזר מעצמו.',
    },
    {
      q: 'אפשר לעדכן סטטוס במקום המוזמן?',
      a: 'כן. אפשר לעדכן כל סטטוס ידנית מתוך הרשימה, למשל אחרי שיחה או הודעה שהגיעה בערוץ אחר.',
    },
    {
      q: 'איך יודעים מתי להתחיל?',
      a: 'לוח הזמנים נבנה לאחור ממועד סגירת הרשימה — היום שבו צריך למסור לאולם מספר סופי. אפשר לראות את התאריכים במחשבון לוח הזמנים, בלי להירשם.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'אישורי הגעה',
    h1: 'אישורי הגעה שלא נעצרים בתשובה',
    lead: 'VEYA מרכזת את אישורי ההגעה, המעקב והסטטוסים כדי שתדעו מה מצב הרשימה — ומה המשמעות שלו להמשך האירוע.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'אישורי הגעה' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_TIMELINE}`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">הזווית</span>
            <h2 class="section-title">אישור הגעה הוא לא סוף התהליך. הוא ההתחלה של ההחלטות.</h2>
            <p>
              ברוב הכלים, ברגע שמוזמן ענה — הסיפור נגמר. הוא מקבל וי בטבלה, והטבלה
              ממשיכה לגדול. אבל התשובה הזו היא בדיוק הנתון שממנו נגזרות ההחלטות
              היקרות של האירוע.
            </p>
            <p class="why-punch">כמה אנשים באמת מגיעים — זה גם כמה שולחנות, וגם כמה זה עולה.</p>
          </div>
        </div>
      </section>

      <section class="flow tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">מה קורה אחרי שמוזמן עונה</span>
            <h2 class="section-title">התשובה לא נשארת בעמודה שלה</h2>
            <p class="section-sub">
              כל שלב כאן נשען על אותו נתון של השלב שלפניו — לא על מספר שהוזן מחדש.
            </p>
          </div>
${flowSteps([
  { icon: ic(P.users), h: 'מוזמן עונה', p: 'התשובה נכנסת לשורת המוזמן שלו, כולל כמה אנשים הוא מביא.' },
  { icon: ic(P.chat), h: 'הסטטוס מתעדכן', p: 'מגיע, לא מגיע, אולי או ממתין לתשובה.' },
  { icon: ic(P.chart), h: 'תמונת המצב זזה', p: 'כמה אישרו, כמה ממתינים, וכמה אנשים זה בפועל.' },
  { icon: ic(P.coin), h: 'ההתחייבות והעלות זזות איתה', p: 'סעיף שמחושב לפי מספר המגיעים מתעדכן מעצמו.' },
  { icon: ic(P.table), h: 'וההושבה יודעת כמה מקומות צריך', p: 'רק מי שמסומן "מגיע" נספר כתופס מקום.' },
])}
          <p class="flow-punch">מספר אחד עובר דרך כל השרשרת. לא ארבעה מספרים בארבעה מקומות.</p>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">סטטוסים</span>
            <h2 class="section-title">ארבעה סטטוסים, ומי מהם נספר</h2>
            <p class="section-sub">
              ההבחנה הזו נשמעת טכנית, והיא זו שקובעת אם המספר שתמסרו לאולם נכון.
            </p>
          </div>
          <div class="numcard">
            <div class="numcard-head">
              <h3>מי נספר כתופס מקום</h3>
              <span class="numcard-tag">בהושבה ובעלות</span>
            </div>
            <dl>
              <div class="numrow is-key"><dt>מגיע</dt><dd>נספר</dd></div>
              <div class="numrow"><dt>אולי</dt><dd>לא נספר</dd></div>
              <div class="numrow"><dt>ממתין לתשובה</dt><dd>לא נספר</dd></div>
              <div class="numrow"><dt>לא מגיע</dt><dd>לא נספר</dd></div>
            </dl>
            <p class="numcard-note">
              <b>"אולי" אינו נספר כמגיע.</b> מוזמן שמתלבט עדיין ברשימת המעקב ועדיין
              אפשר לחזור אליו — אבל הוא לא מנפח את המספר שאתם מוסרים. אם הוא יאשר,
              הוא נכנס לספירה מעצמו.
            </p>
          </div>
          <p class="fineprint">
            מוזמן שאישר מביא את מספר האנשים שהוא ציין. אם לא ציין — נספרת הכמות
            שהוזמנה עבורו מלכתחילה.
          </p>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">לוח הזמנים</span>
            <h2 class="section-title">התהליך נבנה ביחס למועד סגירת הרשימה</h2>
            <p class="section-sub">
              לא "מתישהו חודש לפני", אלא לאחור מהיום שבו האולם צריך מכם מספר סופי:
              בקשת אישור, שלוש תזכורות ושלושה סבבי מעקב, בלי שישי ושבת.
            </p>
          </div>
          <div class="supporting-grid">
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.cal, 22)}</div>
              <h3>עוגן אחד</h3>
              <p>מועד סגירת הרשימה נקבע בפתיחת האירוע, וכל השלבים נפרסים אחורה ממנו.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.chat, 22)}</div>
              <h3>רק למי שעדיין לא ענה</h3>
              <p>מי שכבר אישר לא מקבל תזכורות. זה מה שמונע מהתהליך להרגיש נודניקי.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.phone, 22)}</div>
              <h3>מעקב טלפוני בין השלבים</h3>
              <p>הסבב האחרון נופל בדיוק על מועד סגירת הרשימה.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.shield, 22)}</div>
              <h3>שום דבר לא יוצא לבד</h3>
              <p>מה שאמור להישלח מופיע כתור לאישור, ואתם מאשרים לפני שהוא יוצא.</p>
            </article>
          </div>
          <div class="section-cta">
            ${CTA_TIMELINE}
            <span class="cta-hint">מזינים תאריך אירוע ומקבלים את התאריכים בפועל. בלי הרשמה.</span>
          </div>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">החיבור לכסף</span>
            <h2 class="section-title">כי מספר המגיעים הוא גם מספר כספי</h2>
          </div>
${flowSteps([
  { icon: ic(P.users), h: 'מוזמנים', p: 'הרשימה המלאה, כולל כמה אנשים בכל רשומה.' },
  { icon: ic(P.chat), h: 'מגיעים', p: 'מי שאישר בפועל — וזה המספר שממשיך הלאה.' },
  { icon: ic(P.cal), h: 'התחייבות', p: 'מחייבים אתכם על הגבוה מבין המגיעים לכמות שבחוזה.' },
  { icon: ic(P.coin), h: 'עלות', p: 'כל סעיף שמחושב לפי מספר המגיעים זז עם הרשימה.' },
  { icon: ic(P.chart), h: 'שורה תחתונה', p: 'ואחרי האירוע — ההוצאות מול מה שהתקבל.' },
])}
          <div class="callout" style="max-width:620px;margin-inline:auto">
            <p>
              אחרי שיודעים כמה מגיעים, אפשר לראות מה זה אומר מבחינת ההתחייבות והעלות.
            </p>
            <p><a href="/features/finance/">מאזן האירוע — כמה האירוע שלכם באמת עולה</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>מרשימה שמשתנה כל יום — לתמונה אחת</h2>
            <p class="band-more">
              מתחילים עם רשימת המוזמנים, ומגיעים למועד סגירת הרשימה עם מספר שאפשר להסביר.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/rsvp/',
    title: 'אישורי הגעה — מהתשובה עד המספר הסופי | VEYA',
    description:
      'אישורי הגעה ב-VEYA: סטטוס לכל מוזמן, מעקב אחרי מי שלא ענה, ולוח זמנים שנבנה לאחור ממועד סגירת הרשימה — עד למספר שאפשר למסור לאולם.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'אישורי הגעה' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'אישורי הגעה',
        inLanguage: 'he-IL',
        url: `${SITE}/features/rsvp/`,
        description:
          'ניהול אישורי הגעה: סטטוסים, מעקב אחרי מי שלא ענה, ולוח זמנים שנגזר ממועד סגירת הרשימה.',
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
      a: 'כי מי שלא ענה בפעם הראשונה לא בהכרח לא רוצה לענות. הסבבים פרוסים בין התזכורות, והאחרון נופל על מועד סגירת הרשימה — כדי שהניסיון האחרון יקרה לפני שמוסרים מספר.',
    },
    {
      q: 'מה קורה כשמספר טלפון שגוי?',
      a: 'זו לא שיחה שנכשלה אלא תקלת דאטה. המוזמן יוצא מתור השיחות במקום לחזור לסבב הבא עם אותו מספר שגוי, ונפתחת התראה לתיקון המספר ברשימה.',
    },
    {
      q: 'האם השיחה משנה את סטטוס אישור ההגעה?',
      a: 'רק כשיש החלטה. "אישר" ו"לא מגיע" מעדכנים את הסטטוס דרך אותה לוגיקה שרצה כשהמוזמן עונה בעצמו. "לא ענה", "תפוס" ו"ביקש לחזור" לא נוגעים בסטטוס.',
    },
  ]

  const queue = [
    ['דנה כהן', '05X-XXXXXXX', 'ממתין לתשובה', 'סבב 2'],
    ['משפחת לוי', '05X-XXXXXXX', 'ביקש לחזור מאוחר יותר', 'חוזר בתאריך שנבחר'],
    ['אבי מזרחי', '05X-XXXXXXX', 'לא ענה', 'יחזור בסבב הבא'],
    ['רונית שפירא', '05X-XXXXXXX', 'מספר שגוי', 'יצא מהתור · התראת דאטה'],
    ['יוסי אברהם', '05X-XXXXXXX', 'אישר הגעה', 'ירד מהתור'],
  ]

  const body = `${pageHero({
    eyebrow: 'מעקב אחרי מי שלא ענה',
    h1: 'ומה עם מי שלא ענה?',
    lead: 'כשצריך מספר סופי, יש מוזמנים שלא מספיק לשלוח להם הודעה. VEYA מנהלת גם את תור המעקב הטלפוני.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מעקב טלפוני' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_TIMELINE}`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">הבעיה</span>
            <h2 class="section-title">בכל רשימה יש קבוצה שפשוט לא עונה</h2>
            <p>
              לא כי הם לא רוצים לבוא. הם ראו את ההודעה, התכוונו לענות אחר כך, ושכחו.
              ככל שמתקרבים למועד שבו צריך למסור מספר, הקבוצה הזו הופכת לפער הגדול
              ביותר בין הרשימה למציאות.
            </p>
            <p class="why-punch">מי שלא ענה לא נעלם מהרשימה — הוא עובר לתור.</p>
          </div>
        </div>
      </section>

      <section class="flow tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">איפה זה נמצא בתהליך</span>
            <h2 class="section-title">המעקב הטלפוני אינו מוצר נפרד</h2>
            <p class="section-sub">
              הוא שלב בתוך אותו תהליך אישורי הגעה, על אותה רשימת מוזמנים.
            </p>
          </div>
${flowSteps([
  { icon: ic(P.chat), h: 'התהליך הדיגיטלי', p: 'בקשת אישור ותזכורות, למי שעדיין לא ענה.' },
  { icon: ic(P.users), h: 'מי שלא השלים תשובה', p: 'נשאר פתוח — לא מסומן כמגיע ולא כמסרב.' },
  { icon: ic(P.phone), h: 'תור שיחות', p: 'נגזר מאותו לוח זמנים, בלי רשימה נפרדת.' },
  { icon: ic(P.note), h: 'עדכון סטטוס', p: 'תוצאת השיחה נרשמת על אותה שורת מוזמן.' },
  { icon: ic(P.chart), h: 'מספר סופי', p: 'ביום סגירת הרשימה, אחרי הסבב האחרון.' },
])}
          <p class="flow-punch">VEYA מחברת את תהליך המעקב הטלפוני לאותה רשימת מוזמנים שבה אתם מנהלים את האירוע.</p>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">שלושה סבבים</span>
            <h2 class="section-title">מתי מתקשרים</h2>
            <p class="section-sub">
              הסבבים פרוסים בין התזכורות, והאחרון מוצמד למועד סגירת הרשימה — תאריך
              אחד ויחיד, לא שניים.
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
              <div class="numrow is-key"><dt>סבב אחרון</dt><dd>ביום סגירת הרשימה</dd></div>
            </dl>
            <p class="numcard-note">
              באותו יום לא יוצאים גם הודעה וגם סבב שיחות, ולא מתזמנים שלבים בשישי
              ובשבת. <b>אין סבבים נוספים מעבר לשלושה.</b>
            </p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">תור העבודה</span>
            <h2 class="section-title">איך נראית שורה בתור</h2>
            <p class="section-sub">
              רק מי שעדיין פתוח מופיע בתור. מי שאישר או סירב יורד ממנו מעצמו.
            </p>
          </div>
          <div class="numcard" style="max-width:660px">
            <div class="numcard-head">
              <h3>תור מעקב — המחשה</h3>
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
              במערכת: <b>אישר הגעה · לא מגיע · לא ענה · תפוס · מספר שגוי · ביקש לחזור מאוחר יותר</b>.
            </p>
          </div>

          <div class="supporting-grid" style="margin-top:28px">
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.users, 22)}</div>
              <h3>רק מי שפתוח</h3>
              <p>מי שכבר אישר או סירב לא חוזר לתור. לא מתקשרים אליו שוב.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.cal, 22)}</div>
              <h3>"ביקש לחזור" חוזר</h3>
              <p>הוא לא נחשב ניסיון שנכשל — הוא חוזר לתור במועד שנבחר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.note, 22)}</div>
              <h3>מספר שגוי = תקלת דאטה</h3>
              <p>יוצא מהתור ופותח התראה לתיקון ברשימה, במקום לחזור עם אותו מספר.</p>
            </article>
            <article class="supporting-item">
              <div class="ic" aria-hidden="true">${ic(P.chart, 22)}</div>
              <h3>אותה שורת מוזמן</h3>
              <p>תוצאת השיחה מעדכנת את הרשימה מיד — אין קובץ נפרד לסנכרן.</p>
            </article>
          </div>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">המעקב הטלפוני הוא שלב, לא מוצר</p>
            <p>
              הוא נגזר מאותו לוח זמנים של אישורי ההגעה, ומעדכן את אותם סטטוסים.
            </p>
            <p><a href="/features/rsvp/">איך עובדים אישורי ההגעה</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>שלא יישאר אף אחד באוויר</h2>
            <p class="band-more">
              מי שלא ענה נשאר גלוי, מנוהל ומטופל — עד שיש עליו תשובה.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/calls/',
    title: 'מעקב אחרי מי שלא אישר הגעה | VEYA',
    description:
      'תור מעקב טלפוני שנגזר מאותו לוח זמנים של אישורי ההגעה: שלושה סבבים, תוצאות שמעדכנות את סטטוס המוזמן, והסבב האחרון ביום סגירת הרשימה.',
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

   ⚠️ אמת מוצרית: מאז מיזוג מרחב ההושבה (`App.tsx: navItemsFor`) אין יותר
   פריט ניווט "ניהול מוזמנים" — הרשימה חיה בתוך מסך "סידור הושבה". לכן
   העמוד מתאר **שכבת נתונים**, לא מסך נפרד.
   ════════════════════════════════════════════════════════════════════ */

export function featureGuests() {
  const faq = [
    {
      q: 'איפה מנהלים את הרשימה בפועל?',
      a: 'הרשימה, הקבוצות וההערות נמצאות באותו מרחב עבודה של סידור ההושבה — כדי שלא תצטרכו לקפוץ בין מסך רשימה למסך אולם באמצע העבודה.',
    },
    {
      q: 'מה ההבדל בין מוזמנים לבין מגיעים?',
      a: 'מוזמנים זו הרשימה. מגיעים זה מי שסימן "מגיע", וזה המספר שנספר בהושבה ובחישוב העלות. "אולי" ו"ממתין לתשובה" נספרים כאפס.',
    },
    {
      q: 'מה קורה להערה שאני כותב על מוזמן?',
      a: 'יש שתי שכבות נפרדות: הערה פנימית שנשארת מידע בלבד, והערת הושבה שמזינה את סידור השולחנות. ההפרדה נועדה כדי שהערה תפעולית לא תתפרש בטעות כאילוץ ישיבה.',
    },
    {
      q: 'הקבוצות זהות בכל סוגי האירועים?',
      a: 'לא. הקבוצות משתנות לפי סוג האירוע — לבר מצווה יש משפחת האב, משפחת האם וכיתה, ולאירוע עסקי יש עובדים, לקוחות, ספקים והנהלה.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'רשימת מוזמנים',
    h1: 'רשימת המוזמנים היא המקור לכל האירוע',
    lead: 'כל מוזמן, קבוצה, כמות, סטטוס והערה נמצאים במקום אחד — ומשם ממשיכים לאישורי ההגעה, להושבה ולחישוב האירוע.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'רשימת מוזמנים' }],
    cta: `${CTA_PRIMARY}\n            ${CTA_COMMIT}`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">למה זה חשוב</span>
            <h2 class="section-title">אקסל לא נשבר כשהוא גדול. הוא נשבר כשיש ממנו שתי גרסאות.</h2>
            <p>
              ברוב האירועים הרשימה חיה בכמה מקומות במקביל: קובץ אחד אצלכם, קובץ אחר
              אצל ההורים, ותיקונים שנאמרו בטלפון. כל אחד מהם נכון בזמן אחר.
            </p>
            <p class="why-punch">רשימה אחת שכל השאר נגזר ממנה — זו כל הנקודה.</p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">מה יש בשורה</span>
            <h2 class="section-title">מוזמן הוא לא רק שם וטלפון</h2>
            <p class="section-sub">
              כל שדה כאן משמש בהמשך — באישורי ההגעה, בהושבה או בחישוב העלות.
            </p>
          </div>
          <div class="numcard" style="max-width:640px">
            <div class="numcard-head">
              <h3>השדות של כל מוזמן</h3>
              <span class="numcard-tag">מה נשמר</span>
            </div>
            <dl>
              <div class="numrow"><dt>שם וטלפון</dt><dd>הבסיס לפנייה</dd></div>
              <div class="numrow is-key"><dt>כמה אנשים ברשומה</dt><dd>לא כל מוזמן הוא אדם אחד</dd></div>
              <div class="numrow"><dt>צד וקבוצה</dt><dd>משפיעים על ההושבה ועל הפילוח</dd></div>
              <div class="numrow"><dt>סטטוס אישור הגעה</dt><dd>מגיע · לא מגיע · אולי · ממתין</dd></div>
              <div class="numrow"><dt>סימון ילד/ה</dt><dd>נבדק בהושבה, לא מנוחש</dd></div>
              <div class="numrow"><dt>הערה פנימית</dt><dd>מידע בלבד</dd></div>
              <div class="numrow"><dt>הערת הושבה</dt><dd>מזינה את סידור השולחנות</dd></div>
            </dl>
            <p class="numcard-note">
              <b>כמה אנשים ברשומה</b> הוא השדה שהכי קל לפספס: "משפחת כהן" יכולה להיות
              רשומה אחת וחמישה כיסאות. מי שסופר שורות במקום אנשים מוסר לאולם מספר שגוי.
            </p>
          </div>
${shot('/product/guests.png', 'טבלת המוזמנים ב-VEYA: שם, כמות, צד, קבוצה וסטטוס אישור הגעה')}
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">קבוצות</span>
            <h2 class="section-title">קבוצות שמתאימות לסוג האירוע</h2>
            <p class="section-sub">
              הקבוצות אינן תווית בלבד — הן מזינות את הסינון, את הפילוח ואת סידור ההושבה.
              והן משתנות לפי סוג האירוע, לא נשארות חתונתיות תמיד.
            </p>
          </div>
          <div class="evt-grid" style="max-width:860px;margin:0 auto">
            <a class="evt-card" href="/events/wedding/"><h3>חתונה</h3><p>משפחה קרובה, משפחה רחוקה, חברים, עבודה, צבא, לימודים, שכנים.</p></a>
            <a class="evt-card" href="/events/bar-mitzvah/"><h3>בר / בת מצווה</h3><p>משפחת האב, משפחת האם, כיתה, צוות וחוגים.</p></a>
            <a class="evt-card" href="/events/business/"><h3>אירוע עסקי</h3><p>עובדים, לקוחות, ספקים, הנהלה ושותפים — וגם המילה משתנה ל"משתתפים".</p></a>
          </div>
        </div>
      </section>

      <section class="rsvp-band tone-alt">
        <div class="wrap">
          <div class="rsvp-inner">
            <span class="kicker">מי באמת נספר</span>
            <h2 class="section-title">בין הרשימה לבין המספר יש הפרש</h2>
            <p>
              זה ההפרש שקובע כמה שולחנות לפתוח וכמה מנות למסור לאולם:
            </p>
            <ul class="rsvp-list">
              <li><strong>מוזמנים</strong> — כל מי שברשימה, לפי מספר האנשים בכל רשומה.</li>
              <li><strong>ממתינים</strong> — עדיין לא ענו. לא נספרים.</li>
              <li><strong>אולי</strong> — ענו, אבל לא הכריעו. לא נספרים.</li>
              <li><strong>מגיעים</strong> — אלה שנספרים בהושבה ובעלות.</li>
            </ul>
            <p class="why-punch">רק "מגיע" תופס מקום. כל השאר נשאר ברשימת המעקב.</p>
          </div>
        </div>
      </section>

      <section class="features tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">להתחיל</span>
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
              <p>מדביקים רשימה מטקסט חופשי — גם כשהיא לא מסודרת בטבלה.</p>
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
          <p class="fineprint">
            הייבוא מזהה גם את הקבוצות של סוג האירוע שבחרתם — "עובדים" באירוע עסקי,
            "משפחת האב" בבר מצווה.
          </p>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">ומהרשימה ממשיכים לשולחנות</p>
            <p>הקבוצות, הכמויות והערות ההושבה שסידרתם כאן הם בדיוק מה שסידור ההושבה קורא.</p>
            <p><a href="/features/seating/">סידור הושבה — מהרשימה לשולחנות</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>רשימה אחת, שכל השאר נגזר ממנה</h2>
            <p class="band-more">
              מעלים את הרשימה הקיימת וממשיכים משם — לאישורי ההגעה, להושבה ולחישוב האירוע.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/guests/',
    title: 'ניהול רשימת מוזמנים לאירוע | VEYA',
    description:
      'רשימת המוזמנים כמקור אחד לכל האירוע: כמות אנשים בכל רשומה, קבוצות לפי סוג האירוע, סטטוס אישור הגעה, הערות הושבה וייבוא רשימה קיימת.',
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
      q: 'האם המערכת מסדרת את ההושבה במקומי?',
      a: 'היא נותנת נקודת פתיחה. הסידור נבנה לפי מה שסימנתם — קבוצות, צדדים, הערות ואילוצים — ואתם מזיזים ומשנים אותו עד שהוא נראה לכם נכון. המנוע לא "מבין אנשים", הוא עובד לפי מה שאמרתם לו.',
    },
    {
      q: 'מה קורה אם אילוץ לא מסתדר?',
      a: 'אחרי כל הרצה נבדקת התוצאה בפועל — קיבולת שולחנות, זוגות שאסור להושיב יחד, ומי נשאר בלי שולחן. אם יש הפרה של חוק קשיח, שום דבר לא נשמר ואתם מקבלים פירוט מדויק של מה לא הסתדר.',
    },
    {
      q: 'מה בדיוק אומר "לא ליד"?',
      a: 'שהשניים לא יישבו באותו שולחן. שולחן סמוך אינו נחסם — זו הכרעה מכוונת, כי חסימה של שולחנות סמוכים הופכת כמעט כל אולם לבלתי פתיר.',
    },
    {
      q: 'אפשר לבטל סידור שלא אהבתי?',
      a: 'כן. לפני כל הרצה נשמר תצלום של המצב הקודם בשרת, ואפשר לחזור אליו — גם אחרי רענון הדף או מעבר למכשיר אחר.',
    },
    {
      q: 'מי נכנס לסידור?',
      a: 'רק מי שמסומן "מגיע". מוזמן שממתין לתשובה, מתלבט או ביטל אינו נכנס אוטומטית לשולחנות.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'סידור הושבה',
    h1: 'מהרשימה לשולחנות',
    lead: 'סידור הושבה שמכיר את המוזמנים, את הקבוצות ואת האילוצים שלכם.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'סידור הושבה' }],
    cta: `${CTA_PRIMARY}\n            <a href="/features/guests/" class="btn btn-ghost">להתחיל מהרשימה</a>`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">הבעיה</span>
            <h2 class="section-title">ההושבה לא קשה כי יש הרבה אנשים. היא קשה כי יש כללים.</h2>
            <p>
              מי יושב עם מי, מי לא יכול לשבת ליד מי, מי צריך להיות רחוק מהרמקול ומי
              ליד הכניסה. את הכללים האלה אתם כבר יודעים — הם פשוט לא כתובים בשום מקום
              שאפשר לעבוד איתו.
            </p>
            <p class="why-punch">מה שסימנתם ברשימה הוא בדיוק מה שסידור ההושבה קורא.</p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">מפת האולם</span>
            <h2 class="section-title">הסקיצה שקיבלתם הופכת למפה שאפשר לעבוד עליה</h2>
            <p class="section-sub">
              מעלים את הסקיצה של האולם, מסדרים עליה את השולחנות ומסמנים את האזורים —
              רחבה, בר, כניסה ועמדת התקליטן.
            </p>
          </div>
${shot('/product/seating.png', 'עורך מפת האולם ב-VEYA: שולחנות מסודרים על סקיצת האולם ומוזמנים משובצים')}
          <p class="fineprint">
            מיקום השולחן אינו קישוט: המנוע יודע איפה כל שולחן נמצא, ולכן "רחוק מהרעש"
            או "ליד הכניסה" הם אילוצים שהוא באמת יכול לכבד.
          </p>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">אילוצים</span>
            <h2 class="section-title">"לא ליד עומר" — ומה המערכת עושה עם זה</h2>
            <p class="section-sub">
              כותבים את הכללים בשפה רגילה בהערת ההושבה של המוזמן. אלה סוגי האילוצים
              שהמנוע מכיר:
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
              לא נשמר בכלל. השאר הן העדפות שהמנוע מנסה למקסם — ולפעמים מתנגשות זו בזו.
            </p>
          </div>
          <p class="fineprint">
            משפחה נשארת יחד: רשומת מוזמן אחת יושבת תמיד באותו שולחן, ולא מתפצלת בין שניים.
          </p>
        </div>
      </section>

      <section class="rsvp-band tone-alt">
        <div class="wrap">
          <div class="rsvp-inner">
            <span class="kicker">מי מושב</span>
            <h2 class="section-title">רק מי שמסומן "מגיע" נספר לשולחנות</h2>
            <p>
              זה נשמע מובן מאליו, וזה המקום שבו סידורי הושבה נשברים: אם סופרים גם את
              מי שעדיין לא ענה, פותחים שולחנות שיישארו ריקים.
            </p>
            <ul class="rsvp-list">
              <li><strong>מגיע</strong> — נכנס לסידור, ותופס את מספר המקומות שהוא הביא.</li>
              <li><strong>ממתין לתשובה</strong> — לא נכנס אוטומטית.</li>
              <li><strong>אולי</strong> — לא נכנס אוטומטית.</li>
              <li><strong>לא מגיע</strong> — לא נכנס.</li>
            </ul>
            <p class="why-punch">אותו מספר בדיוק שמזין את חישוב העלות.</p>
          </div>
        </div>
      </section>

      <section class="features tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">אחרי ההרצה</span>
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
            בשקט — ואם לא ניתן לקיים אותו, תדעו על זה.
          </p>

          <div class="callout" style="max-width:620px;margin:32px auto 0">
            <p class="callout-h">הכול מתחיל ברשימה</p>
            <p>הקבוצות, הכמויות והערות ההושבה שמזינות את הסידור נמצאות ברשימת המוזמנים.</p>
            <p><a href="/features/guests/">ניהול רשימת המוזמנים</a></p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
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
