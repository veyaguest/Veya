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
  writeFileSync(path.join(OUT_DIR, `${slug}.html`), pageTemplate({ title, bodyHtml }))
  console.log(`✓ legal/${file} → public/legal/${slug}.html`)
}
