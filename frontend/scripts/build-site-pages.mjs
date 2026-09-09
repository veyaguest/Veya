#!/usr/bin/env node
/**
 * בונה את עמודי האתר הציבורי הסטטיים: מחשבונים, עמוד המוצר "מאזן האירוע",
 * ומרכז המדריכים — כולם דרך מעטפת אחת (`site-shell.mjs`).
 *
 * הרצה: npm run build:site (רץ אוטומטית ב-prebuild).
 *
 * כתובת ה-API מוזרקת כאן בזמן build מ-`VITE_API_URL`, בדיוק כמו שהאפליקציה
 * מקבלת אותה — כי עמוד סטטי ב-public/ לא עובר דרך Vite ואין לו גישה ל-
 * `import.meta.env`. בלי זה כל מחשבון היה צריך לנחש את כתובת השרת.
 */
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { marked } from 'marked'
import { page, pageHero, faqHtml, esc, SITE, CTA_PRIMARY } from './site-shell.mjs'
import { EVENT_TYPES, GROUPS, EXPENSES, FOCUS } from '../content/event-types.mjs'
import { featureRsvp, featureCalls, featureGuests, featureSeating } from './build-features.mjs'
import { buildNuschim } from './build-nuschim.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const PUB = path.resolve(__dirname, '../public')
const GUIDES_SRC = path.resolve(__dirname, '../content/guides')

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000'

const written = []
const titles = new Map()
function emit(routePath, html) {
  const dir = path.join(PUB, routePath.replace(/^\/|\/$/g, ''))
  mkdirSync(dir, { recursive: true })
  writeFileSync(path.join(dir, 'index.html'), html)
  written.push(routePath)
  const t = html.match(/<title>([^<]*)<\/title>/)
  if (t) titles.set(routePath, t[1].replace(/\s*\|\s*VEYA\s*$/, '').trim())
  console.log(`✓ ${routePath}`)
}

/* ════════════════════════════════════════════════════════════════════
   מדריכים — נקראים מקבצי Markdown ב-content/guides/
   ════════════════════════════════════════════════════════════════════ */

/** Frontmatter מינימלי: `key: value` עד שורת `---` סוגרת. אין תלות חיצונית. */
function parseFrontmatter(raw) {
  if (!raw.startsWith('---')) return { meta: {}, body: raw }
  const end = raw.indexOf('\n---', 3)
  const head = raw.slice(4, end)
  const body = raw.slice(end + 4).replace(/^\n+/, '')
  const meta = {}
  let key = null
  for (const line of head.split('\n')) {
    const m = line.match(/^([a-z_]+):\s*(.*)$/)
    if (m) {
      key = m[1]
      meta[key] = m[2].trim()
      if (meta[key] === '') meta[key] = []
    } else if (line.trim().startsWith('- ') && Array.isArray(meta[key])) {
      meta[key].push(line.trim().slice(2).trim())
    }
  }
  return { meta, body }
}

/** FAQ נכתב במקור כ-`## שאלות נפוצות` עם ### לכל שאלה — נשלף ל-Schema. */
function extractFaq(body) {
  const idx = body.indexOf('\n## שאלות נפוצות')
  if (idx < 0) return { body, faq: [] }
  const section = body.slice(idx)
  const rest = body.slice(0, idx)
  const faq = []
  const re = /\n### (.+)\n([\s\S]*?)(?=\n### |\n## |$)/g
  let m
  while ((m = re.exec(section))) {
    faq.push({ q: m[1].trim(), a: m[2].trim().replace(/\n+/g, ' ') })
  }
  return { body: rest, faq }
}

const CLUSTERS = {
  A: { title: 'התחייבות לאולם וכמות מגיעים', blurb: 'המספר שאתם מוסרים לאולם, ומה הוא אומר בשקלים.' },
  B: { title: 'מאזן האירוע', blurb: 'כמה האירוע עולה, כמה נכנס, ומה נשאר בסוף.' },
  C: { title: 'אישורי הגעה', blurb: 'איך מגיעים למספר שאפשר לסמוך עליו.' },
  D: { title: 'מוזמנים והושבה', blurb: 'מהרשימה אל השולחנות.' },
  E: { title: 'נוסחים', blurb: 'מה כותבים, ומתי.' },
  F: { title: 'סוגי אירועים', blurb: 'לכל אירוע יש לוגיסטיקה משלו.' },
  G: { title: 'תרחישים', blurb: 'מה עושים כשמשהו משתנה.' },
}

function guideHtml(g) {
  const bodyHtml = marked
    .parse(g.body, { gfm: true })
    .replace(/<table>/g, '<div class="table-scroll"><table>')
    .replace(/<\/table>/g, '</table></div>')

  // `related` נכתב ב-frontmatter כשורות "url|כותרת" — פורמט אחד, בלי
  // תלות בספריית YAML.
  const rel = (g.related || []).map((line) => {
    const [url, title] = String(line).split('|')
    return { url: url.trim(), title: (title || url).trim() }
  })
  const related = rel.length
    ? `<div class="guide-cluster">
          <h2 style="border:0;padding:0;margin-top:0">להמשך</h2>
          <ul class="guide-list">
${rel.map((r) => `            <li><a href="${r.url}"><h3>${esc(r.title)}</h3></a></li>`).join('\n')}
          </ul>
        </div>`
    : ''

  return page({
    path: `/guides/${g.slug}/`,
    title: `${g.title} | VEYA`,
    description: g.description,
    ogType: 'article',
    faq: g.faq,
    trail: [
      { name: 'VEYA', url: '/' },
      { name: 'מדריכים', url: '/guides/' },
      { name: g.short || g.title },
    ],
    schema: [
      {
        '@type': 'Article',
        headline: g.title,
        description: g.description,
        inLanguage: 'he-IL',
        datePublished: g.published,
        dateModified: g.updated || g.published,
        author: { '@type': 'Organization', name: 'צוות VEYA', url: SITE },
        publisher: { '@type': 'Organization', name: 'VEYA', url: SITE, logo: `${SITE}/logo.png` },
        mainEntityOfPage: { '@type': 'WebPage', '@id': `${SITE}/guides/${g.slug}/` },
      },
    ],
    body: `${pageHero({
      eyebrow: CLUSTERS[g.cluster]?.title || 'מדריך',
      h1: esc(g.title),
      lead: esc(g.description),
      trail: [
        { name: 'VEYA', url: '/' },
        { name: 'מדריכים', url: '/guides/' },
        { name: g.short || g.title },
      ],
    })}

      <section class="article-wrap">
        <div class="wrap">
          <article class="article">
            <p class="article-meta">
              <span>צוות VEYA</span>
              <span>עודכן: <time datetime="${g.updated || g.published}">${g.updated_he || g.published_he}</time></span>
            </p>
            <p class="article-lead">${esc(g.lead)}</p>
${bodyHtml.split('\n').map((l) => '            ' + l).join('\n')}

            <div class="article-cta">
              <h2>${esc(g.cta_title)}</h2>
              <p>${esc(g.cta_text)}</p>
              <a href="${g.cta_url}" class="btn btn-primary">${esc(g.cta_label)} <span class="arw" aria-hidden="true">←</span></a>
            </div>
${related}
          </article>
        </div>
      </section>

${faqHtml(g.faq)}`,
  })
}

