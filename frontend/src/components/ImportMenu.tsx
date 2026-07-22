import { useEffect, useRef, useState } from 'react'
import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  onExcel: () => void
  onPaste: () => void
  /** לא מועבר כלל כשהדפדפן הנוכחי לא תומך בבחירת אנשי קשר (למשל Safari/iPhone). */
  onContacts?: () => void
}

/** כפתור "ייבוא מוזמנים" מרכזי עם תפריט נפתח לכל דרכי הייבוא. */
export function ImportMenu({ onExcel, onPaste, onContacts }: Props) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="import-menu" ref={wrapRef}>
      <button
        type="button"
        className="btn-ghost"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {t.importMenuButton}
      </button>
      {open && (
        <div className="import-menu-list" role="menu">
          <button
            type="button"
            role="menuitem"
            className="import-menu-item"
            onClick={() => {
              setOpen(false)
              onExcel()
            }}
          >
            {t.uploadButton}
          </button>
          <button
            type="button"
            role="menuitem"
            className="import-menu-item"
            onClick={() => {
              setOpen(false)
              onPaste()
            }}
          >
            {t.pasteButton}
          </button>
          {onContacts && (
            <button
              type="button"
              role="menuitem"
              className="import-menu-item"
              onClick={() => {
                setOpen(false)
                onContacts()
              }}
            >
              {t.contactsButton}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
