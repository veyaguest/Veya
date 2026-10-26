import { useEffect, useId, useRef, useState } from 'react'
import { searchVenues } from '../api'
import { strings } from '../strings/he'
import type { VenueSuggestion } from '../types'

const t = strings.dashboard.venueSearch

/** שורת המשנה של הצעה: "גן אירועים · משמר השרון" — מבחינה בין מקומות באותו שם. */
function metaLine(s: VenueSuggestion): string {
  return [s.kind_label, s.city].filter(Boolean).join(' · ')
}

/** הרחוב בלבד — העיר כבר מופיעה בשורת המשנה ("הרצל 5, חולון" → "הרצל 5"). */
function streetLine(s: VenueSuggestion): string {
  const addr = (s.address || '').trim()
  const city = (s.city || '').trim()
  if (!city) return addr
  if (addr === city) return ''
  return addr.endsWith(`, ${city}`) ? addr.slice(0, -(city.length + 2)) : addr
}

/**
 * שדה שם אולם עם השלמה אוטומטית מהמאגר המשותף.
 *
 * הזוג מקליד שם אולם; המערכת מציעה מקומות מהמאגר (המאגר הארצי + מקומות שזוגות
 * אחרים שמרו) עם העיר והכתובת. בחירה ממלאת את השם, ואת הכתובת רק אם השדה ריק
 * (הקורא מחליט — לא דורסים כתובת שהוקלדה). לא נמצא? ממשיכים להקליד, והשם נשמר
 * כמו שהוא. אין תלות ב-API בתשלום; החיפוש מקומי מול המאגר.
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
  // חיפוש שהסתיים בלי תוצאות (3+ תווים) — מציגים הערה שמותר להמשיך ידנית.
  const [noMatch, setNoMatch] = useState(false)
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
      setNoMatch(false)
      return
    }
    let alive = true
    const t = setTimeout(() => {
      searchVenues(q)
        .then((rows) => {
          if (!alive) return
          setSuggestions(rows)
          setNoMatch(rows.length === 0 && q.length >= 3)
          setOpen(rows.length > 0 || q.length >= 3)
          setActive(-1)
        })
        .catch(() => {
          if (!alive) return
          setSuggestions([])
          setNoMatch(false)
          setOpen(false)
        })
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
    setNoMatch(false)
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
        onFocus={() => (suggestions.length > 0 || noMatch) && setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && (suggestions.length > 0 || noMatch) && (
        <div className="venue-ac-pop">
          {suggestions.length > 0 && (
            <ul className="venue-ac-list" id={listId} role="listbox">
              {suggestions.map((s, i) => (
                <li
                  key={`${s.name}-${s.city ?? ''}-${i}`}
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
                  {metaLine(s) && <span className="venue-ac-meta">{metaLine(s)}</span>}
                  {streetLine(s) && <span className="venue-ac-addr">{streetLine(s)}</span>}
                </li>
              ))}
            </ul>
          )}
          {/* לא חלק מה-listbox: הערה בלבד, לא אפשרות לבחירה. */}
          <div className="venue-ac-foot" aria-live="polite">
            <span>{noMatch ? t.noMatch : t.notListed}</span>
            {suggestions.length > 0 && <span className="venue-ac-credit">{t.attribution}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