function loadGuides() {
  if (!existsSync(GUIDES_SRC)) return []
  return readdirSync(GUIDES_SRC)
    .filter((f) => f.endsWith('.md'))
    .map((f) => {
      const raw = readFileSync(path.join(GUIDES_SRC, f), 'utf8')
      const { meta, body: full } = parseFrontmatter(raw)
      const { body, faq } = extractFaq(full)
      return { ...meta, slug: meta.slug || f.replace(/\.md$/, ''), body, faq }
    })
    .sort((a, b) => (a.cluster + a.order).localeCompare(b.cluster + b.order))
}

function guidesIndex(guides) {
  const byCluster = {}
  for (const g of guides) (byCluster[g.cluster] ||= []).push(g)

  const sections = Object.entries(CLUSTERS)
    .filter(([k]) => byCluster[k]?.length)
    .map(([k, c]) => `        <div class="guide-cluster">
          <h2>${esc(c.title)}</h2>
          <p>${esc(c.blurb)}</p>
          <ul class="guide-list">
${byCluster[k].map((g) => `            <li><a href="/guides/${g.slug}/"><h3>${esc(g.title)}</h3><p>${esc(g.description)}</p></a></li>`).join('\n')}
          </ul>
        </div>`).join('\n')

  return page({
    path: '/guides/',
    title: 'מדריכים לניהול אירוע | VEYA',
    description:
      'מדריכים פרקטיים לניהול אירוע בישראל: התחייבות לאולם, אישורי הגעה, הושבה, הוצאות והשורה התחתונה. בלי תיאוריה, עם מספרים.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מדריכים' }],
    schema: [
      {
        '@type': 'CollectionPage',
        name: 'מדריכים לניהול אירוע',
        inLanguage: 'he-IL',
        url: `${SITE}/guides/`,
      },
    ],
    body: `${pageHero({
      eyebrow: 'מרכז הידע',
      h1: 'מדריכים לניהול אירוע',
      lead: 'הדברים שבאמת עולים כסף באירוע ישראלי — ההתחייבות לאולם, מספר המגיעים, ההושבה וההוצאות. מדריכים קצרים עם מספרים, לא עם סיסמאות.',
      trail: [{ name: 'VEYA', url: '/' }, { name: 'מדריכים' }],
    })}

      <section class="article-wrap">
        <div class="wrap">
${sections}
        </div>
      </section>`,
  })
}

/* ════════════════════════════════════════════════════════════════════
   מחשבונים
   ════════════════════════════════════════════════════════════════════ */

const CALCS = [
  {
    slug: 'venue-commitment',
    title: 'התחייבות לאולם — כמה באמת משלמים',
    short: 'מחשבון התחייבות',
    desc: 'מזינים כמה אישרו הגעה, על כמה התחייבתם ומה מחיר המנה — ורואים על כמה מנות באמת משלמים וכמה מוסיף כל אדם נוסף.',
  },
  {
    slug: 'rsvp-timeline',
    title: 'לוח הזמנים של אישורי ההגעה',
    short: 'מחשבון לוח זמנים',
    desc: 'מזינים תאריך אירוע וכמה ימים לפניו צריך למסור לאולם מספר — ומקבלים את שבעת השלבים בתאריכים אמיתיים.',
  },
]

function calcIndex() {
  return page({
    path: '/calculators/',
    title: 'מחשבונים לאירוע | VEYA',
    description:
      'מחשבונים חינמיים לאירוע: התחייבות לאולם, כמה מוסיף אדם נוסף, ולוח הזמנים של אישורי ההגעה. אותו חישוב שרץ בתוך VEYA.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים' }],
    schema: [
      {
        '@type': 'CollectionPage',
        name: 'מחשבונים לאירוע',
        inLanguage: 'he-IL',
        url: `${SITE}/calculators/`,
        description: 'מחשבוני התחייבות לאולם ולוח זמנים לאישורי הגעה.',
      },
    ],
    body: `${pageHero({
      eyebrow: 'כלים',
      h1: 'מחשבונים לאירוע',
      lead: 'אותו מנוע חישוב שרץ בתוך VEYA, פתוח לכולם. בלי הרשמה ובלי להשאיר פרטים.',
      trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים' }],
    })}

      <section class="article-wrap">
        <div class="wrap">
          <div class="calc-grid">
${CALCS.map((c) => `            <a class="evt-card" href="/calculators/${c.slug}/"><h3>${esc(c.title)}</h3><p>${esc(c.desc)}</p></a>`).join('\n')}
          </div>
          <p class="calc-note" style="max-width:62ch">
            המחשבונים לא שומרים את מה שהזנתם ולא מבקשים פרטים. הם רצים מול אותו
            מנוע חישוב של המערכת, כדי שהמספר שתראו כאן יהיה בדיוק המספר שתראו בפנים.
          </p>
        </div>
      </section>`,
  })
}

/* ---- מחשבון ההתחייבות לאולם ---- */

