/**
 * כותב קובץ ``.xlsx`` אמיתי — בלי ספרייה חיצונית.
 *
 * ## למה לא SheetJS
 *
 * החבילה ``xlsx`` ב-npm **הוצאה משימוש** ונושאת התרעת אבטחה ברמה גבוהה
 * (``npm audit``). VEYA פרוסה בייצור, ותלות עם התרעה פתוחה בשביל כפתור
 * ייצוא היא עסקה גרועה. הגרסה המתוחזקת מתפרסמת רק מ-CDN של SheetJS —
 * כלומר קוד צד-שלישי שנטען בזמן ריצה, וזה סיכון אחר באותה עוצמה.
 *
 * הקובץ הזה הוא הדרך השלישית: ``xlsx`` הוא ZIP של קובצי XML, ושניהם
 * פשוטים מספיק לכתוב לבד. אפס תלויות, אפס משקל בבנדל המשותף, ושליטה
 * מלאה בכל בית שיוצא ללקוח.
 *
 * ## מה נתמך, ומה לא
 *
 * נתמך: כמה גיליונות, כותרות מודגשות, רוחב עמודות, יישור RTL לגיליון,
 * מספרים כמספרים (ולא כטקסט), ועברית מלאה ב-UTF-8.
 *
 * לא נתמך, ובכוונה: נוסחאות, מיזוג תאים, צבעים, גרפים. דוח כספי צריך
 * להיות קריא ולעבור לניתוח — לא להיות מצגת.
 *
 * ## דחיסה
 *
 * הקבצים נכתבים ללא דחיסה (שיטה 0 — ``STORE``). זה מייתר מימוש של
 * DEFLATE, ומחיר הגודל זניח: דוח של 600 מוזמנים הוא מאות קילובייטים,
 * וההורדה מקומית.
 */

/** תא בגיליון: מחרוזת, מספר, או ריק. */
export type Cell = string | number | null | undefined

export interface Sheet {
  /** שם הלשונית באקסל. נחתך ל-31 תווים — מגבלה של הפורמט. */
  name: string
  /** שורת הכותרות. מודגשת, וקופאת בראש הגיליון. */
  head: string[]
  rows: Cell[][]
  /** רוחב עמודות בתווים. חסר ⇒ רוחב ברירת מחדל. */
  widths?: number[]
}

// ── XML ───────────────────────────────────────────────────────────────

function esc(value: string): string {
  return value.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c] as string,
  )
}

/** ``0`` → ``A``, ``26`` → ``AA``. */
function columnName(index: number): string {
  let name = ''
  let n = index
  do {
    name = String.fromCharCode(65 + (n % 26)) + name
    n = Math.floor(n / 26) - 1
  } while (n >= 0)
  return name
}

function cellXml(cell: Cell, ref: string, styleId: number): string {
  const style = styleId ? ` s="${styleId}"` : ''
  if (cell === null || cell === undefined || cell === '') {
    return `<c r="${ref}"${style}/>`
  }
  // מספר נשמר כמספר — אחרת אקסל לא יסכם אותו, וזו כל הנקודה בייצוא
  // של דוח כספי. ``NaN``/``Infinity`` נופלים לטקסט ולא שוברים את הקובץ.
  if (typeof cell === 'number' && Number.isFinite(cell)) {
    return `<c r="${ref}"${style}><v>${cell}</v></c>`
  }
  return `<c r="${ref}"${style} t="inlineStr"><is><t xml:space="preserve">${esc(
    String(cell),
  )}</t></is></c>`
}

function sheetXml(sheet: Sheet): string {
  const cols = sheet.widths?.length
    ? `<cols>${sheet.widths
        .map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`)
        .join('')}</cols>`
    : ''

  const rows = [sheet.head, ...sheet.rows].map((row, r) => {
    const cells = row
      .map((cell, c) => cellXml(cell, `${columnName(c)}${r + 1}`, r === 0 ? 1 : 0))
      .join('')
    return `<row r="${r + 1}">${cells}</row>`
  })

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetPr><outlinePr/></sheetPr>
<sheetViews><sheetView rightToLeft="1" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="15"/>
${cols}
<sheetData>${rows.join('')}</sheetData>
</worksheet>`
}

