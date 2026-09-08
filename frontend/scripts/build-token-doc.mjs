#!/usr/bin/env node
/**
 * מפיק `frontend/DESIGN-TOKENS.md` מתוך ה-CSS עצמו.
 *
 * המסמך **נגזר ולא נכתב ביד** — כך הוא לא יכול להתיישן מול הקוד. אם טוקן
 * נוסף או משתנה ב-`content/brand-layer.css` או ב-`public/veya-site.css`,
 * ההרצה הבאה מעדכנת את הטבלה.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const css = readFileSync(path.resolve(__dirname, '../public/veya-site.css'), 'utf8')

// כל בלוקי :root מאוחדים — הצבעים מגיעים מבלוק אחד, הטוקנים החדשים מאחר
const tokens = new Map()
for (const m of css.matchAll(/:root\s*\{([\s\S]*?)\n\}/g)) {
  let comment = ''
  for (const line of m[1].split('\n')) {
    const c = line.match(/\/\*\s*(.*?)\s*\*\//)
    if (c && !line.includes('--')) { comment = c[1]; continue }
    const t = line.match(/(--[\w-]+):\s*([^;]+);/)
    if (t) tokens.set(t[1], { value: t[2].trim(), note: (line.match(/\/\*\s*(.*?)\s*\*\//) || [, ''])[1] })
  }
}

const GROUPS = [
  ['צבע — רקע ומשטח', ['--ivory', '--ivory-2', '--cream', '--ink', '--ink-2']],
  ['צבע — טקסט', ['--charcoal', '--body', '--muted', '--cream-text']],
  ['צבע — מותג', ['--gold', '--gold-light', '--gold-deep']],
  ['צבע — גבול', ['--line']],
  ['צבע — סמנטי', ['--success', '--warning', '--error', '--error-bg', '--error-border', '--green']],
  ['רדיוס', ['--radius-sm', '--radius-md', '--radius-lg', '--radius-xl', '--radius-pill']],
  ['צל', ['--shadow-sm', '--shadow-md', '--shadow-lg']],
  ['תנועה', ['--motion-fast', '--motion-normal', '--motion-slow', '--ease-out', '--ease-in-out']],
  ['גופן', ['--font-body', '--font-display', '--font-num']],
]

let out = `# VEYA — Design Tokens

> **מסמך נגזר.** נוצר אוטומטית מ-\`public/veya-site.css\` על ידי
> \`scripts/build-token-doc.mjs\`. אין לערוך אותו ביד — ערכו את
> \`content/brand-layer.css\` (טוקנים חדשים) והריצו \`npm run build:brand\`.

מקור האמת של הטוקנים הוא ה-CSS. המסמך הזה קיים כדי שאפשר יהיה לקרוא
אותם בלי לפתוח גיליון של ${css.split('{').length - 1} כללים.

`

for (const [title, keys] of GROUPS) {
  const rows = keys.filter((k) => tokens.has(k))
  if (!rows.length) continue
  out += `## ${title}\n\n| טוקן | ערך | הערה |\n|---|---|---|\n`
  for (const k of rows) {
    const t = tokens.get(k)
    out += `| \`${k}\` | \`${t.value}\` | ${t.note || ''} |\n`
  }
  out += '\n'
}

const listed = new Set(GROUPS.flatMap(([, k]) => k))
const rest = [...tokens.keys()].filter((k) => !listed.has(k))
if (rest.length) {
  out += `## נוספים\n\n${rest.map((k) => `\`${k}\``).join(' · ')}\n\n`
}

out += `## כללים

1. **אין hex בקומפוננטה.** צבע שנושא משמעות עובר דרך טוקן סמנטי.
2. **\`--green\` הוא לאייקון בלבד** — 3.16:1 מספיק לגרפיקה ולא לטקסט.
   טקסט הצלחה משתמש ב-\`--success\`.
3. **סולם הרדיוס סגור** לחמישה ערכים. אין להוסיף ערך שישי בלי סיבה.
4. **תנועה על transform/opacity בלבד**, ותמיד מתחת ל-\`prefers-reduced-motion\`.
`

writeFileSync(path.resolve(__dirname, '../DESIGN-TOKENS.md'), out)
console.log(`✓ DESIGN-TOKENS.md — ${tokens.size} טוקנים`)
