import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/** מה נחשב "ניתן למיקוד" לצורך המלכודת. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
  ' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** מלכודות פעילות, מהישנה לחדשה. רק העליונה מטפלת ב-Tab — אחרת חלון
 *  אישור שנפתח מעל חלון עריכה (כאחים ב-DOM, לא כילד) היה "נמשך" חזרה
 *  אל החלון שמתחתיו בכל לחיצת Tab. */
const trapStack: HTMLElement[] = []
/** לאן להחזיר פוקוס כשה"פותח" כבר לא קיים (ראו ב-cleanup). */
let fallbackReturn: HTMLElement | null = null

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
  /** מי פתח את הרכיב — כשנלכד כבר ברינדור (useDialog). בלי זה נלקח
   *  ``document.activeElement`` ברגע ההפעלה, וזה כבר עלול להיות שדה
   *  ``autoFocus`` שבתוך הדיאלוג עצמו. */
  openerRef?: RefObject<Element | null>,
): void {
  // הערך העדכני של ``active`` — כדי שה-cleanup ידע אם הרכיב באמת נסגר, או
  // שה-effect רק רץ מחדש (StrictMode בפיתוח מריץ כל effect פעמיים) ואז
  // אסור להחזיר פוקוס ל"פותח" ולגנוב אותו מהשדה שבתוך החלון.
  const activeRef = useRef(active)
  activeRef.current = active
  // "מי פתח" נשמר על פני הרצות חוזרות של ה-effect — בהרצה השנייה הפוקוס
  // כבר בתוך החלון, ו-``document.activeElement`` כבר לא הפותח.
  const savedOpener = useRef<Element | null>(null)
  useEffect(() => {
    if (!active) return
    const node = ref.current
    if (!node) return

    if (!savedOpener.current) savedOpener.current = openerRef?.current ?? document.activeElement
    const opener = savedOpener.current

    // הפוקוס נכנס אל **הרכיב עצמו** כשהוא בר-מיקוד (tabIndex={-1}) — זו
    // ההתנהגות הנכונה לדיאלוג: קורא המסך מקריא קודם את שם המגירה
    // ("רשימת המוזמנים, dialog") ורק אז המשתמש נכנס לפקדים ב-Tab.
    // אם הרכיב אינו בר-מיקוד, נופלים לפקד הראשון שבו. ואם הפוקוס כבר
    // בפנים (שדה עם ``autoFocus``) — משאירים אותו שם: זו בחירה מכוונת.
    if (node.contains(document.activeElement)) {
      // כבר בפנים
    } else if (node.tabIndex >= -1 && node.hasAttribute('tabindex')) node.focus()
    else node.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    trapStack.push(node)

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab' || !node) return
      if (trapStack[trapStack.length - 1] !== node) return
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

    // "הצלת פוקוס": חלון שמחליף תוכן (שלב באשף, "פענוח הרשימה" → טבלת
    // סקירה) מוחק את הכפתור שהיה בפוקוס, והפוקוס נופל ל-body — מחוץ
    // לחלון, וקורא המסך לא מקריא כלום. מחזירים אותו לחלון עצמו (שמו
    // מוקרא), ומשם Tab ממשיך כרגיל.
    const rescue = new MutationObserver(() => {
      if (document.activeElement !== document.body) return
      if (trapStack[trapStack.length - 1] !== node || !document.contains(node)) return
      if (node.hasAttribute('tabindex')) node.focus()
      else node.querySelector<HTMLElement>(FOCUSABLE)?.focus()
    })
    rescue.observe(node, { childList: true, subtree: true })

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      rescue.disconnect()
      document.removeEventListener('keydown', onKeyDown, true)
      const at = trapStack.lastIndexOf(node)
      if (at >= 0) trapStack.splice(at, 1)
      const target =
        opener instanceof HTMLElement && document.contains(opener)
          ? opener
          : fallbackReturn && document.contains(fallbackReturn)
            ? fallbackReturn
            : null
      if (activeRef.current && document.contains(node)) return
      savedOpener.current = null
      const active = document.activeElement
      const focusLost = !active || active === document.body || node.contains(active)
      if (focusLost) {
        target?.focus()
        fallbackReturn = null
      } else if (target) {
        // הפוקוס כבר עבר במכוון למקום אחר — בדרך כלל לחלון הבא שנפתח
        // מתוך זה (למשל "הדבקה" מתוך חלון הפתיחה). לא חוטפים אותו בחזרה,
        // אבל זוכרים לאן לחזור: כשהחלון הבא ייסגר, "מי שפתח" אותו (כפתור
        // בחלון הקודם) כבר לא קיים.
        fallbackReturn = target
      }
    }
  }, [ref, active, openerRef])
}
