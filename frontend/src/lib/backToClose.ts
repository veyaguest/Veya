import { useEffect, useRef } from 'react'

/**
 * כפתור "חזור" של הטלפון/הדפדפן סוגר חלון פתוח — לפני שהוא מנווט למסך קודם.
 *
 * כל חלון שנפתח (``useBackToClose(true, onClose)``) מוסיף רשומת היסטוריה
 * באותה כתובת ונרשם במחסנית. "חזור" סוגר רק את החלון העליון — גם כשחלון
 * אישור פתוח מעל חלון אחר. סגירה רגילה (כפתור ✕ / "ביטול") מסירה את הרשומה
 * שלה, כך שה"חזור" הבא כבר מנווט כרגיל ולא נתקע.
 *
 * ה-App בודק ``consumeModalPop()`` בתחילת טיפול ה-popstate שלו, כדי לא לנווט
 * למסך אחר כשה"חזור" רק סגר חלון.
 */

interface Entry {
  id: number
  close: () => void
}

const stack: Entry[] = []
let nextId = 1
let ignoreNextPop = false
let lastPopWasModal = false

if (typeof window !== 'undefined') {
  // נרשם בזמן טעינת המודול — לפני המאזין של ה-App — ולכן רץ ראשון.
  window.addEventListener('popstate', () => {
    lastPopWasModal = false
    if (ignoreNextPop) {
      // זה ה-history.back() שלנו, אחרי סגירה מכפתור — לא "חזור" של המשתמש.
      ignoreNextPop = false
      lastPopWasModal = true
      return
    }
    const top = stack.pop()
    if (top) {
      lastPopWasModal = true
      top.close()
    }
  })
}

/** האם ה-popstate האחרון טופל כסגירת חלון (ולכן אין לנווט). קורא ומאפס. */
export function consumeModalPop(): boolean {
  const was = lastPopWasModal
  lastPopWasModal = false
  return was
}

export function useBackToClose(open: boolean, onClose: () => void): void {
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    if (!open) return
    const id = nextId++
    let pushed = false
    stack.push({ id, close: () => closeRef.current() })
    // הרשומה נוספת רק אחרי שהחלון באמת נשאר פתוח (setTimeout 0): בפיתוח
    // React מריץ כל effect פעמיים (StrictMode), ובלי זה נשארת בהיסטוריה
    // רשומה יתומה שגורמת ל"חזור" לדלג על מסך.
    const timer = window.setTimeout(() => {
      pushed = true
      window.history.pushState(
        { ...(window.history.state ?? {}), veyaModal: id },
        '',
        window.location.href,
      )
    }, 0)
    return () => {
      window.clearTimeout(timer)
      const i = stack.findIndex((e) => e.id === id)
      if (i === -1) return // נסגר ב"חזור" — הרשומה כבר הוסרה
      stack.splice(i, 1)
      if (pushed && window.history.state?.veyaModal === id) {
        ignoreNextPop = true
        window.history.back()
      }
    }
  }, [open])
}