// ── ZIP (שיטה 0 — בלי דחיסה) ─────────────────────────────────────────

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i++) {
    let c = i
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[i] = c >>> 0
  }
  return table
})()

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

interface Entry {
  name: string
  bytes: Uint8Array
  crc: number
  offset: number
}

function zip(files: { name: string; text: string }[]): Blob {
  const encoder = new TextEncoder()
  const chunks: Uint8Array[] = []
  const entries: Entry[] = []
  let offset = 0

  function push(bytes: Uint8Array) {
    chunks.push(bytes)
    offset += bytes.length
  }

  function u32(n: number) {
    return new Uint8Array([n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff])
  }
  function u16(n: number) {
    return new Uint8Array([n & 0xff, (n >>> 8) & 0xff])
  }
  function concat(...parts: Uint8Array[]) {
    const total = parts.reduce((n, p) => n + p.length, 0)
    const out = new Uint8Array(total)
    let at = 0
    for (const p of parts) {
      out.set(p, at)
      at += p.length
    }
    return out
  }

  for (const file of files) {
    const nameBytes = encoder.encode(file.name)
    const bytes = encoder.encode(file.text)
    const crc = crc32(bytes)
    entries.push({ name: file.name, bytes, crc, offset })

    push(
      concat(
        u32(0x04034b50), // local file header
        u16(20), // version needed
        u16(0x0800), // דגל UTF-8 לשמות הקבצים
        u16(0), // method 0 = STORE
        u16(0), // time
        u16(0), // date
        u32(crc),
        u32(bytes.length),
        u32(bytes.length),
        u16(nameBytes.length),
        u16(0),
        nameBytes,
      ),
    )
    push(bytes)
  }

  const centralStart = offset
  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name)
    push(
      concat(
        u32(0x02014b50), // central directory header
        u16(20),
        u16(20),
        u16(0x0800),
        u16(0),
        u16(0),
        u16(0),
        u32(entry.crc),
        u32(entry.bytes.length),
        u32(entry.bytes.length),
        u16(nameBytes.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(entry.offset),
        nameBytes,
      ),
    )
  }

  push(
    concat(
      u32(0x06054b50), // end of central directory
      u16(0),
      u16(0),
      u16(entries.length),
      u16(entries.length),
      u32(offset - centralStart),
      u32(centralStart),
      u16(0),
    ),
  )

  return new Blob(chunks as BlobPart[], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

// ── הרכבת החוברת ─────────────────────────────────────────────────────

/** שם לשונית חוקי: עד 31 תווים, בלי התווים שאקסל אוסר. */
function sheetName(name: string, index: number): string {
  const clean = name.replace(/[\\/?*[\]:]/g, ' ').trim().slice(0, 31)
  return clean || `גיליון ${index + 1}`
}

/**
 * בונה חוברת ומוריד אותה.
 *
 * ``fileName`` נמסר כמו שהוא — כולל הסיומת.
 */
export function downloadWorkbook(fileName: string, sheets: Sheet[]): void {
  const named = sheets.map((s, i) => ({ ...s, name: sheetName(s.name, i) }))

  const files = [
    {
      name: '[Content_Types].xml',
      text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
${named
  .map(
    (_, i) =>
      `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`,
  )
  .join('\n')}
</Types>`,
    },
    {
      name: '_rels/.rels',
      text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
    },
    {
      name: 'xl/workbook.xml',
      text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>${named
        .map(
          (s, i) =>
            `<sheet name="${esc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`,
        )
        .join('')}</sheets>
</workbook>`,
    },
    {
      name: 'xl/_rels/workbook.xml.rels',
      text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${named
  .map(
    (_, i) =>
      `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`,
  )
  .join('\n')}
<Relationship Id="rId${named.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`,
    },
    {
      // שני סגנונות בלבד: רגיל (0) וכותרת מודגשת (1).
      name: 'xl/styles.xml',
      text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`,
    },
    ...named.map((s, i) => ({
      name: `xl/worksheets/sheet${i + 1}.xml`,
      text: sheetXml(s),
    })),
  ]

  const url = URL.createObjectURL(zip(files))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}
