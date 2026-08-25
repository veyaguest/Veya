import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  onClose: () => void
  /** ייבוא מהדבקת טקסט (וואטסאפ/כל מקור) — אותו מנגנון בדיוק כמו ב-ImportMenu. */
  onPaste: () => void
  /** ייבוא מקובץ Excel/CSV — אותו מנגנון בדיוק כמו ב-ImportMenu. */
  onExcel: () => void
  /** לא מועבר כלל כשהדפדפן הנוכחי לא תומך בבחירת אנשי קשר (בדיוק כמו ב-ImportMenu). */
  onContacts?: () => void
  /** פותח את טופס ההוספה הידנית הקיים (AddGuestForm). */
  onManual: () => void
}

/**
 * מסך "הוסיפו את המוזמנים שלכם" — מוצג פעם אחת, מיד לאחר יצירת האירוע
 * (App.tsx מנווט ישירות ל-guests, ולא לדשבורד). ממשיך טבעי מ-Onboarding
 * יצירת האירוע, לא "מעבר פתאומי" למסך ניהול: שלוש דרכי הייבוא הקיימות
 * מוצגות כאן כפעולה ראשית וברורה; הוספה ידנית נשארת זמינה כאפשרות משנית.
 *
 * חשוב: לא בונה שום מנגנון ייבוא חדש. שלוש הפעולות (onPaste/onExcel/
 * onContacts) הן בדיוק אותן פונקציות שה-toolbar הרגיל ב-GuestsPage מעביר
 * ל-ImportMenu — כאן הן רק מוצגות בפריסה בולטת יותר, עם התוצאה הזהה: אותם
 * PasteImportDialog/ImportDialog/ContactsImportDialog נפתחים אחר כך.
 */
export function OnboardingDialog({ onClose, onPaste, onExcel, onContacts, onManual }: Props) {
  function choose(action: () => void) {
    onClose()
    action()
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog onboarding-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="x" onClick={onClose}>
          ✕
        </button>

        <div className="onboarding-head">
          <h2>{t.onboardingTitle}</h2>
          <p className="onboarding-sub">{t.onboardingSub}</p>
        </div>

        <div className="onboarding-import-options">
          <button
            type="button"
            className="onboarding-import-btn"
            onClick={() => choose(onPaste)}
          >
            {t.pasteButton}
          </button>
          <button
            type="button"
            className="onboarding-import-btn"
            onClick={() => choose(onExcel)}
          >
            {t.uploadButton}
          </button>
          {onContacts && (
            <button
              type="button"
              className="onboarding-import-btn"
              onClick={() => choose(onContacts)}
            >
              {t.contactsButton}
            </button>
          )}
        </div>

        <button type="button" className="btn-text onboarding-manual" onClick={() => choose(onManual)}>
          {t.onboardingManualCta}
        </button>
      </div>
    </div>
  )
}
