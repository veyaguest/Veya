#!/usr/bin/env node
/**
 * ממיר את מסמכי legal/*.md לעמודי HTML סטטיים תחת frontend/public/legal/,
 * כדי שהפוטר (גם ב-index.html השיווקי וגם ב-Footer.tsx של האפליקציה) יוכל
 * לקשר אליהם בקישור אמיתי ועובד — בלי תלות בראוטר בצד הלקוח.
 *
 * הרצה: npm run build:legal (רץ גם אוטומטית לפני `npm run build`, ראו
 * package.json::prebuild). יש להריץ מחדש בכל פעם שמסמך ב-legal/ משתנה.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { marked } from 'marked'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const LEGAL_SRC = path.resolve(__dirname, '../../legal')
const OUT_DIR = path.resolve(__dirname, '../public/legal')

// מיפוי שם-קובץ-מקור → slug ציבורי (כתובת /legal/<slug>.html).
const DOCS = [
  ['01-terms-of-service.md', 'terms', 'תנאי שימוש'],
  ['02-privacy-policy.md', 'privacy', 'מדיניות פרטיות'],
  ['03-cookie-policy.md', 'cookies', 'מדיניות Cookies'],
  ['04-accessibility-statement.md', 'accessibility', 'הצהרת נגישות'],
  ['05-account-deletion-policy.md', 'account-deletion', 'מדיניות מחיקת חשבון'],
  ['07-about-page.md', 'about', 'אודות VEYA'],
  ['08-ai-policy.md', 'ai-policy', 'מדיניות בינה מלאכותית'],
  ['06-security-policy.md', 'security', 'מדיניות אבטחת מידע'],
]

// שמות-קובץ → slug, כדי לתרגם קישורים פנימיים בין המסמכים (למשל
// "(02-privacy-policy.md)") לקישורי HTML תקינים ("(/legal/privacy.html)").
const SLUG_BY_FILENAME = Object.fromEntries(DOCS.map(([file, slug]) => [file, slug]))

function rewriteInternalLinks(md) {
  return md.replace(/\]\(((?:\.\/)?\d{2}-[\w-]+\.md)(#[\w-]*)?\)/g, (_all, file, anchor = '') => {
    const clean = file.replace(/^\.\//, '')
    const slug = SLUG_BY_FILENAME[clean]
    return slug ? `](/legal/${slug}.html${anchor})` : `](${file}${anchor})`
  })
}

function pageTemplate({ title, bodyHtml }) {
  return `<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex" />
<title>${title} · VEYA</title>
<style>
  :root { color-scheme: light; }
  body {
    margin: 0; padding: 0 20px 64px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Heebo, Arial, sans-serif;
    background: #fbf9f5; color: #2a2420; line-height: 1.75; font-size: 16.5px;
  }
  .legal-topbar {
    max-width: 780px; margin: 0 auto; padding: 22px 0 10px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .legal-topbar a { color: #9a7b1f; text-decoration: none; font-weight: 600; font-size: 14.5px; }
  .legal-doc { max-width: 780px; margin: 0 auto; background: #fff; border: 1px solid #ece4d3;
    border-radius: 14px; padding: 40px clamp(20px, 5vw, 56px); }
  .legal-doc h1 { font-size: 1.7rem; margin-top: 0; }
  .legal-doc h2 { font-size: 1.28rem; margin-top: 2.1em; border-top: 1px solid #f0e9da; padding-top: 1em; }
  .legal-doc h3 { font-size: 1.08rem; margin-top: 1.6em; }
  .legal-doc a { color: #9a7b1f; }
  .legal-doc table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: 0.95em; }
  .legal-doc th, .legal-doc td { border: 1px solid #ece4d3; padding: 8px 10px; text-align: right; vertical-align: top; }
  .legal-doc th { background: #f7f2e8; }
  .legal-doc code { background: #f3ede0; padding: 1px 6px; border-radius: 5px; font-size: 0.92em; }
  .legal-doc hr { border: none; border-top: 1px solid #ece4d3; margin: 2em 0; }
  @media (prefers-color-scheme: dark) {
    body { background: #16130f; color: #e9e1d2; }
    .legal-doc { background: #1e1a14; border-color: #322c22; }
    .legal-doc h2 { border-top-color: #322c22; }
    .legal-doc th, .legal-doc td { border-color: #322c22; }
    .legal-doc th { background: #241f18; }
    .legal-doc code { background: #241f18; }
    .legal-doc hr { border-top-color: #322c22; }
  }
</style>
</head>
<body>
  <div class="legal-topbar">
    <a href="/">← חזרה ל-VEYA</a>
    <a href="/app">כניסה למערכת</a>
  </div>
  <article class="legal-doc">
    ${bodyHtml}
  </article>
</body>
</html>
`
}

/**
 * עמוד האודות הוא סיפור מותג, לא מסמך משפטי — ולכן תבנית משלו: בלי כרטיס
 * לבן, עם הטיפוגרפיה של האתר (Frank Ruhl Libre לכותרות, Assistant לגוף),
 * טור צר, הרבה אוויר וקו זהב דק שמפריד בין הפרקים. שאר המסמכים ב-DOCS
 * ממשיכים לקבל את התבנית המשפטית כרגיל.
 */
