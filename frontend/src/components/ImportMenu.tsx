import { useMenu } from '../lib/useMenu'
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
  const menu = useMenu()

  return (
    <div className="import-menu" ref={menu.wrapRef}>
      <button
        type="button"
        className="btn-ghost"
        data-help="guests.importMenu"
        {...menu.triggerProps}
      >
        {t.importMenuButton}
      </button>
      {menu.open && (
        <div className="import-menu-list" {...menu.listProps}>
          <button
            type="button"
            role="menuitem"
            className="import-menu-item"
            data-help="guests.importExcel"
            tabIndex={-1}
            onClick={menu.select(onExcel)}
          >
            {t.uploadButton}
          </button>
          <button
            type="button"
            role="menuitem"
            className="import-menu-item"
            data-help="guests.importPaste"
            tabIndex={-1}
            onClick={menu.select(onPaste)}
          >
            {t.pasteButton}
          </button>
          {onContacts && (
            <button
              type="button"
              role="menuitem"
              className="import-menu-item"
              tabIndex={-1}
              onClick={menu.select(onContacts)}
            >
              {t.contactsButton}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
