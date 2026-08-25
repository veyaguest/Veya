import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { BANKS, BANKS_SOURCE, BANK_BY_CODE, type Bank } from '../data/banks'
import { strings } from '../strings/he'
import './BankSelect.css'

const t = strings.payout.bank

/**
 * בורר בנק — מגירה עם חיפוש, מעל רשימת הבנקים הרשמית של בנק ישראל.
 *
 * **למה לא ``<select>`` רגיל:** שמונה־עשרה אפשרויות בעברית, שחלקן דומות
 * מאוד בשם ("בנק דיסקונט" מול "בנק מרכנתיל דיסקונט"), הן בדיוק המקרה שבו
 * רשימה נפתחת של הדפדפן נכשלת — אין בה חיפוש, אין בה קוד בנק, ובמובייל
 * היא גלגלת זעירה. כאן הזוג מקליד "פוע" או "12" ומגיע ישר.
 *
 * **ה"לוגו":** אריח עם **קוד הבנק**, לא סמל הבנק. סמלי הבנקים הם סימני
 * מסחר רשומים ואין לנו רישיון להשתמש בהם, ולכן לא הומצא כאן דמיון —
 * במקומו מוצג הנתון שהזוג ממילא משווה מול אישור ניהול החשבון שלו, והוא
 * גם מזהה ייחודי (בשונה מאות ראשונה: לשלושה בנקים יש "מ" ולשלושה "ה").
 * אם יתקבל רישיון, אפשר להוסיף שדה ``logo`` בלי לגעת בלוגיקה כאן.
 */

/** מנרמל לחיפוש: בלי גרשיים, מקפים ורווחים — "בנק פאג\"י" ≈ "פאגי". */
function norm(s: string): string {
  return s.toLowerCase().replace(/["'״׳\-\s.]/g, '')
}

function matches(bank: Bank, query: string): boolean {
  const q = norm(query)
  if (!q) return true
  // חיפוש לפי קוד עובד רק כשהשאילתה כולה ספרות, אחרת "1" היה תופס כל בנק
  // שיש בשמו את הספרה.
  if (/^\d+$/.test(q) && String(bank.code).startsWith(q)) return true
  return norm(bank.name).includes(q) || norm(bank.legalName).includes(q)
}

/** אריח קוד הבנק — ממלא את מקום הלוגו. */
function BankMark({ code, size }: { code: number; size?: 'sm' }) {
  return (
    <span className={`bank-mark${size === 'sm' ? ' bank-mark-sm' : ''}`} aria-hidden="true">
      {code}
    </span>
  )
}

export function BankSelect({
  value,
  onChange,
  invalid,
  describedBy,
}: {
  value: number | null
  onChange: (code: number) => void
  invalid?: boolean
  describedBy?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)

  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const selected = value != null ? BANK_BY_CODE.get(value) ?? null : null
  const results = useMemo(() => BANKS.filter((b) => matches(b, query)), [query])

  // בפתיחה: מתמקדים בשדה החיפוש ומסמנים את הבנק שכבר נבחר.
  useEffect(() => {
    if (!open) return
    setQuery('')
    const idx = selected ? BANKS.findIndex((b) => b.code === selected.code) : 0
    setActive(Math.max(0, idx))
    // במובייל אנחנו *לא* מתמקדים אוטומטית: פתיחת המקלדת מיד מכסה חצי מסך
    // ומסתירה את הרשימה שהמשתמש בא לראות. הוא ילחץ על החיפוש אם ירצה.
    if (window.matchMedia('(min-width: 601px)').matches) {
      requestAnimationFrame(() => searchRef.current?.focus())
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // סגירה בלחיצה בחוץ.
  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  // גלילת הפריט הפעיל לתוך התצוגה בניווט מקלדת.
  useLayoutEffect(() => {
    if (!open) return
    listRef.current?.querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [active, open, results.length])

  function choose(bank: Bank) {
    onChange(bank.code)
    setOpen(false)
    triggerRef.current?.focus()
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!results.length) return
      const dir = e.key === 'ArrowDown' ? 1 : -1
      setActive((i) => {
        const cur = results.findIndex((b) => b === results[i]) >= 0 ? i : 0
        return (cur + dir + results.length) % results.length
      })
      return
    }
    if (e.key === 'Enter' && open) {
      e.preventDefault()
      const bank = results[active]
      if (bank) choose(bank)
    }
  }

  return (
    <div className="bank-select" ref={rootRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={triggerRef}
        className={`bank-trigger${invalid ? ' bank-trigger-invalid' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
      >
        {selected ? (
          <>
            <BankMark code={selected.code} />
            <span className="bank-trigger-text">
              <span className="bank-trigger-name">{selected.name}</span>
              <span className="bank-trigger-code">{t.codeLabel(selected.code)}</span>
            </span>
          </>
        ) : (
          <span className="bank-trigger-placeholder">{t.placeholder}</span>
        )}
        <svg className="bank-chevron" viewBox="0 0 20 20" aria-hidden="true">
          <path d="M5 7.5 10 12.5 15 7.5" fill="none" stroke="currentColor" strokeWidth="1.6"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <>
          {/* רקע כהה — במובייל בלבד, כדי שהמגירה תיקרא כשכבה מעל המסך. */}
          <div className="bank-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="bank-panel" role="dialog" aria-label={t.dialogLabel}>
            <div className="bank-panel-head">
              <span className="bank-panel-title">{t.dialogLabel}</span>
              <button type="button" className="bank-panel-close" onClick={() => setOpen(false)}
                aria-label={strings.common.close}>×</button>
            </div>

            <div className="bank-search">
              <svg viewBox="0 0 20 20" aria-hidden="true" className="bank-search-icon">
                <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="m13.5 13.5 3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              <input
                ref={searchRef}
                type="search"
                className="bank-search-input"
                placeholder={t.searchPlaceholder}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setActive(0) }}
                aria-label={t.searchPlaceholder}
                autoComplete="off"
              />
            </div>

            {results.length === 0 ? (
              <p className="bank-empty">{t.noResults}</p>
            ) : (
              <ul className="bank-list" role="listbox" ref={listRef} aria-label={t.dialogLabel}>
                {results.map((bank, i) => (
                  <li key={bank.code}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={selected?.code === bank.code}
                      data-active={i === active}
                      className="bank-option"
                      onClick={() => choose(bank)}
                      onMouseEnter={() => setActive(i)}
                    >
                      <BankMark code={bank.code} />
                      <span className="bank-option-text">
                        <span className="bank-option-name">{bank.name}</span>
                        <span className="bank-option-code">{t.codeLabel(bank.code)}</span>
                      </span>
                      {selected?.code === bank.code && (
                        <svg className="bank-check" viewBox="0 0 20 20" aria-hidden="true">
                          <path d="m5 10.5 3.5 3.5L15 7" fill="none" stroke="currentColor"
                            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {/* ייחוס המקור — גם שקיפות וגם אמון: הרשימה אינה מומצאת. */}
            <p className="bank-source">{t.source(BANKS_SOURCE)}</p>
          </div>
        </>
      )}
    </div>
  )
}

export { BankMark }
