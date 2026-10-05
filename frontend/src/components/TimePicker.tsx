import { useEffect, useRef, useState } from 'react'
import type { FocusEvent as ReactFocusEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { strings } from '../strings/he'

interface TimePickerProps {
  /** ערך בפורמט "HH:MM" — בדיוק כמו input type="time", בלי שינוי. */
  value: string
  onChange: (value: string) => void
  /** גבולות אופציונליים באותו פורמט "HH:MM" — אותה סמנטיקה כמו min/max הילידיים. */
  min?: string
  max?: string
  id?: string
  ariaLabel?: string
}

const HOURS = Array.from({ length: 24 }, (_, i) => i)
// קפיצות של חצי שעה בלבד — 00 ו-30 (החלטת מוצר: אין צורך בדיוק של דקה בודדת לשעות אירוע).
const MINUTES = [0, 30]

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function parseTime(t: string): { h: number; m: number } | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(t)
  if (!match) return null
  return { h: Number(match[1]), m: Number(match[2]) }
}

/**
 * בורר שעה ויזואלי — שתי עמודות גלילה (שעות/דקות) בפאנל צף, במקום ה-picker
 * הילידי של input type="time" שבמחשב דורש הקלדה ידנית. אותו ערך ("HH:MM")
 * ואותה סמנטיקת min/max כמו הקלט המקורי — שינוי בחוויית הבחירה בלבד.
 */
export function TimePicker({ value, onChange, min, max, id, ariaLabel }: TimePickerProps) {
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const hourListRef = useRef<HTMLDivElement>(null)
  const minuteListRef = useRef<HTMLDivElement>(null)

  const parsed = parseTime(value)
  const minParsed = min ? parseTime(min) : null
  const maxParsed = max ? parseTime(max) : null

  // סגירה בלחיצה מחוץ לרכיב ובמקש Escape — אותו דפוס כמו VenueAutocomplete.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const triggerRef = useRef<HTMLButtonElement>(null)

  /** סגירה והחזרת הפוקוס לכפתור — אחרת הפוקוס נשאר על אפשרות שנעלמה
   *  מה-DOM ונופל ל-body, ומשתמש מקלדת מתחיל את העמוד מההתחלה. */
  function closeAndReturn() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  // מקלדת: Escape סוגר (ועוצר — כדי לא לסגור גם חלון שסביבו), חיצים
  // למעלה/למטה זזים בתוך עמודה, Home/End לקצוות. Enter/רווח בוחרים כרגיל
  // (אלה כפתורים). Tab עובר מעמודת השעות לעמודת הדקות ומשם החוצה.
  function onPanelKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      closeAndReturn()
      return
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return
    const col = (e.target as HTMLElement).closest('.time-picker-col')
    if (!col) return
    const opts = Array.from(col.querySelectorAll<HTMLButtonElement>('.time-picker-opt:not(:disabled)'))
    const at = opts.indexOf(e.target as HTMLButtonElement)
    if (at < 0) return
    e.preventDefault()
    const next =
      e.key === 'Home' ? 0
        : e.key === 'End' ? opts.length - 1
          : e.key === 'ArrowDown' ? Math.min(opts.length - 1, at + 1)
            : Math.max(0, at - 1)
    opts[next].focus()
    opts[next].scrollIntoView({ block: 'nearest' })
  }

  // יציאה מהרכיב ב-Tab סוגרת את הפאנל — כמו לחיצה מחוצה לו.
  function onBlur(e: ReactFocusEvent<HTMLDivElement>) {
    if (open && !boxRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false)
  }

  // גלילה אוטומטית אל השעה/הדקה הנבחרות ברגע שהפאנל נפתח — כמו בורר שעה בטלפון.
  useEffect(() => {
    if (!open) return
    const scrollToActive = (listEl: HTMLDivElement | null) => {
      listEl?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView({ block: 'center' })
    }
    scrollToActive(hourListRef.current)
    scrollToActive(minuteListRef.current)
  }, [open])

  function hourDisabled(h: number): boolean {
    if (minParsed && h < minParsed.h) return true
    if (maxParsed && h > maxParsed.h) return true
    return false
  }

  function minuteDisabled(h: number, m: number): boolean {
    if (minParsed && h === minParsed.h && m < minParsed.m) return true
    if (maxParsed && h === maxParsed.h && m > maxParsed.m) return true
    return false
  }

  function pickHour(h: number) {
    // שומרים על הדקה הנוכחית, אבל מהדקים אותה לתחום המותר אם הגבול נחצה —
    // אותה התנהגות שדפדפנים אוכפים על min/max ילידיים.
    let m = parsed?.m ?? 0
    if (minParsed && h === minParsed.h && m < minParsed.m) m = minParsed.m
    if (maxParsed && h === maxParsed.h && m > maxParsed.m) m = maxParsed.m
    onChange(`${pad(h)}:${pad(m)}`)
  }

  function pickMinute(m: number) {
    const h = parsed?.h ?? 0
    onChange(`${pad(h)}:${pad(m)}`)
  }

  return (
    <div className="time-picker" ref={boxRef} onBlur={onBlur}>
      {/* השם הנגיש כולל את הערך: בלעדיו קורא מסך אמר "שעת האירוע, כפתור"
          בלי לומר איזו שעה נבחרה. */}
      <button
        type="button"
        id={id}
        ref={triggerRef}
        className="time-picker-trigger"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={
          ariaLabel
            ? `${ariaLabel}: ${parsed ? `${pad(parsed.h)}:${pad(parsed.m)}` : strings.common.timeNotSet}`
            : undefined
        }
        onClick={() => setOpen((o) => !o)}
      >
        <span className="time-picker-value">
          {parsed ? `${pad(parsed.h)}:${pad(parsed.m)}` : '--:--'}
        </span>
        <span className="time-picker-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="8.5" />
            <path d="M12 7.5V12l3 2" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="time-picker-panel" dir="ltr" onKeyDown={onPanelKeyDown}>
          <div
            className="time-picker-col"
            ref={hourListRef}
            role="group"
            aria-label={strings.common.timeHours}
          >
            {HOURS.map((h) => {
              const active = parsed?.h === h
              return (
                <button
                  key={h}
                  type="button"
                  className={`time-picker-opt${active ? ' is-active' : ''}`}
                  data-active={active ? 'true' : undefined}
                  aria-pressed={active}
                  // רק השעה הנבחרת (או הראשונה) בסדר ה-Tab; בין השאר — חיצים.
                  tabIndex={active || (!parsed && h === 0) ? 0 : -1}
                  disabled={hourDisabled(h)}
                  onClick={() => pickHour(h)}
                >
                  {pad(h)}
                </button>
              )
            })}
          </div>
          <div className="time-picker-sep" aria-hidden="true">:</div>
          <div
            className="time-picker-col"
            ref={minuteListRef}
            role="group"
            aria-label={strings.common.timeMinutes}
          >
            {MINUTES.map((m) => {
              const active = parsed?.m === m
              return (
                <button
                  key={m}
                  type="button"
                  className={`time-picker-opt${active ? ' is-active' : ''}`}
                  data-active={active ? 'true' : undefined}
                  aria-pressed={active}
                  tabIndex={active || (!parsed && m === 0) ? 0 : -1}
                  disabled={parsed ? minuteDisabled(parsed.h, m) : false}
                  onClick={() => pickMinute(m)}
                >
                  {pad(m)}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
