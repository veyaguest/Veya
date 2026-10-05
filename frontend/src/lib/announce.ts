/**
 * הכרזה לקורא מסך — "המוזמן נוסף", "נשמר", "3 מוזמנים שובצו".
 *
 * למה לא פשוט ``role="status"`` על הטוסט: אזור חי מוכרז רק כשהתוכן שלו
 * *משתנה* אחרי שהאזור כבר קיים בעץ. טוסט שמרונדר יחד עם הטקסט שלו נולד
 * מלא, ורוב קוראי המסך (בעיקר VoiceOver) פשוט לא מקריאים אותו. כאן יש
 * אזור אחד קבוע ב-body, שקיים מהרגע הראשון, ורק הטקסט שבו מתחלף.
 *
 * מנומס (polite) בלבד: לא קוטע את מה שהמשתמש שומע עכשיו. שגיאות ממשיכות
 * להשתמש ב-``role="alert"`` הקיים ליד השדה/הטופס — שם המיקום הוא חלק
 * מהמידע.
 */

let region: HTMLElement | null = null
let clearTimer: number | undefined

function ensureRegion(): HTMLElement {
  if (region && document.body.contains(region)) return region
  region = document.createElement('div')
  region.setAttribute('role', 'status')
  region.setAttribute('aria-live', 'polite')
  region.setAttribute('aria-atomic', 'true')
  region.className = 'sr-only'
  region.id = 'veya-announcer'
  document.body.appendChild(region)
  return region
}

export function announce(message: string): void {
  if (typeof document === 'undefined' || !message) return
  const el = ensureRegion()
  // ריקון ואז כתיבה בטיק הבא: אותה הודעה פעמיים ברצף ("נשמר", "נשמר")
  // אחרת לא נחשבת שינוי ולא מוכרזת בפעם השנייה.
  el.textContent = ''
  window.clearTimeout(clearTimer)
  window.setTimeout(() => {
    el.textContent = message
    // מנקים אחרי כמה שניות, כדי שמי שמגיע לסוף העמוד בחיצים לא ייתקל
    // בהודעה ישנה שכבר לא רלוונטית.
    clearTimer = window.setTimeout(() => {
      el.textContent = ''
    }, 7000)
  }, 60)
}

// האזור נוצר כבר בטעינה, כדי שההודעה הראשונה לא תיפול על אזור "חדש".
if (typeof document !== 'undefined') {
  if (document.body) ensureRegion()
  else document.addEventListener('DOMContentLoaded', () => ensureRegion(), { once: true })
}
