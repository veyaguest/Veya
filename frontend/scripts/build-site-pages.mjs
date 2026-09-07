#!/usr/bin/env node
/**
 * בונה את עמודי האתר הציבורי הסטטיים: מחשבונים, עמוד המוצר "כספי האירוע",
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

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const PUB = path.resolve(__dirname, '../public')
const GUIDES_SRC = path.resolve(__dirname, '../content/guides')

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000'

const written = []
function emit(routePath, html) {
  const dir = path.join(PUB, routePath.replace(/^\/|\/$/g, ''))
  mkdirSync(dir, { recursive: true })
  writeFileSync(path.join(dir, 'index.html'), html)
  written.push(routePath)
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
  B: { title: 'כספי האירוע', blurb: 'כמה האירוע עולה, כמה נכנס, ומה נשאר בסוף.' },
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

  const related = g.related?.length
    ? `<div class="guide-cluster">
          <h2 style="border:0;padding:0;margin-top:0">להמשך</h2>
          <ul class="guide-list">
${g.related.map((r) => `            <li><a href="${r.url}"><h3>${esc(r.title)}</h3></a></li>`).join('\n')}
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
    desc: 'מזינים כמה אישרו הגעה, על כמה התחייבתם ומה מחיר המנה — ורואים על כמה מנות באמת משלמים וכמה מוסיף כל אורח נוסף.',
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
      'מחשבונים חינמיים לאירוע: התחייבות לאולם, כמה מוסיף אורח נוסף, ולוח הזמנים של אישורי ההגעה. אותו חישוב שרץ בתוך VEYA.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'מחשבונים' }],
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

const CALC_JS = (extra) => `    <script>
      window.VEYA_API = ${JSON.stringify(API_URL)};
${extra}
    </script>`

writeFileSync // (no-op reference to keep imports honest in tooling)

export { CALCS, CLUSTERS, loadGuides, guideHtml, guidesIndex, calcIndex, CALC_JS, emit, written }
