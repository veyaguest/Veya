/**
 * חיפוש שאלה — בלי AI (HELP_CENTER_PLAN.md §7.5).
 *
 * מנרמל עברית (ניקוד, אותיות סופיות, סימני פיסוק), מסיר קידומות נפוצות
 * (ו/ה/ב/ל/מ/ש/כ) ומילים שלא אומרות כלום ("איך", "מה"…), ומתאים מילים מול
 * הכותרת והניסוחים הנוספים של כל נושא/עץ. תוצאה בלי אף מילה משמעותית
 * משותפת — לא מוצגת.
 *
 * הטקסט שהמשתמש הקליד **לא נשמר ולא נשלח** לשום מקום (החלטת המייסד 2026-09-29).
 */

const NIQQUD = /[֑-ׇ]/g
const FINALS: Record<string, string> = { 'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ' }
const PREFIXES = ['ו', 'ה', 'ב', 'ל', 'מ', 'ש', 'כ']

/** מילים שלא מבדילות בין שאלות. */
const STOPWORDS = new Set(
  [
    'איך', 'מה', 'למה', 'מתי', 'איפה', 'האם', 'אני', 'אנחנו', 'את', 'של', 'עם', 'על', 'לא',
    'יש', 'אין', 'זה', 'זאת', 'אפשר', 'רוצה', 'רוצים', 'צריך', 'צריכים', 'או', 'גם', 'כל',
    'עוד', 'הוא', 'היא', 'הם', 'לי', 'לנו', 'שלי', 'שלנו', 'כמה', 'אחד', 'אחת',
  ].map((w) => normalizeWord(w)),
)

function normalizeWord(w: string): string {
  return w.replace(/[ךםןףץ]/g, (c) => FINALS[c] ?? c)
}

/** ניקוד, סופיות, אותיות לטיניות קטנות, רווחים במקום פיסוק. */
export function normalize(s: string): string {
  return normalizeWord(s.replace(NIQQUD, '').toLowerCase())
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

/** מילה + הצורה שלה בלי קידומת אחת או שתיים (רק במילים ארוכות מספיק). */
function forms(word: string): string[] {
  const out = [word]
  let w = word
  for (let i = 0; i < 2; i++) {
    if (w.length > 3 && PREFIXES.includes(w[0])) {
      w = w.slice(1)
      out.push(w)
    } else break
  }
  return out
}

export function meaningfulWords(s: string): string[] {
  return normalize(s)
    .split(' ')
    .filter((w) => w.length >= 2 && !STOPWORDS.has(w))
}

function wordMatches(q: string, candidates: readonly string[]): boolean {
  const qf = forms(q)
  return candidates.some((c) => {
    const cf = forms(c)
    if (qf.some((a) => cf.includes(a))) return true
    // הקלדה חלקית: "מוזמ" → "מוזמן"
    return q.length >= 3 && cf.some((x) => x.startsWith(q))
  })
}

export interface Searchable {
  id: string
  texts: readonly string[]
}

/**
 * מחזיר מזהים לפי ציון (מספר מילים משמעותיות שנמצאו), מהגבוה לנמוך.
 * שוויון → הסדר המקורי (יציב).
 */
export function search(query: string, items: readonly Searchable[]): string[] {
  const words = meaningfulWords(query)
  if (words.length === 0) return []
  const scored: { id: string; score: number; i: number }[] = []
  items.forEach((item, i) => {
    const candidates = item.texts.flatMap(meaningfulWords)
    const score = words.filter((w) => wordMatches(w, candidates)).length
    if (score > 0) scored.push({ id: item.id, score, i })
  })
  scored.sort((a, b) => b.score - a.score || a.i - b.i)
  return scored.map((s) => s.id)
}
