import { useEffect, useId, useRef, useState } from 'react'
import { searchVenues } from '../api'
import type { VenueSuggestion } from '../types'

/**
 * שדה שם אולם עם השלמה אוטומטית מהמאגר המשותף.
 *
 * הזוג מקליד שם אולם; המערכת מציעה אולמות שנשמרו בעבר (ע"י זוגות אחרים) עם
 * הכתובת המוכנה. בחירה ממלאת גם את השם וגם את הכתובת — כדי לחסוך הקלדה ולהפעיל
 * ניווט אוטומטי בהזמנה. אין תלות ב-API בתשלום; החיפוש מקומי מול המאגר.
 */
export function VenueAutocomplete({
  value,
  onChange,
  onPick,
  placeholder = 'שם האולם',
  id,
}: {
  value: string
  onChange: (name: string) => void
  onPick: (name: string, address: string) => void
  placeholder?: string
  /** לחיבור ``<label htmlFor>`` גלוי מבחוץ. */
  id?: string
}) {
  const listId = useId()
  const [suggestions, setSuggestions] = useState<VenueSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  // מדלגים על חיפוש מיד אחרי בחירה, כדי שהרשימה לא תיפתח שוב על הערך שנבחר.
  const skipNext = useRef(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false
      return
    }
    const q = value.trim()
    if (q.length < 2) {
      setSuggestions([])
      setOpen(false)
      return
    }
    let alive = true
    const t = setTimeout(() => {
      searchVenues(q)
        .then((rows) => {
          if (!alive) return
          setSuggestions(rows)
          setOpen(rows.length > 0)
          setActive(-1)
        })
        .catch(() => alive && setSuggestions([]))
    }, 200)
    return () => {
      alive = false
      clearTimeout(t)
    }
  }, [value])

  // סגירה בלחיצה מחוץ לרכיב.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function choose(s: VenueSuggestion) {
    skipNext.current = true
    onPick(s.name, s.address)
    setOpen(false)
    setSuggestions([])
    setActive(-1)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(suggestions.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      choose(suggestions[active])
    } else if (e.key === 'Escape') {
      // preventDefault: Escape סוגר את הרשימה בלבד — לא את החלון שסביבה.
      e.preventDefault()
      setOpen(false)
    }
  }

  return (
    <div className="venue-ac" ref={boxRef}>
      {/* combobox: קורא מסך מודיע שיש הצעות, ומקריא את ההצעה המסומנת
          בחיצים (aria-activedescendant) בלי שהפוקוס עוזב את השדה. */}
      <input
        type="text"
        id={id}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => suggestions.length > 0 && setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && suggestions.length > 0 && (
        <ul className="venue-ac-list" id={listId} role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.name}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`venue-ac-item ${i === active ? 'active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(s)
              }}
              onMouseEnter={() => setActive(i)}
            >
              <span className="venue-ac-name">{s.name}</span>
              {s.address && <span className="venue-ac-addr">{s.address}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
