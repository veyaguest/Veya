import { useEffect, useRef, useState } from 'react'

export interface ActionsMenuItem {
  label: string
  onClick: () => void
  /** מספר קטן ליד הפריט (למשל כמה הצעות מחכות). 0/undefined — לא מוצג. */
  badge?: number
}

/** כפתור עם תפריט נפתח לפעולות משניות — כדי שסרגל הכלים יציג רק את
 *  הפעולות העיקריות. אותו מראה והתנהגות כמו ``ImportMenu`` (סגירה בלחיצה
 *  מחוץ לתפריט וב-Escape). */
export function ActionsMenu({ label, items }: { label: string; items: ActionsMenuItem[] }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const total = items.reduce((sum, it) => sum + (it.badge ?? 0), 0)

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
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
        className="btn-ghost toolbar-suggestions"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {label}
        {total > 0 && <span className="toolbar-badge">{total}</span>}
      </button>
      {open && (
        <div className="import-menu-list" role="menu">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              className="import-menu-item"
              onClick={() => {
                setOpen(false)
                it.onClick()
              }}
            >
              {it.label}
              {(it.badge ?? 0) > 0 && <span className="toolbar-badge">{it.badge}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