function calcVenueCommitment() {
  const faq = [
    {
      q: 'מה זה בעצם התחייבות לאולם?',
      a: 'הכמות המינימלית שסיכמתם בחוזה מול האולם או הספק. גם אם יגיעו פחות אנשים מהכמות הזו, החיוב נשאר לפי הכמות שהתחייבתם עליה.',
    },
    {
      q: 'למה אדם נוסף עולה לפעמים 0 ₪?',
      a: 'כל עוד מספר המגיעים נמוך מכמות ההתחייבות, אתם כבר משלמים על המקום שלו. רק מהרגע שעוברים את ההתחייבות כל אדם נוסף נספר במחיר מלא. אם יש לכם הוצאות נוספות לאדם, כמו אלכוהול, הן כן מתווספות גם מתחת להתחייבות.',
    },
    {
      q: 'מה זה מינימום כספי, ובמה הוא שונה מכמות ההתחייבות?',
      a: 'יש חוזים שנוקבים בסכום מינימלי ולא רק בכמות מנות. כשגם וגם רשומים בחוזה, נספר הגבוה מבין השניים. המחשבון מיישם בדיוק את הכלל הזה.',
    },
    {
      q: 'האם המחשבון שומר את הנתונים שהזנתי?',
      a: 'לא. הנתונים נשלחים לחישוב וחוזרים כתשובה, בלי שמירה ובלי זיהוי. אין צורך בהרשמה.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'מחשבון',
    h1: 'מחשבון התחייבות לאולם',
    lead: 'מזינים כמה אישרו הגעה, על כמה התחייבתם בחוזה ומה מחיר המנה. המחשבון מראה על כמה מנות מחייבים אתכם בפועל, וכמה מוסיף כל אדם נוסף.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים', url: '/calculators/' }, { name: 'התחייבות לאולם' }],
  })}

      <section class="article-wrap">
        <div class="wrap">
          <div class="calc">
            <form class="calc-form" id="f" novalidate>
              <div class="calc-error" id="err" hidden role="alert"></div>

              <label class="calc-field">
                <span>כמה אנשים אישרו הגעה?</span>
                <input type="number" id="attendees" inputmode="numeric" min="0" max="100000" value="463" required />
              </label>

              <label class="calc-field">
                <span>על כמה מנות התחייבתם בחוזה?
                  <span class="hint">אפשר להשאיר ריק אם אין התחייבות.</span>
                </span>
                <input type="number" id="committed" inputmode="numeric" min="0" max="100000" value="500" />
              </label>

              <label class="calc-field">
                <span>מחיר למנה, בשקלים</span>
                <input type="number" id="meal" inputmode="numeric" min="0" step="1" value="320" required />
              </label>

              <label class="calc-field">
                <span>עוד הוצאות לאדם, בשקלים
                  <span class="hint">אלכוהול, מתנה למוזמן — כל מה שמשולם לפי ראש ואינו כלול במנה.</span>
                </span>
                <input type="number" id="extra" inputmode="numeric" min="0" step="1" value="0" />
              </label>

              <label class="calc-field">
                <span>מינימום כספי בחוזה, בשקלים
                  <span class="hint">רק אם החוזה נוקב בסכום ולא רק בכמות.</span>
                </span>
                <input type="number" id="mintotal" inputmode="numeric" min="0" step="1" value="" />
              </label>

              <label class="calc-field">
                <span>הוצאות קבועות, בשקלים
                  <span class="hint">צילום, מוזיקה, עיצוב — לא זזות עם מספר המגיעים, אבל משנות את העלות לאדם.</span>
                </span>
                <input type="number" id="fixed" inputmode="numeric" min="0" step="1" value="" />
              </label>

              <button type="submit" class="btn btn-primary">לחשב</button>
            </form>

            <div class="calc-out" id="out" aria-live="polite">
              <div class="calc-empty">מזינים את הנתונים ולוחצים "לחשב".</div>
            </div>
          </div>

          <article class="article" style="margin-top:56px">
            <h2>למה זה לא סתם כפל</h2>
            <p>
              אולם ישראלי נמכר כמעט תמיד בהתחייבות לכמות מנות מינימלית. זוג שהתחייב על
              500 מנות ומגיעים אליו 463 <strong>משלם על 500</strong>, לא על 463. לכן החישוב
              הנכון הוא:
            </p>
            <div class="callout">
              <p class="callout-h">מנות לחיוב = הגבוה מבין מספר המגיעים לכמות ההתחייבות</p>
              <p>ואם החוזה נוקב גם במינימום כספי — נספר הגבוה מבין המכפלה לבין הסכום הזה.</p>
            </div>
            <p>
              מכאן נגזרת גם התשובה לשאלה שנשאלת הכי הרבה בשבועיים האחרונים לפני האירוע:
              <strong>כמה עולה עוד אדם?</strong> מתחת להתחייבות התשובה היא לרוב 0 ₪ על
              המנה עצמה, כי כבר משלמים עליה. מעל ההתחייבות — מחיר מנה מלא. מחשבון שמכפיל
              מחיר במספר אנשים ייתן כאן תשובה שגויה בשתי המדרגות.
            </p>
            <p class="calc-note">
              <b>הבהרה:</b> המחשבון לא מציג מחירי שוק ולא מעריך כמה עולה מנה. הוא מחשב
              לפי המספרים שאתם מזינים מהחוזה שלכם. אותו חישוב עצמו רץ בתוך VEYA על
              נתוני האירוע האמיתיים שלכם.
            </p>
            <div class="callout" style="margin-top:24px">
              <p class="callout-h">רוצים להבין איך בוחרים את המספר מלכתחילה?</p>
              <p>המדריך המלא מסביר על כמה כדאי להתחייב, מה קורה כשמגיעים פחות, ומתי מוסרים לאולם מספר סופי.</p>
              <p><a href="/guides/hitchayvut-la-ulam/">התחייבות לאולם — כמה מנות באמת להתחייב</a></p>
            </div>
          </article>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">בתוך VEYA</span>
            <h2>המספר הזה מתעדכן לבד</h2>
            <p class="band-more">
              בתוך המערכת ההתחייבות יושבת על שורת ההוצאה, ומספר המגיעים מגיע מאישורי
              ההגעה בפועל — כך שהעלות זזה עם כל אישור חדש, בלי שתזינו שוב כלום.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  const script = `      var f = document.getElementById('f'), out = document.getElementById('out'), err = document.getElementById('err');
      function sh(id) { var v = document.getElementById(id).value.trim(); return v === '' ? null : Math.round(Number(v) * 100); }
      function num(id) { var v = document.getElementById(id).value.trim(); return v === '' ? null : Math.round(Number(v)); }
      function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

      f.addEventListener('submit', function (e) {
        e.preventDefault();
        err.hidden = true;
        var body = {
          attendees: num('attendees') || 0,
          meal_price_agorot: sh('meal') || 0,
          committed_quantity: num('committed'),
          min_total_agorot: sh('mintotal'),
          extra_per_attendee_agorot: sh('extra') || 0,
          fixed_agorot: sh('fixed') || 0
        };
        if (!(body.attendees >= 0) || !(body.meal_price_agorot >= 0)) {
          err.textContent = 'נשמח שתזינו מספר מגיעים ומחיר מנה.'; err.hidden = false; return;
        }
        out.innerHTML = '<div class="calc-empty">רגע אחד…</div>';
        fetch(window.VEYA_API + '/public/calculators/venue-commitment', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        }).then(function (r) {
          return r.json().then(function (d) { if (!r.ok) throw new Error(d.detail || 'שגיאה'); return d; });
        }).then(render).catch(function (e2) {
          out.innerHTML = '<div class="calc-empty">לא הצלחנו לחשב כרגע. אפשר לנסות שוב.</div>';
          err.textContent = e2.message || 'לא הצלחנו לחשב כרגע.'; err.hidden = false;
        });
      });

      function render(d) {
        var head, note;
        if (d.committed_quantity && d.unused_quantity > 0) {
          head = 'משלמים על ' + d.billed_quantity + ' מנות';
          note = 'אישרו הגעה ' + d.attendees + ', והתחייבתם על ' + d.committed_quantity +
                 '. ' + d.unused_quantity + ' מנות לא ינוצלו, ועדיין נספרות.';
        } else if (d.committed_quantity && d.over_commitment > 0) {
          head = 'משלמים על ' + d.billed_quantity + ' מנות';
          note = 'עברתם את ההתחייבות ב-' + d.over_commitment + ' אנשים. מכאן כל אדם נספר במחיר מלא.';
        } else {
          head = 'משלמים על ' + d.billed_quantity + ' מנות';
          note = d.committed_quantity ? 'מספר המגיעים תואם בדיוק להתחייבות.' : 'לא הזנתם התחייבות, ולכן החיוב לפי מספר המגיעים.';
        }
        if (d.min_total_applied) { note += ' המינימום הכספי בחוזה גבוה מהמכפלה, ולכן הוא זה שנספר.'; }

        var rows = '';
        function row(label, value, key) {
          rows += '<div class="numrow' + (key ? ' is-key' : '') + '"><dt>' + esc(label) + '</dt><dd>' + esc(value) + '</dd></div>';
        }
        row('אישרו הגעה', d.attendees + ' אנשים');
        if (d.committed_quantity) { row('התחייבתם על', d.committed_quantity + ' מנות'); }
        row('משלמים על', d.billed_quantity + ' מנות', true);
        row('עלות שורת המנה', d.meal_line.total_display);
        row('סך העלות שהוזנה', d.total_display, true);
        if (d.cost_per_attendee_display) { row('עלות ממוצעת לאדם שמגיע', d.cost_per_attendee_display); }

        var sc = '';
        if (d.scenarios && d.scenarios.length) {
          sc = '<div class="numcard" style="margin-top:18px"><div class="numcard-head"><h3>מה קורה אם יגיעו יותר או פחות</h3></div><dl>';
          d.scenarios.forEach(function (s) {
            var tag = s.is_current ? ' (כרגע)' : s.is_commitment ? ' (ההתחייבות)' : '';
            sc += '<div class="numrow' + (s.is_current ? ' is-key' : '') + '"><dt>' + s.attendees + ' מגיעים' + tag + '</dt><dd>' + esc(s.total_display) + '</dd></div>';
          });
          sc += '</dl></div>';
        }

        // המספר הוא העוגן הוויזואלי של המסך: הוא מקבל את חתימת המספרים
        // של VEYA, ומונפש מהערך הקודם לחדש כדי שהשינוי יהיה מורגש.
        var prev = window.__veyaPrevNext;
        var nextAgorot = d.next_attendee_agorot;
        window.__veyaPrevNext = nextAgorot;

        out.innerHTML =
          '<div class="calc-headline"><span class="lbl">אדם נוסף מוסיף לכם</span>' +
          '<span class="big num-value" id="calc-anchor">' + esc(d.next_attendee_display) + '</span>' +
          '<p>' + esc(note) + '</p></div>' +
          '<div class="numcard"><div class="numcard-head"><h3>' + esc(head) + '</h3><span class="numcard-tag">החישוב</span></div><dl>' + rows + '</dl></div>' +
          sc;

        // הנפשת המעבר בין תוצאה לתוצאה — רק כשיש ערך קודם ורק כשלא
        // ביקשו תנועה מופחתת. veyaCountUp מכבד את ההעדפה בעצמו.
        var anchor = document.getElementById('calc-anchor');
        if (anchor && typeof prev === 'number' && prev !== nextAgorot && window.veyaCountUp) {
          anchor.setAttribute('data-count-from', (prev / 100).toFixed(0));
          anchor.setAttribute('data-count-to', (nextAgorot / 100).toFixed(0));
          anchor.setAttribute('data-count-suffix', '\u202f₪');
          anchor.setAttribute('data-count-duration', '500');
          window.veyaCountUp(anchor);
        }
      }`

  return page({
    path: '/calculators/venue-commitment/',
    title: 'מחשבון התחייבות לאולם — על כמה באמת משלמים | VEYA',
    description:
      'מחשבון התחייבות לאולם: כמה מנות מחייבים אתכם בפועל כשמגיעים פחות ממה שהתחייבתם, וכמה מוסיף כל אדם נוסף. אותו חישוב שרץ בתוך VEYA.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים', url: '/calculators/' }, { name: 'התחייבות לאולם' }],
    faq,
    schema: [
      {
        '@type': 'WebApplication',
        name: 'מחשבון התחייבות לאולם',
        applicationCategory: 'FinanceApplication',
        operatingSystem: 'Web',
        inLanguage: 'he-IL',
        url: `${SITE}/calculators/venue-commitment/`,
        description: 'חישוב כמות המנות לחיוב מול ההתחייבות בחוזה, והעלות של אורח נוסף.',
      },
    ],
    body,
    scripts: `    <script>\n      window.VEYA_API = ${JSON.stringify(API_URL)};\n${script}\n    </script>`,
  })
}

