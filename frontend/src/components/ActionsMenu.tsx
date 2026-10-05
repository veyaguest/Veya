import { useMenu } from '../lib/useMenu'

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
  const menu = useMenu()
  const total = items.reduce((sum, it) => sum + (it.badge ?? 0), 0)

  return (
    <div className="import-menu" ref={menu.wrapRef}>
      <button type="button" className="btn-ghost toolbar-suggestions" {...menu.triggerProps}>
        {label}
        {total > 0 && <span className="toolbar-badge">{total}</span>}
      </button>
      {menu.open && (
        <div className="import-menu-list" {...menu.listProps}>
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              className="import-menu-item"
              tabIndex={-1}
              onClick={menu.select(it.onClick)}
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
