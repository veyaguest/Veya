/**
 * בדיקת זהות בין התצוגה המקדימה בדפדפן לרינדור בפועל בשרת.
 *
 * הרצה: `node src/lib/messagePreview.test.mjs` מתוך תיקיית frontend.
 * (סקריפט עצמאי עם assert, כמו שאר הבדיקות בפרויקט — אין runner.)
 *
 * למה זה קיים: הזוג עורך הודעה, רואה תצוגה מקדימה, ולוחץ "שליחה". אם
 * המנוע שמצייר את התצוגה והמנוע ששולח בפועל לא מסכימים — הזוג שולח למאות
 * מוזמנים משהו שהוא לא ראה. זה בדיוק מה שקרה עד הסבב הזה (טוקנים שהוצגו
 * כטקסט גולמי, שורות שנשארו בתצוגה ונמחקו בשליחה).
 *
 * הבדיקה מייבאת את המודול האמיתי (`messagePreview.ts`, מקומפל ב-esbuild)
 * ומשווה אותו מול פלט אמיתי של `render_automation_template` בפייתון,
 * שנוצר ע"י `messagePreview.fixtures.py` ונשמר ב-`messagePreview.fixtures.json`.
 * שינוי בכללי הרינדור בצד אחד בלי הצד השני — הבדיקה נכשלת.
 */
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'

const here = dirname(fileURLToPath(import.meta.url))
const fixturesPath = join(here, 'messagePreview.fixtures.json')

if (!existsSync(fixturesPath)) {
  console.error(
    'חסר קובץ ה-fixtures. הריצו קודם, מתוך backend:\n' +
      '  venv/bin/python ../frontend/src/lib/messagePreview.fixtures.py',
  )
  process.exit(1)
}

// מקמפלים את המודול האמיתי לזיכרון — לא מעתיקים את הלוגיקה לכאן, אחרת
// הבדיקה תבדוק את עצמה במקום את הקוד שרץ בפרודקשן.
const bundled = await build({
  entryPoints: [join(here, 'messagePreview.ts')],
  bundle: true,
  format: 'esm',
  write: false,
  platform: 'neutral',
  // eventTypes.ts גורר את authStore ואת ה-DOM; ממירים אותו ל-stub שמספק רק
  // את מה ש-buildSampleTokens באמת צריך.
  plugins: [
    {
      name: 'stub-event-terms',
      setup(b) {
        b.onResolve({ filter: /strings\/eventTypes$/ }, () => ({
          path: 'stub-event-terms',
          namespace: 'stub',
        }))
        b.onLoad({ filter: /.*/, namespace: 'stub' }, () => ({
          contents: `
            export function getEventTerms() { return {}; }
            export function hostNames() { return ''; }
          `,
          loader: 'js',
        }))
      },
    },
  ],
})

const mod = await import(
  'data:text/javascript;base64,' +
    Buffer.from(bundled.outputFiles[0].text).toString('base64')
)
const { renderMessagePreview } = mod

const { samples, cases } = JSON.parse(readFileSync(fixturesPath, 'utf8'))
let checked = 0
const failures = []

for (const f of cases) {
  const got = renderMessagePreview(f.body, samples[f.sample_id])
  if (got !== f.expected) {
    failures.push({ name: f.name, got, expected: f.expected })
  }
  checked++
}

if (failures.length > 0) {
  for (const f of failures.slice(0, 5)) {
    console.error(`\n✗ ${f.name}`)
    console.error(`  שרת:   ${JSON.stringify(f.expected)}`)
    console.error(`  דפדפן: ${JSON.stringify(f.got)}`)
  }
  console.error(`\n${failures.length} מתוך ${checked} תבניות אינן זהות.`)
  process.exit(1)
}

assert.ok(checked > 0, 'לא נבדקה אף תבנית — קובץ ה-fixtures ריק')
console.log(`✓ ${checked} תבניות: התצוגה המקדימה זהה בייט-לבייט לשליחה בפועל`)