/* ---- מחשבון לוח הזמנים של אישורי ההגעה ---- */

function calcRsvpTimeline() {
  const faq = [
    {
      q: 'למה בונים את לוח הזמנים לאחור ולא קדימה?',
      a: 'כי התאריך היחיד שבאמת מחייב אתכם הוא היום שבו צריך למסור לאולם מספר סופי. אם פורסים את השלבים קדימה מהיום שבו נזכרתם, הסבב האחרון נופל אחרי שכבר היה צריך להחליט.',
    },
    {
      q: 'למה אין שלבים בשישי ושבת?',
      a: 'שלב שנופל על סוף שבוע נדחה ליום פעיל. בקשת אישור שנשלחת בשישי בערב נבלעת, וסבב שיחות בשבת פשוט לא קורה.',
    },
    {
      q: 'מה קורה כשנשאר מעט מדי זמן?',
      a: 'הלוח מתכווץ: אותם שבעה שלבים נדחסים לטווח שנשאר, אבל שני שלבים לעולם לא נופלים על אותו יום — וסבב שיחות ובקשה בהודעה לא יוצאים באותו יום.',
    },
    {
      q: 'האם זה מחייב אותי לשלוח בדיוק בתאריכים האלה?',
      a: 'לא. זו תוכנית עבודה, לא התחייבות. בתוך VEYA אתם מאשרים כל שליחה לפני שהיא יוצאת.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'מחשבון',
    h1: 'לוח הזמנים של אישורי ההגעה',
    lead: 'מזינים את תאריך האירוע וכמה ימים לפניו צריך למסור לאולם מספר סופי. מקבלים את שבעת השלבים בתאריכים אמיתיים — נפרסים לאחור, בלי שישי ושבת.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים', url: '/calculators/' }, { name: 'לוח זמנים' }],
  })}

      <section class="article-wrap">
        <div class="wrap">
          <div class="calc">
            <form class="calc-form" id="f" novalidate>
              <div class="calc-error" id="err" hidden role="alert"></div>

              <label class="calc-field">
                <span>תאריך האירוע</span>
                <input type="date" id="date" required />
              </label>

              <label class="calc-field">
                <span>כמה ימים לפני האירוע צריך למסור לאולם מספר סופי?
                  <span class="hint">רוב האולמות מבקשים בין 3 ל-7 ימים. כתוב בחוזה.</span>
                </span>
                <select id="days">
                  <option value="1">יום אחד לפני האירוע</option>
                  <option value="2">2 ימים לפני האירוע</option>
                  <option value="3">3 ימים לפני האירוע</option>
                  <option value="4">4 ימים לפני האירוע</option>
                  <option value="5" selected>5 ימים לפני האירוע</option>
                  <option value="6">6 ימים לפני האירוע</option>
                  <option value="7">7 ימים לפני האירוע</option>
                  <option value="8">8 ימים לפני האירוע</option>
                  <option value="9">9 ימים לפני האירוע</option>
                  <option value="10">10 ימים לפני האירוע</option>
                </select>
              </label>

              <button type="submit" class="btn btn-primary">לראות את לוח הזמנים</button>
            </form>

            <div class="calc-out" id="out" aria-live="polite">
              <div class="calc-empty">בוחרים תאריך אירוע ולוחצים "לראות את לוח הזמנים".</div>
            </div>
          </div>

          <article class="article" style="margin-top:56px">
            <h2>מה יש בלוח הזה</h2>
            <p>
              שבעה שלבים: בקשת אישור ראשונה, שלוש תזכורות ושלושה סבבי מעקב טלפוני.
              הסבב האחרון נופל <strong>בדיוק על מועד סגירת הרשימה</strong> — זה תאריך אחד
              ויחיד, לא שניים. ביום הזה סוגרים את הרשימה ומוסרים מספר.
            </p>
            <p>
              שני כללים נוספים שמופעלים אוטומטית: שלב שנופל על שישי או שבת נדחה ליום
              פעיל, ובאותו יום לא יוצאים גם הודעה וגם סבב שיחות.
            </p>
            <p class="calc-note">
              <b>הבהרה:</b> מספר הימים שהאולם דורש משתנה בין אולמות — בדקו את החוזה
              שלכם. המחשבון לא מניח מספר מטעמכם.
            </p>
          </article>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">בתוך VEYA</span>
            <h2>הלוח הזה הופך לתוכנית עבודה</h2>
            <p class="band-more">
              במערכת התאריכים האלה מנהלים את התהליך בפועל: מי מקבל מה ומתי, מי עדיין לא
              ענה, ומי צריך מעקב לפני שסוגרים את הרשימה.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  const script = `      var f = document.getElementById('f'), out = document.getElementById('out'), err = document.getElementById('err'), di = document.getElementById('date');
      var t = new Date(); t.setDate(t.getDate() + 1);
      di.min = t.toISOString().slice(0, 10);
      var d90 = new Date(); d90.setDate(d90.getDate() + 90);
      di.value = d90.toISOString().slice(0, 10);
      function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
      function heb(iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }

      f.addEventListener('submit', function (e) {
        e.preventDefault();
        err.hidden = true;
        if (!di.value) { err.textContent = 'נשמח שתבחרו תאריך אירוע.'; err.hidden = false; return; }
        out.innerHTML = '<div class="calc-empty">רגע אחד…</div>';
        fetch(window.VEYA_API + '/public/calculators/rsvp-timeline', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event_date: di.value, commit_days_before: Number(document.getElementById('days').value) })
        }).then(function (r) {
          return r.json().then(function (d) { if (!r.ok) throw new Error(d.detail || 'שגיאה'); return d; });
        }).then(render).catch(function (e2) {
          out.innerHTML = '<div class="calc-empty">לא הצלחנו לבנות לוח זמנים כרגע.</div>';
          err.textContent = e2.message || 'לא הצלחנו לחשב כרגע.'; err.hidden = false;
        });
      });

      function render(d) {
        var items = d.placements.map(function (p) {
          var last = p.type === 'call_round' && p.date === d.commitment_date;
          return '<li class="tl-item' + (last ? ' is-final' : '') + '">' +
            '<span class="ico" aria-hidden="true">' + esc(p.icon) + '</span>' +
            '<span class="nm">' + esc(p.label) + (last ? ' — ומועד סגירת הרשימה' : '') +
            '<small>יום ' + esc(p.weekday) + ' · ' + p.days_before_event + ' ימים לפני האירוע' +
            '</small></span>' +
            '<span class="dt">' + heb(p.date) + '</span></li>';
        }).join('');

        var warn = d.compressed
          ? '<p class="calc-note"><b>שימו לב:</b> נשאר מעט זמן, ולכן הלוח דחוס. השלבים נשמרו, אבל הפערים ביניהם קצרים מהרגיל.</p>'
          : '';

        out.innerHTML =
          '<div class="calc-headline"><span class="lbl">מועד סגירת הרשימה</span>' +
          '<span class="big">' + heb(d.commitment_date) + '</span>' +
          '<p>יום ' + esc(d.commitment_weekday) + '. זה גם היום של סבב המעקב האחרון, וגם היום שבו מוסרים לאולם מספר.</p></div>' +
          '<div class="numcard"><div class="numcard-head"><h3>שבעת השלבים</h3><span class="numcard-tag">נפרסים לאחור</span></div>' +
          '<ul class="tl-list" style="padding:6px 18px">' + items + '</ul></div>' + warn;
      }`

  return page({
    path: '/calculators/rsvp-timeline/',
    title: 'מחשבון לוח זמנים לאישורי הגעה | VEYA',
    description:
      'מזינים תאריך אירוע ומקבלים את לוח הזמנים המלא של אישורי ההגעה: בקשה, שלוש תזכורות ושלושה סבבי מעקב — נפרסים לאחור ממועד סגירת הרשימה, בלי שישי ושבת.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים', url: '/calculators/' }, { name: 'לוח זמנים' }],
    faq,
    schema: [
      {
        '@type': 'WebApplication',
        name: 'מחשבון לוח זמנים לאישורי הגעה',
        applicationCategory: 'BusinessApplication',
        operatingSystem: 'Web',
        inLanguage: 'he-IL',
        url: `${SITE}/calculators/rsvp-timeline/`,
        description: 'פריסת שלבי אישורי ההגעה לאחור ממועד סגירת הרשימה.',
      },
    ],
    body,
    scripts: `    <script>\n      window.VEYA_API = ${JSON.stringify(API_URL)};\n${script}\n    </script>`,
  })
}

