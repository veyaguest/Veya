import { useId, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useFocusTrap } from './useFocusTrap'

/**
 * כל מה שחלון (דיאלוג) צריך כדי שיהיה נגיש — במקום אחד.
 *
 * עד עכשיו כל חלון במערכת נבנה ידנית (``.overlay > .dialog``), וברובם
 * הפוקוס נשאר מאחור, Tab "ברח" אל המסך שמתחת, Escape לא סגר, ובסגירה
 * הפוקוס נפל ל-body. ה-hook מחזיר props לפריסה על ה-div של החלון:
 *
 *   const dlg = useDialog(onClose)
 *   <div className="dialog" {...dlg.props}>
 *     <h2 id={dlg.titleId}>…</h2>
 *
 * - ``role="dialog"`` + ``aria-modal`` + ``aria-labelledby`` → קורא מסך
 *   מכריז "חלון, <הכותרת>" ומתעלם מהמסך שמאחור.
 * - פוקוס נכנס לחלון (לחלון עצמו, כדי שהשם יוקרא; או נשאר בשדה
 *   ``autoFocus`` אם יש), Tab מסתובב בפנים, ובסגירה חוזר למי שפתח.
 * - Escape סוגר. מטופל ב-onKeyDown של החלון (ולא על document), כך
 *   שבחלונות מקוננים רק הפנימי נסגר, ורכיב פנימי שכבר טיפל ב-Escape
 *   (בורר שעה פתוח, השלמה אוטומטית) קורא ``preventDefault`` והחלון נשאר.
 *
 * ``closeOnEscape: false`` לחלון שאסור לסגור באמצע (למשל בזמן שמירה) —
 * אז מעבירים פונקציה שבודקת את המצב, או false.
 */
export function useDialog(
  onClose: () => void,
  { open = true, closeOnEscape = true }: { open?: boolean; closeOnEscape?: boolean } = {},
) {
  const ref = useRef<HTMLDivElement | null>(null)
  const titleId = useId()
  // מי פתח את החלון — נלכד ברינדור הראשון, לפני ש-autoFocus בתוך החלון
  // מזיז את הפוקוס. רק קריאה, בלי תופעות לוואי.
  const openerRef = useRef<Element | null>(null)
  if (open && openerRef.current === null && typeof document !== 'undefined') {
    openerRef.current = document.activeElement
  }
  if (!open) openerRef.current = null

  useFocusTrap(ref, open, openerRef)

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key !== 'Escape' || e.defaultPrevented || !closeOnEscape) return
    e.preventDefault()
    e.stopPropagation()
    onClose()
  }

  return {
    titleId,
    props: {
      ref,
      role: 'dialog' as const,
      'aria-modal': true as const,
      'aria-labelledby': titleId,
      tabIndex: -1,
      onKeyDown,
    },
  }
}
