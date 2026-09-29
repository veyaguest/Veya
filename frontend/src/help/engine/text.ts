/**
 * רינדור טקסט עזרה: טוקנים → עברית סופית (HELP_CENTER_PLAN.md §6.2).
 *
 * כלל: טוקן שאי אפשר למלא (עובדה חסרה, כפתור שלא קיים) → ``null`` לכל
 * השורה. לא מציגים חצי-משפט ולא "undefined" — עדיף שהשורה לא תופיע.
 *
 * פונקציה טהורה — כל מה שתלוי בסביבה (לקסיקון, טקסטי כפתורים) מגיע ב-ctx.
 */
import type { Facts } from '../facts'

export interface TextTerms {
  /** "מוזמנים" / "משתתפים" (activeEventTerms().guestsLabel). */
  guests: string
  /** "מוזמן" / "משתתף". */
  guest: string
  /** "בני הזוג" / "המשפחה" / "מארגני האירוע"… (hostsLabel). */
  hosts: string
  /** "החתונה" / "אירוע בר המצווה" / "האירוע" (eventNoun). */
  event: string
}

export interface TextContext {
  facts: Facts
  terms: TextTerms
  /** טקסט כפתור מ-strings/he.ts לפי נתיב (``guests.addGuestButton``). */
  ui: (path: string) => string | undefined
}

const TOKEN = /\{([a-z]+)(?::([^}|]+))?(?:\|([^}]*))?\}/g

/** "29 באוקטובר" מתוך ``YYYY-MM-DD`` — בלי תלות באזור הזמן של המכשיר. */
export function hebrewDate(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return null
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return new Intl.DateTimeFormat('he-IL', {
    weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC',
  }).format(d)
}

function countText(n: number, forms: string | undefined, terms: TextTerms): string | null {
  if (!forms) return String(n)
  let one: string
  let many: string
  if (forms === 'guest' || forms.startsWith('guest:')) {
    // "מוזמן אחד" / "3 מוזמנים" — ועם אות יחס: "guest:ל" → "למוזמן אחד" /
    // "ל-3 מוזמנים" (מקף רק לפני מספר, כמו ב-strings/he.ts).
    const pre = forms.startsWith('guest:') ? forms.slice('guest:'.length) : ''
    one = `${pre}${terms.guest} אחד`
    many = pre ? `${pre}-# ${terms.guests}` : `# ${terms.guests}`
  } else {
    const parts = forms.split('|')
    if (parts.length !== 2) return null
    ;[one, many] = parts
  }
  return n === 1 ? one : many.replace('#', String(n))
}

/** מרנדר שורה אחת. ``null`` = אי אפשר להציג אותה נכון. */
export function renderText(template: string, ctx: TextContext): string | null {
  let failed = false
  const out = template.replace(TOKEN, (_all, kind: string, arg?: string, forms?: string) => {
    const fail = () => {
      failed = true
      return ''
    }
    switch (kind) {
      case 'guests':
        return ctx.terms.guests
      case 'guest':
        return ctx.terms.guest
      case 'hosts':
        return ctx.terms.hosts
      case 'event':
        return ctx.terms.event
      case 'ui': {
        const s = arg ? ctx.ui(arg) : undefined
        return typeof s === 'string' && s ? s : fail()
      }
      case 'n': {
        const v = arg ? ctx.facts[arg as keyof Facts] : undefined
        return typeof v === 'number' ? String(v) : fail()
      }
      case 'text': {
        const v = arg ? ctx.facts[arg as keyof Facts] : undefined
        return typeof v === 'string' && v ? v : fail()
      }
      case 'date': {
        const v = arg ? ctx.facts[arg as keyof Facts] : undefined
        const d = typeof v === 'string' ? hebrewDate(v) : null
        return d ?? fail()
      }
      case 'count': {
        const v = arg ? ctx.facts[arg as keyof Facts] : undefined
        const s = typeof v === 'number' ? countText(v, forms, ctx.terms) : null
        return s ?? fail()
      }
      default:
        return fail()
    }
  })
  return failed ? null : out
}

/** כל הטוקנים בשורה — לבדיקות השלמות (אילו עובדות/כפתורים היא צריכה). */
export function tokensOf(template: string): { kind: string; arg?: string; forms?: string }[] {
  return [...template.matchAll(TOKEN)].map((m) => ({ kind: m[1], arg: m[2], forms: m[3] }))
}