/* ════════════════════════════════════════════════════════════════════
   /features/finance — עמוד הכסף המרכזי
   ════════════════════════════════════════════════════════════════════ */

function featureFinance() {
  const faq = [
    {
      q: 'מה בדיוק VEYA מחשבת בצד הכספי?',
      a: 'את עלות האירוע לפי סעיפי ההוצאה שהזנתם ומספר המגיעים בפועל, את ההתחייבות מול הספק, את העלות הממוצעת לאדם, את מה שהתקבל במתנות אחרי האירוע, ואת ההפרש ביניהם.',
    },
    {
      q: 'איך העלות מתעדכנת לבד?',
      a: 'סעיף שמוגדר "לפי מספר המגיעים" נגזר מאישורי ההגעה באותה מערכת. כשעוד מוזמן מאשר, העלות זזה — בלי שתזינו שוב כלום.',
    },
    {
      q: 'מה ההבדל בין "לפי מגיעים" ל"לפי מוזמנים"?',
      a: 'מנה באולם משולמת לפי מי שהגיע. הזמנה מודפסת או מעטפה נקנות לפי מי שהוזמן. אלה שתי כמויות שונות, ולכן הן שתי שיטות חישוב נפרדות.',
    },
    {
      q: 'האם VEYA מנהלת ספקים?',
      a: 'לא. לכל שורת הוצאה יש שדה חופשי לזכור מול מי סוכם, אבל אין כאן ניהול חוזים, חשבוניות או תיקי ספקים.',
    },
    {
      q: 'מתי אפשר להתחיל לספור מתנות?',
      a: 'ספירת המתנות נפתחת מיום האירוע ואילך. מעטפה שעדיין לא שויכה למוזמן נשארת מסומנת כ"עדיין לא נספרה" — ולא הופכת ל"לא נתן".',
    },
    {
      q: 'מה קורה אם אין לי עדיין את כל המספרים?',
      a: 'כל שורה נפתחת כהערכה, ואתם מסמנים "סוכם" רק כשבאמת סוכם. אפשר גם לסמן תשלום חלקי, כמו מקדמה לאולם.',
    },
  ]

  const body = `${pageHero({
    eyebrow: 'מאזן האירוע',
    h1: 'כמה האירוע שלכם באמת עולה?',
    lead: 'ההוצאה הגדולה באירוע ישראלי לא נקבעת בטבלה — היא נקבעת במספר האנשים שמגיעים. VEYA מחברת בין אישורי ההגעה, ההתחייבות לאולם וסעיפי ההוצאה, עד לשורה התחתונה אחרי האירוע.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מאזן האירוע' }],
    cta: `${CTA_PRIMARY}\n            <a href="/calculators/venue-commitment/" class="btn btn-ghost">לחשב את ההתחייבות</a>`,
  })}

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">השרשרת</span>
            <h2 class="section-title">מוזמנים ← מגיעים ← התחייבות ← הוצאה ← מתנות ← שורה תחתונה</h2>
            <p class="why-list">
              רוב הכלים עוצרים בשלב השני. אחרי שהמוזמן ענה, המספר שלו הופך לעמודה בטבלה
              ונשאר שם. אצלנו הוא ממשיך: הוא קובע כמה מנות מחייבים אתכם, כמה שולחנות
              צריך, וכמה עולה בסוף האירוע.
            </p>
            <p class="why-punch">אישור הגעה אחד משנה מספר בשקלים.</p>
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">איך זה מחושב</span>
            <h2 class="section-title">ארבע דרכים לחשב הוצאה, כי לא הכול נמכר אותו דבר</h2>
            <p class="section-sub">
              לכל שורת הוצאה בוחרים איך היא מחושבת. מכאן נגזר הכול — הסיכום, העלות
              לאדם, והתשובה לשאלה כמה מוסיף אדם נוסף.
            </p>
          </div>
          <div class="supporting-grid">
            <article class="supporting-item">
              <h3>סכום קבוע</h3>
              <p>צילום, שמלה, DJ. לא זז עם מספר האנשים.</p>
            </article>
            <article class="supporting-item">
              <h3>לפי מספר המגיעים</h3>
              <p>מנה, אלכוהול. כאן חיה גם ההתחייבות מול הספק.</p>
            </article>
            <article class="supporting-item">
              <h3>לפי מספר המוזמנים</h3>
              <p>הזמנה מודפסת, מעטפה, משלוח — נקנים לפי מי שהוזמן.</p>
            </article>
            <article class="supporting-item">
              <h3>לפי יחידה או באחוזים</h3>
              <p>מספרי שולחן, הסעות. וטיפים שנגזרים משאר ההוצאות ומתעדכנים איתן.</p>
            </article>
          </div>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">ההתחייבות</span>
            <h2 class="section-title">ההתחייבות לאולם היא חלק מהחשבון, לא הערה בצד</h2>
            <p class="section-sub">
              אולם ישראלי נמכר כמעט תמיד בהתחייבות למספר מנות מינימלי. זה לא פרט טכני —
              זה מה שקובע כמה תשלמו.
            </p>
          </div>

          <div class="numcard">
            <div class="numcard-head">
              <h3>איך זה נראה בפועל</h3>
              <span class="numcard-tag">דוגמה</span>
            </div>
            <dl>
              <div class="numrow"><dt>התחייבתם בחוזה על</dt><dd>500 מנות</dd></div>
              <div class="numrow"><dt>אישרו הגעה</dt><dd>463 אנשים</dd></div>
              <div class="numrow is-key"><dt>משלמים על</dt><dd>500 מנות</dd></div>
            </dl>
            <p class="numcard-note">
              מנות לחיוב הן <b>הגבוה מבין מספר המגיעים לכמות ההתחייבות</b>. אם החוזה
              נוקב גם במינימום כספי — נספר הגבוה מבין השניים.
            </p>
          </div>

          <div class="steps-two">
            <div class="step-two">
              <span class="lbl">מתחת להתחייבות</span>
              <span class="big">המנה כבר משולמת</span>
              <p>אדם נוסף לא מוסיף על המנה. רק הוצאות אחרות לאדם, אם יש.</p>
            </div>
            <div class="step-two">
              <span class="lbl">מעל ההתחייבות</span>
              <span class="big">מחיר מנה מלא</span>
              <p>מכאן כל אדם נספר במלוא המחיר. זו המדרגה שמשנה את החשבון.</p>
            </div>
          </div>

          <p class="fineprint">
            המספרים בדוגמה להמחשה בלבד. החישוב רץ על הנתונים שאתם מזינים מהחוזה שלכם.
          </p>

          <div class="section-cta">
            <a href="/calculators/venue-commitment/" class="btn btn-primary">לחשב את ההתחייבות <span class="arw" aria-hidden="true">←</span></a>
            <span class="cta-hint">אותו חישוב, פתוח, בלי הרשמה.</span>
          </div>
        </div>
      </section>

      <section class="after tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">אחרי האירוע</span>
            <h2 class="section-title">ואז מגיעה המעטפה הראשונה</h2>
            <p class="section-sub">
              ספירת המתנות נפתחת מיום האירוע. כל מעטפה מקבלת מספר רץ, אפשר לשייך אותה
              למוזמן — או להשאיר אותה לא משויכת ולחזור אליה.
            </p>
          </div>

          <div class="numcard">
            <div class="numcard-head">
              <h3>דוח סיום האירוע</h3>
              <span class="numcard-tag">מה מוצג</span>
            </div>
            <dl>
              <div class="numrow"><dt>כמה אנשים הגיעו בפועל</dt><dd>מהרשימה</dd></div>
              <div class="numrow"><dt>סך ההוצאות</dt><dd>לפי הסעיפים שהזנתם</dd></div>
              <div class="numrow"><dt>כמה כבר שולם, וכמה נשאר</dt><dd>כולל מקדמות</dd></div>
              <div class="numrow"><dt>סך המתנות שנספרו</dt><dd>מעטפה אחר מעטפה</dd></div>
              <div class="numrow"><dt>עלות בפועל לאדם</dt><dd>על כל ההוצאות, לא רק המנה</dd></div>
              <div class="numrow is-key"><dt>השורה התחתונה</dt><dd>הכנסות פחות הוצאות</dd></div>
            </dl>
            <p class="numcard-note">
              יש גם פילוח שדוח רגיל לא נותן: <b>כמה התקבל ממי שהגיע מול ממי שלא הגיע</b>.
              זו חלוקה תיאורית לדוח, לא שיפוט של אף אחד.
            </p>
          </div>
        </div>
      </section>

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">מה שלא נמצא כאן</span>
            <h2 class="section-title">כדי שיהיה ברור</h2>
            <p>
              אין ניהול ספקים, אין חוזים ואין חשבוניות — לכל שורה יש שדה חופשי לזכור מול
              מי סוכם, וזה הכול. אין קטלוג מחירים ואין הערכה של כמה עולה מנה: המערכת
              מחשבת לפי מה שאתם מזינים, ולא מנחשת מחירי שוק מטעמכם.
            </p>
            <p class="why-punch">מספר מומצא במסך כספי גרוע מהיעדרו.</p>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>הגיע הזמן להפסיק לנחש את המספר</h2>
            <p class="band-more">
              מתחילים עם רשימת המוזמנים ומגיעים לאירוע עם תמונה ברורה יותר של האנשים,
              ההושבה והכסף.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: '/features/finance/',
    title: 'מאזן האירוע — כמה האירוע שלכם באמת עולה | VEYA',
    description:
      'עלות האירוע לפי מספר המגיעים בפועל, ההתחייבות לאולם, העלות לאדם וספירת המתנות אחרי האירוע — עד לשורה התחתונה. כך VEYA מחברת בין אישורי ההגעה לכסף.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מאזן האירוע' }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: 'מאזן האירוע',
        inLanguage: 'he-IL',
        url: `${SITE}/features/finance/`,
        description: 'מסך מאזן האירוע ב-VEYA: הוצאות לפי מספר המגיעים, התחייבות לאולם, עלות לאדם, ספירת מתנות ושורה תחתונה.',
      },
    ],
    body,
  })
}

/* ════════════════════════════════════════════════════════════════════
   /events/<type> — עמוד לכל סוג אירוע

   העמודים האלה אינם "עמודי SEO דקים": התוכן שלהם (קבוצות המוזמנים
   ותבנית ההוצאות) מגיע ממה שהמערכת באמת עושה אחרת בכל סוג אירוע.
   ════════════════════════════════════════════════════════════════════ */

function eventPage(t) {
  const groups = GROUPS[t.slug] || []
  const expenses = EXPENSES[t.slug] || []

  const faq = [
    {
      q: `במה ${t.the} שונה מסוגי אירוע אחרים במערכת?`,
      a: `זו אותה מערכת, אבל השפה, קבוצות ה${t.guests} ותבנית ההוצאות מותאמות ${pref("ל", t.the)}. אין כאן "מצב חתונה" עם כותרת אחרת.`,
    },
    {
      q: `אילו קבוצות ${t.guests} יש ${pref("ב", t.the)}?`,
      a: groups.length
        ? `${groups.join(', ')} — ואפשר לשייך כל מוזמן לקבוצה שמתאימה לו.`
        : 'אפשר ליצור קבוצות שמתאימות לאירוע שלכם.',
    },
    {
      q: 'האם אפשר לנהל כמה אירועים באותו חשבון?',
      a: 'כן. כל אירוע עומד בפני עצמו — רשימה משלו, לוח זמנים משלו ותמונה כספית משלו.',
    },
    {
      q: 'מי עוד יכול לגשת לאירוע?',
      a: 'אפשר לצרף בן/בת זוג, בני משפחה או מפיק, כך שכולם עובדים על אותה רשימה.',
    },
  ]

  const body = `${pageHero({
    eyebrow: t.name,
    h1: esc(t.title),
    lead: esc(t.lead),
    trail: [{ name: 'VEYA', url: '/' }, { name: 'סוגי אירוע', url: '/#events' }, { name: t.name }],
    cta: `${CTA_PRIMARY}\n            <a href="/calculators/venue-commitment/" class="btn btn-ghost">לחשב את ההתחייבות</a>`,
  })}

      <section class="commit tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">${esc(t.name)}</span>
            <h2 class="section-title">${esc((FOCUS[t.slug] || {}).line || '')}</h2>
          </div>
          <div class="num-row" data-v-stagger="90" style="max-width:660px;margin:0 auto">
${((FOCUS[t.slug] || {}).stats || []).map(([v, l]) => `            <div class="num v-reveal"><span class="num-value">${esc(v)}</span><span class="num-label">${esc(l)}</span></div>`).join('\n')}
          </div>
          <p class="fineprint" style="text-align:center">מספרי הדוגמה להמחשה בלבד — המערכת עובדת על הנתונים שלכם.</p>
          <div class="note-chips" style="justify-content:center;margin-top:22px">
${((FOCUS[t.slug] || {}).chips || []).map((c) => `            <span class="note-chip">${esc(c)}</span>`).join('\n')}
          </div>
        </div>
      </section>

      <section class="why">
        <div class="wrap">
          <div class="why-inner">
            <span class="kicker">מה מיוחד כאן</span>
            <h2 class="section-title">${esc('למה ' + t.the + (t.gender === 'f' ? ' לא מתנהלת' : ' לא מתנהל') + ' כמו כל אירוע אחר')}</h2>
${t.angle.map((para) => `            <p>${esc(para)}</p>`).join('\n')}
          </div>
        </div>
      </section>

      <section class="features tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">בפועל</span>
            <h2 class="section-title">${esc('שלושה דברים שהמערכת עושה אחרת ' + pref('ב', t.the))}</h2>
          </div>
          <div class="supporting-grid">
${t.highlights.map(([h, p]) => `            <article class="supporting-item"><h3>${esc(h)}</h3><p>${esc(p)}</p></article>`).join('\n')}
          </div>
        </div>
      </section>

      <section class="commit tone-light">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">${esc(t.guests)}</span>
            <h2 class="section-title">${esc('קבוצות ה' + t.guests + ' של ' + t.the)}</h2>
            <p class="section-sub">
              הקבוצות האלה אינן תווית בלבד — הן מזינות את הסינון, את הסטטיסטיקות
              ואת סידור ההושבה.
            </p>
          </div>
          <div class="evt-grid" style="max-width:820px;margin:0 auto">
${groups.map((g) => `            <div class="evt-card" style="text-align:center"><h3 style="margin:0">${esc(g)}</h3></div>`).join('\n')}
          </div>
        </div>
      </section>

      <section class="after tone-alt">
        <div class="wrap">
          <div class="section-head">
            <span class="kicker">מאזן האירוע</span>
            <h2 class="section-title">${esc('תבנית ההוצאות של ' + t.the)}</h2>
            <p class="section-sub">
              כשפותחים אירוע מהסוג הזה, אלה הסעיפים שמוצעים מיד. אפשר להוסיף,
              למחוק ולשנות הכול — זו נקודת פתיחה, לא רשימה סגורה.
            </p>
          </div>
          <div class="numcard" style="max-width:660px">
            <div class="numcard-head">
              <h3>${esc('מוצע מיד ' + pref('ב', t.the))}</h3>
              <span class="numcard-tag">ברירת מחדל</span>
            </div>
            <dl>
${expenses.map(([cat, items]) => `              <div class="numrow"><dt>${esc(cat)}</dt><dd style="font-weight:500;font-size:15px;color:var(--body)">${esc(items.join(' · '))}</dd></div>`).join('\n')}
            </dl>
            <p class="numcard-note">
              סעיף שנמכר בהתחייבות — מנה או קייטרינג — נושא גם את
              <b>כמות ההתחייבות והמינימום הכספי</b>, ולכן העלות שלו מחושבת נכון
              גם כשמגיעים פחות אנשים ממה שהתחייבתם.
            </p>
          </div>
          <div class="section-cta">
            <a href="/features/finance/" class="btn btn-ghost">לעמוד המאזן</a>
          </div>
        </div>
      </section>

${faqHtml(faq)}

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>${esc('פותחים ' + t.name + ' ומתחילים מהרשימה')}</h2>
            <p class="band-more">
              בוחרים את סוג האירוע בפתיחה, והמערכת מתאימה את עצמה — השפה,
              הקבוצות, ההודעות ותבנית ההוצאות.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  return page({
    path: `/events/${t.slug}/`,
    title: `${t.title} | VEYA`,
    description: t.description,
    trail: [{ name: 'VEYA', url: '/' }, { name: 'סוגי אירוע', url: '/#events' }, { name: t.name }],
    faq,
    schema: [
      {
        '@type': 'WebPage',
        name: t.title,
        inLanguage: 'he-IL',
        url: `${SITE}/events/${t.slug}/`,
        description: t.description,
      },
    ],
    body,
  })
}

