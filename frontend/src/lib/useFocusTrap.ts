import { useEffect } from 'react'
import type { RefObject } from 'react'

/** מה נחשב "ניתן למיקוד" לצורך המלכודת. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
  ' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * מלכודת פוקוס למגירה/דיאלוג (§26, §30).
 *
 * כשהיא פעילה: הפוקוס נכנס פנימה, Tab ו-Shift+Tab מסתובבים **בתוך**
 * הרכיב בלבד, ובסגירה הפוקוס חוזר לאלמנט שפתח אותו.
 *
 * למה זה נחוץ ולא מספיק ``aria-modal``: ``aria-modal`` אומר לקורא המסך
 * שיש כאן מודל, אבל **לא** מונע מ-Tab לצאת אל התוכן שמאחור. משתמש מקלדת
 * היה "נופל" מהמגירה אל מפת האולם שמתחתיה בלי לדעת.
 *
 * שימו לב: הקומפוננטה עצמה עדיין אחראית ל-Escape — הוא לרוב תלוי הקשר
 * (סגירה, ביטול בחירה, יציאה ממצב העברה), ולכן לא נכנס לכאן.
 */
export function useFocusTrap(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useEffect(() => {
    if (!active) return
    const node = ref.current
    if (!node) return

    const opener = document.activeElement

    // הפוקוס נכנס אל **הרכיב עצמו** כשהוא בר-מיקוד (tabIndex={-1}) — זו
    // ההתנהגות הנכונה לדיאלוג: קורא המסך מקריא קודם את שם המגירה
    // ("רשימת המוזמנים, dialog") ורק אז המשתמש נכנס לפקדים ב-Tab.
    // אם הרכיב אינו בר-מיקוד, נופלים לפקד הראשון שבו.
    if (node.tabIndex >= -1 && node.hasAttribute('tabindex')) node.focus()
    else node.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab' || !node) return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      )
      if (items.length === 0) {
        e.preventDefault()
        node.focus()
        return
      }
      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      // גם המקרה שבו הפוקוס איכשהו כבר מחוץ לרכיב מוחזר פנימה.
      if (!node.contains(document.activeElement)) {
        e.preventDefault()
        firstItem.focus()
        return
      }
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault()
        lastItem.focus()
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault()
        firstItem.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus()
    }
  }, [ref, active])
}
