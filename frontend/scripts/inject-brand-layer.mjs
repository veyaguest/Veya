#!/usr/bin/env node
/**
 * מזריק את `content/brand-layer.css` לשני היעדים שלו.
 *
 * שכבת המותג נכתבת במקום אחד, אבל צריכה לחיות בשניים: הגיליון המשותף
 * של העמודים הפנימיים, וה-CSS המוטמע של דף הבית (שנשאר מוטמע מטעמי LCP).
 * הסקריפט הזה הוא מה שמונע מהשניים להיפרד — הוא רץ בכל build.
 *
 * הבלוק מסומן בתגי START/END ומוחלף במלואו בכל הרצה, כך שהרצה חוזרת
 * אינה מכפילה אותו.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const LAYER = readFileSync(path.resolve(__dirname, '../content/brand-layer.css'), 'utf8')

const START = '/* ===== VEYA BRAND LAYER — START (generated, do not edit here) ===== */'
const END = '/* ===== VEYA BRAND LAYER — END ===== */'
const BLOCK = `${START}\n${LAYER}\n${END}`

function inject(text, indent = '') {
  const body = indent
    ? BLOCK.split('\n').map((l) => (l.trim() ? indent + l : l)).join('\n')
    : BLOCK
  const re = new RegExp(
    START.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[\\s\\S]*?' + END.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
  )
  return re.test(text) ? text.replace(re, () => body) : `${text.trimEnd()}\n\n${body}\n`
}

// 1) הגיליון המשותף
const sheetPath = path.resolve(__dirname, '../public/veya-site.css')
writeFileSync(sheetPath, inject(readFileSync(sheetPath, 'utf8')))

// 2) ה-<style> המוטמע של דף הבית
const homePath = path.resolve(__dirname, '../index.html')
const home = readFileSync(homePath, 'utf8')
const css = home.split('<style>')[1].split('</style>')[0]
writeFileSync(
  homePath,
  home.replace(`<style>${css}</style>`, `<style>${inject(css, '      ')}\n    </style>`),
)

console.log('✓ brand-layer הוזרק ל-veya-site.css ול-index.html')