/* ════════════════════════════════════════════════════════════════════
   sitemap
   ════════════════════════════════════════════════════════════════════ */

/* llms.txt — אינדקס קריא ל-crawlers של AI. הוא נגזר מאותה רשימת נתיבים
   שממנה נבנה ה-sitemap, ולכן הוא לא יכול להיפרד ממנה. גוגל מתעלמת ממנו
   במפורש; הוא כאן עבור crawlers אחרים, ולא כתחליף ל-HTML ול-schema. */
function llmsTxt(routes) {
  const group = (label, filter) => {
    const rows = routes.filter(filter).map((r) => `- [${titles.get(r) || r}](${SITE}${r})`)
    return rows.length ? `\n## ${label}\n${rows.join('\n')}\n` : ''
  }
  return `# VEYA

> VEYA מלווה אירוע מהמוזמן הראשון ועד השורה התחתונה: רשימת מוזמנים,
> אישורי הגעה, סידור הושבה ומאזן האירוע. שבעה סוגי אירוע: חתונה,
> בר מצווה, בת מצווה, חינה, ברית, בריתה ואירוע עסקי. בעברית, בישראל.
${group('יכולות', (r) => r.startsWith('/features/'))}${group('מחשבונים', (r) => r.startsWith('/calculators/'))}${group('סוגי אירוע', (r) => r.startsWith('/events/'))}${group('מדריכים', (r) => r.startsWith('/guides/'))}${group('הודעות למוזמנים', (r) => r.startsWith('/nuschim'))}
## תנאים ומדיניות
- [תנאי שימוש](${SITE}/legal/terms.html)
- [מדיניות פרטיות](${SITE}/legal/privacy.html)
- [מדיניות AI](${SITE}/legal/ai-policy.html)
`
}

