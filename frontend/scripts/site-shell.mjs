/**
 * המעטפת המשותפת לכל עמוד ציבורי שאינו דף הבית.
 *
 * למה קובץ אחד: ה-header, ה-footer, תגיות המטא וה-Schema חייבים להיות
 * זהים בכל העמודים. אילו כל עמוד היה קובץ HTML שנכתב ביד, השורה
 * "כניסה למערכת" בפוטר הייתה מתחילה להשתנות בין עמוד לעמוד תוך חודש.
 *
 * דף הבית (`frontend/index.html`) **אינו** עובר דרך כאן בכוונה: הוא
 * שומר על ה-CSS המוטמע שלו מטעמי LCP. השינוי המשותף היחיד בין השניים
 * הוא הטוקנים — ראו ההערה בראש `public/veya-site.css`.
 */

export const SITE = 'https://veyaguest.co.il'

const LOGO_SVG = `<svg class="header-logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 212 64" width="212" height="64" fill="none" direction="ltr" role="img" aria-label="VEYA">
            <g>
              <circle cx="32" cy="32" r="27" stroke="#C9A227" stroke-width="1.5"/>
              <circle cx="32" cy="32" r="22.5" stroke="#C9A227" stroke-width="0.75" stroke-opacity="0.45"/>
              <path d="M32 1.2 L35 5 L32 8.8 L29 5 Z" fill="#C9A227"/>
              <text x="32" y="44" font-family="'Cormorant Garamond', Georgia, 'Times New Roman', serif" font-size="34" font-weight="600" fill="#E4C96B" text-anchor="middle">V</text>
            </g>
            <text x="74" y="42.5" font-family="'Cormorant Garamond', Georgia, 'Times New Roman', serif" font-size="32" font-weight="600" letter-spacing="9" fill="#F5EFE2">VEYA</text>
          </svg>`

export const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/** פירורי לחם — גם ויזואלית וגם כ-Schema, ממקור אחד. */
function crumbsHtml(trail) {
  if (!trail?.length) return ''
  const parts = trail.map((c) => (c.url ? `<a href="${c.url}">${esc(c.name)}</a>` : esc(c.name)))
  return `<p class="crumbs">${parts.join('<span aria-hidden="true">›</span>')}</p>`
}

function breadcrumbSchema(trail, path) {
  const items = [{ name: 'VEYA', url: '/' }, ...trail.filter((c) => c.name !== 'VEYA')]
  return {
    '@type': 'BreadcrumbList',
    itemListElement: items.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: c.name,
      item: SITE + (c.url || path),
    })),
  }
}

function faqSchema(faq) {
  if (!faq?.length) return null
  return {
    '@type': 'FAQPage',
    mainEntity: faq.map((q) => ({
      '@type': 'Question',
      name: q.q,
      acceptedAnswer: { '@type': 'Answer', text: q.a },
    })),
  }
}

/** בלוק ה-FAQ הגלוי. אותו מקור נתונים כמו ה-Schema — לעולם לא שניים. */
export function faqHtml(faq, { heading = 'שאלות נפוצות' } = {}) {
  if (!faq?.length) return ''
  const chev = `<span class="chev" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg></span>`
  return `<section class="faq-wrap" aria-labelledby="faq-title">
      <div class="wrap">
        <div class="section-head">
          <span class="kicker">${esc(heading)}</span>
          <h2 id="faq-title" class="section-title">מה שכדאי לדעת</h2>
        </div>
        <div class="faq">
${faq.map((q) => `          <details>
            <summary>${esc(q.q)}${chev}</summary>
            <p>${q.a}</p>
          </details>`).join('\n')}
        </div>
      </div>
    </section>`
}

/**
 * @param {object} o
 * @param {string} o.path      נתיב ציבורי עם / בסוף, למשל "/guides/xyz/"
 * @param {string} o.title     ה-<title> המלא
 * @param {string} o.description meta description
 * @param {string} o.body      ה-HTML של <main>
 * @param {Array}  [o.trail]   פירורי לחם
 * @param {Array}  [o.schema]  צמתים נוספים ל-@graph
 * @param {string} [o.head]    תגיות/סגנון נוספים ל-<head>
 */