function aboutTemplate({ title, bodyHtml }) {
  return `<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1" />
<link rel="canonical" href="https://veyaguest.co.il/legal/about.html" />
<meta name="description" content="הסיפור של VEYA: מערכת ישראלית שמחברת בין רשימת המוזמנים, אישורי ההגעה, ההושבה ומאזן האירוע." />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="VEYA" />
<meta property="og:title" content="אודות VEYA" />
<meta property="og:description" content="הסיפור של VEYA: מערכת שמחברת את כל חלקי האירוע סביב אותה רשימת מוזמנים." />
<meta property="og:url" content="https://veyaguest.co.il/legal/about.html" />
<meta property="og:image" content="https://veyaguest.co.il/og-image.png?v=3" />
<title>${title} · VEYA</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700&family=Frank+Ruhl+Libre:wght@400;500&display=swap"
/>
<style>
  :root {
    color-scheme: light;
    --ivory: #fbf6ee; --charcoal: #2b2620; --body: #4a4438; --muted: #6a6252;
    --line: #e5dec9; --gold-deep: #6f5b26;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0 20px 96px; background: var(--ivory); color: var(--body);
    font-family: Assistant, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    font-size: 17px; line-height: 1.9;
  }
  .about-topbar {
    max-width: 680px; margin: 0 auto; padding: 22px 0 8px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .about-topbar a { color: var(--gold-deep); text-decoration: none; font-weight: 600; font-size: 14.5px; }
  .about-topbar a:hover { text-decoration: underline; text-underline-offset: 3px; }
  .about-topbar a:focus-visible { outline: 2px solid var(--gold-deep); outline-offset: 3px; border-radius: 4px; }
  .about-doc { max-width: 680px; margin: 0 auto; }
  .about-doc h1 {
    margin: clamp(28px, 6vw, 56px) 0 clamp(26px, 4vw, 44px);
    font-family: "Frank Ruhl Libre", Georgia, serif; font-weight: 500; line-height: 1.12;
    font-size: clamp(2.1rem, 6vw, 3.1rem); color: var(--charcoal);
  }
  /* כל פרק נפתח בקו זהב דק — ההפרדה היחידה, בלי מסגרות ובלי כרטיסים */
  .about-doc h2 {
    margin: clamp(48px, 7vw, 82px) 0 clamp(16px, 2vw, 22px); padding-top: clamp(24px, 3vw, 34px);
    border-top: 1px solid rgba(131, 106, 38, 0.3);
    font-family: "Frank Ruhl Libre", Georgia, serif; font-weight: 500; line-height: 1.25;
    font-size: clamp(1.45rem, 3.4vw, 2rem); color: var(--charcoal);
  }
  .about-doc p { margin: 0 0 1.2em; max-width: 34rem; }
  .about-doc ul { margin: 0 0 1.2em; padding-inline-start: 1.1em; }
  .about-doc li { margin-bottom: 0.4em; }
  .about-doc a { color: var(--gold-deep); }
  .about-doc hr { border: none; border-top: 1px solid var(--line); margin: clamp(40px, 5vw, 64px) 0 26px; }
  .about-doc hr + p { font-size: 15px; color: var(--muted); }
  @media (max-width: 600px) {
    body { font-size: 16.5px; line-height: 1.85; padding-bottom: 72px; }
    .about-doc p { max-width: none; }
  }
</style>
</head>
<body>
  <div class="about-topbar">
    <a href="/">← חזרה ל-VEYA</a>
    <a href="/app">כניסה למערכת</a>
  </div>
  <article class="about-doc">
    ${bodyHtml}
  </article>
</body>
</html>
`
}

mkdirSync(OUT_DIR, { recursive: true })

for (const [file, slug, title] of DOCS) {
  const srcPath = path.join(LEGAL_SRC, file)
  let md = readFileSync(srcPath, 'utf8')
  md = rewriteInternalLinks(md)
  if (file === '07-about-page.md') {
    // עוגן קבוע ל"יצירת קשר" בפוטר, בלי להסתמך על slugger אוטומטי של כותרות עבריות.
    md = md.replace('## דברו איתנו', '<a id="contact"></a>\n\n## דברו איתנו')
  }
  const bodyHtml = marked.parse(md, { gfm: true })
  const render = slug === 'about' ? aboutTemplate : pageTemplate
  writeFileSync(path.join(OUT_DIR, `${slug}.html`), render({ title, bodyHtml }))
  console.log(`✓ legal/${file} → public/legal/${slug}.html`)
}