/* בעברית אות היחס ב/ל/כ בולעת את ה' הידיעה: ב + החתונה = בחתונה, לא
   "בהחתונה". שדה `the` בלקסיקון כבר מיודע, ולכן כל שרשור ידני יצר שגיאה
   דקדוקית. הפונקציה הזו היא המקום היחיד שמותר לחבר בו אות יחס למונח. */
function pref(letter, definite) {
  return letter + (definite.startsWith('ה') ? definite.slice(1) : definite)
}

function sitemap(routes) {
  const today = new Date().toISOString().slice(0, 10)
  const url = (loc, priority, freq) =>
    `  <url>\n    <loc>${SITE}${loc}</loc>\n    <lastmod>${today}</lastmod>\n    <changefreq>${freq}</changefreq>\n    <priority>${priority}</priority>\n  </url>`

  const entries = [
    url('/', '1.0', 'weekly'),
    ...routes.map((r) => {
      if (r.startsWith('/features/')) return url(r, '0.9', 'monthly')
      if (r === '/calculators/') return url(r, '0.8', 'monthly')
      if (r.startsWith('/calculators/')) return url(r, '0.9', 'monthly')
      if (r.startsWith('/events/')) return url(r, '0.8', 'monthly')
      if (r === '/nuschim/') return url(r, '0.8', 'weekly')
      if (r.startsWith('/nuschim/')) return url(r, '0.7', 'weekly')
      if (r === '/guides/') return url(r, '0.7', 'weekly')
      return url(r, '0.6', 'monthly')
    }),
  ]
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries.join('\n')}\n</urlset>\n`
}

/* ════════════════════════════════════════════════════════════════════
   main
   ════════════════════════════════════════════════════════════════════ */

const guides = loadGuides()

emit('/features/finance/', featureFinance())
emit('/features/rsvp/', featureRsvp())
emit('/features/calls/', featureCalls())
emit('/features/guests/', featureGuests())
emit('/features/seating/', featureSeating())
emit('/calculators/', calcIndex())
emit('/calculators/venue-commitment/', calcVenueCommitment())
emit('/calculators/rsvp-timeline/', calcRsvpTimeline())
for (const t of EVENT_TYPES) emit(`/events/${t.slug}/`, eventPage(t))
emit('/guides/', guidesIndex(guides))
for (const g of guides) emit(`/guides/${g.slug}/`, guideHtml(g))

// ספריית הנוסחים נבנית אחרונה: היא קוראת לשרת, ולכן היא היחידה שיכולה
// להיכשל מסיבה חיצונית. כישלון שלה לא מפיל את שאר העמודים.
for (const p of await buildNuschim(API_URL)) emit(p.path, p.html)

writeFileSync(path.join(PUB, 'sitemap.xml'), sitemap(written))
console.log(`✓ sitemap.xml (${written.length + 1} כתובות)`)
writeFileSync(path.join(PUB, 'llms.txt'), llmsTxt(written))
console.log(`✓ llms.txt`)
console.log(`\nAPI לעמודי המחשבון: ${API_URL}`)