export function page(o) {
  const url = SITE + o.path
  const graph = [
    ...(o.schema || []),
    breadcrumbSchema(o.trail || [], o.path),
    faqSchema(o.faq),
  ].filter(Boolean)

  return `<!doctype html>
<html lang="he" dir="rtl">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#2b2620" />
    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1" />
    <link rel="canonical" href="${url}" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />

    <title>${esc(o.title)}</title>
    <meta name="description" content="${esc(o.description)}" />

    <meta property="og:type" content="${o.ogType || 'website'}" />
    <meta property="og:site_name" content="VEYA" />
    <meta property="og:locale" content="he_IL" />
    <meta property="og:title" content="${esc(o.title)}" />
    <meta property="og:description" content="${esc(o.description)}" />
    <meta property="og:url" content="${url}" />
    <meta property="og:image" content="${SITE}/og-image.png?v=3" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:image:alt" content="VEYA — מערכת לניהול אירועים" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${esc(o.title)}" />
    <meta name="twitter:description" content="${esc(o.description)}" />
    <meta name="twitter:image" content="${SITE}/og-image.png?v=3" />

    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700&family=Frank+Ruhl+Libre:wght@400;500;700&family=Cormorant+Garamond:wght@500;600&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/veya-site.css" />

    <script type="application/ld+json">
${JSON.stringify({ '@context': 'https://schema.org', '@graph': graph }, null, 2)
  .split('\n').map((l) => '      ' + l).join('\n')}
    </script>
${o.head || ''}
  </head>
  <body>
    <header class="site-header on-dark">
      <div class="wrap">
        <a href="/" aria-label="VEYA — דף הבית">
          ${LOGO_SVG}
        </a>
        <div class="header-actions">
          <a href="/app" class="link-quiet" aria-label="כניסה למערכת">כניסה<span class="lq-long"> למערכת</span></a>
          <a href="/app?auth=register" class="btn btn-primary">מתחילים לתכנן <span class="arw" aria-hidden="true">←</span></a>
        </div>
      </div>
    </header>

    <main>
${o.body}
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <div class="footer-brand">
          ${LOGO_SVG.replace('class="header-logo"', 'class="footer-logo"')}
          <span class="footer-tag">מערכת לניהול אירועים — מוזמנים, אישורי הגעה, הושבה ומאזן האירוע במקום אחד.</span>
        </div>
        <nav aria-label="ניווט תחתון">
          <a href="/features/finance/">מאזן</a>
          <a href="/calculators/">מחשבונים</a>
          <a href="/guides/">מדריכים</a>
          <a href="/">דף הבית</a>
          <a href="/app">כניסה למערכת</a>
        </nav>
        <nav aria-label="קישורים משפטיים">
          <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">תנאי שימוש</a>
          <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">מדיניות פרטיות</a>
          <a href="/legal/cookies.html" target="_blank" rel="noopener noreferrer">מדיניות Cookies</a>
          <a href="/legal/accessibility.html" target="_blank" rel="noopener noreferrer">הצהרת נגישות</a>
          <a href="/legal/about.html#contact" target="_blank" rel="noopener noreferrer">יצירת קשר</a>
        </nav>
      </div>
      <div class="wrap" style="margin-top: 24px; padding-top: 20px; border-top: 1px solid rgba(201,162,39,0.14); font-size: 13px; color: #9b907c;">
        © VEYA — מערכת לניהול אירועים
      </div>
    </footer>
    <script src="/veya-motion.js" defer></script>
${o.scripts || ''}
  </body>
</html>
`
}

/** כותרת עמוד פנימי, עם פירורי לחם. */
export function pageHero({ eyebrow, h1, lead, trail, cta }) {
  return `      <section class="page-hero">
        <div class="wrap">
          ${crumbsHtml(trail)}
          ${eyebrow ? `<span class="eyebrow">${esc(eyebrow)}</span>` : ''}
          <h1>${h1}</h1>
          ${lead ? `<p class="lead">${lead}</p>` : ''}
          ${cta ? `<div class="cta-row" style="margin-top:26px">${cta}</div>` : ''}
        </div>
      </section>`
}

export const CTA_PRIMARY =
  '<a href="/app?auth=register" class="btn btn-primary">מתחילים לתכנן <span class="arw" aria-hidden="true">←</span></a>'
