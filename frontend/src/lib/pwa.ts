/**
 * שכבת ה-Web App של VEYA — זיהוי "רצים כאפליקציה מותקנת", מצב ההצעה
 * להתקנה, ומשתני ה-CSS שתלויים בחלון האמיתי (מקלדת פתוחה).
 *
 * הקובץ הזה **לא נוגע בהתחברות**. הטוקן ממשיך לחיות ב-``authStore``
 * וב-localStorage בדיוק כמו קודם — אפליקציה שהותקנה למסך הבית מקבלת את
 * אותו אחסון, ולכן המשתמש נשאר מחובר גם אחרי סגירה ופתיחה מחדש.
 */

/** רק "כן/לא" של ההצעה + מתי נדחתה. אין כאן שום מידע אישי. */
const DISMISSED_KEY = 'veya_install_dismissed_at'
/** נדלק פעם אחת ברגע ש-VEYA נפתחה כאפליקציה מותקנת — ואז ההצעה נעלמת לתמיד. */
const INSTALLED_KEY = 'veya_installed'

/**
 * כמה זמן שקט אחרי סגירת ההצעה — ושתי התשובות אינן שוות.
 *
 * ``SNOOZE_DISMISS`` — "לא עכשיו". 30 יום: מספיק ארוך כדי לא להציק,
 * מספיק קצר כדי לתפוס זוג שחזר לתכנן חודש לפני האירוע.
 *
 * ``SNOOZE_EXPLAINED`` — סגירה **אחרי** שקרא את שלושת הצעדים. חצי שנה,
 * ובכוונה: זה כמעט תמיד מישהו שהתקין בפועל, אבל אנחנו לא יכולים לדעת
 * זאת. הסיבה שאי אפשר לדעת היא מגבלת iOS: אפליקציה שנוספה למסך הבית
 * מקבלת אחסון **נפרד** מזה של Safari, ולכן הדגל "כבר מותקן" שנכתב
 * בתוך האפליקציה אינו נראה כשאותו אדם פותח שוב את VEYA ב-Safari.
 * במקום לנחש "הוא התקין" (וכך להעלים את ההצעה ממי שלא) — פשוט שותקים
 * לתקופה ארוכה. הבחנה, לא הנחה.
 */
const SNOOZE_DISMISS_DAYS = 30
const SNOOZE_EXPLAINED_DAYS = 180

/** קריאה בטוחה מ-localStorage: בגלישה פרטית ב-Safari הגישה עלולה לזרוק. */
function readFlag(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeFlag(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* אין אחסון — ההצעה פשוט תופיע שוב בביקור הבא. לא שוברים כלום. */
  }
}

/**
 * האם VEYA רצה כרגע כאפליקציה מותקנת (ולא בתוך Safari).
 *
 * שתי בדיקות, כי iOS ואנדרואיד לא מסכימים:
 *   - ``navigator.standalone`` — הדרך **היחידה** של iOS. קיים רק ב-Safari.
 *   - ``display-mode: standalone`` — התקן, מה שאנדרואיד/דסקטופ מדווחים.
 * מספיק שאחת מהן נכונה. במפורש **לא** נשענים על ``beforeinstallprompt``:
 * iOS לא יורה אותו בכלל, ולכן היעדרו לא אומר שום דבר.
 */
export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  const iosStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone
  if (iosStandalone === true) return true
  return window.matchMedia?.('(display-mode: standalone)').matches === true
}

/** iPhone / iPad / iPod (כולל iPadOS שמתחזה ל-Mac עם מסך מגע). */
export function isIos(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  if (/iPhone|iPad|iPod/.test(ua)) return true
  return /Macintosh/.test(ua) && navigator.maxTouchPoints > 1
}

/**
 * Safari עצמו — ולא Chrome/Firefox/אפליקציה שמריצה WebView בתוך iOS.
 * חשוב, כי "הוספה למסך הבית" קיימת **רק** ב-Safari: להציע אותה בתוך
 * הדפדפן של פייסבוק או ב-Chrome לאייפון זו הוראה שלא ניתן לבצע.
 */
export function isIosSafari(): boolean {
  if (!isIos()) return false
  const ua = navigator.userAgent
  // CriOS=Chrome, FxiOS=Firefox, EdgiOS=Edge, OPT=Opera, GSA=אפליקציית גוגל.
  if (/CriOS|FxiOS|EdgiOS|OPT\/|GSA\//.test(ua)) return false
  // דפדפן מוטמע (פייסבוק/אינסטגרם/וואטסאפ) — אין שם תפריט שיתוף של Safari.
  if (/FBAN|FBAV|Instagram|Line\/|Twitter/.test(ua)) return false
  return /Safari/.test(ua)
}

/** האם המשתמש כבר פתח פעם את VEYA כאפליקציה מותקנת. */
export function wasEverInstalled(): boolean {
  return readFlag(INSTALLED_KEY) === '1'
}

/**
 * האם ההצעה בהשהיה אחרי ש"סגרו" אותה.
 *
 * שימו לב להבחנה שהיא **כל הרעיון** של המסך הזה: סגירת ההצעה היא
 * ``dismissed`` בלבד — היא לא נחשבת התקנה. רק פתיחה אמיתית ב-standalone
 * מדליקה את ``veya_installed``. לכן מי שסגר יקבל תזכורת בבוא הזמן
 * (30 יום, או חצי שנה אם קרא קודם את ההוראות), ומי שהתקין באמת לא
 * יראה את ההצעה שוב לעולם.
 */
export function isSnoozed(): boolean {
  const raw = readFlag(DISMISSED_KEY)
  if (!raw) return false
  // הפורמט: "<timestamp>:<ימי השהיה>". רשומה ישנה בלי ימים נופלת ל-30.
  const [stamp, days] = raw.split(':')
  const at = Number(stamp)
  if (!Number.isFinite(at)) return false
  const window = (Number(days) || SNOOZE_DISMISS_DAYS) * 24 * 60 * 60 * 1000
  return Date.now() - at < window
}

/**
 * סגירת ההצעה. ``explained`` = המשתמש ראה את הוראות ההתקנה לפני שסגר.
 *
 * בשני המקרים זו **סגירה בלבד** — לא סימון "הותקן". הדגל הקבוע
 * ``veya_installed`` נדלק רק כש-VEYA באמת נפתחת כאפליקציה מותקנת.
 */
export function snoozeInstallPrompt(explained = false): void {
  const days = explained ? SNOOZE_EXPLAINED_DAYS : SNOOZE_DISMISS_DAYS
  writeFlag(DISMISSED_KEY, `${Date.now()}:${days}`)
}

/**
 * האם להציע עכשיו התקנה למסך הבית.
 *
 * ההצעה מוצגת רק כשכל התנאים מתקיימים — כל אחד מהם הוא סיבה אמיתית
 * לשתוק, לא "העדפה":
 *   1. אנחנו ב-Safari על iPhone/iPad (רק שם ההוראה בכלל ניתנת לביצוע).
 *   2. VEYA לא רצה כבר כאפליקציה מותקנת.
 *   3. המשתמש לא פתח אותה כאפליקציה בעבר.
 *   4. הוא לא סגר את ההצעה לאחרונה (ראו ``isSnoozed``).
 */
export function shouldOfferInstall(): boolean {
  if (!isIosSafari()) return false
  if (isStandalone()) return false
  if (wasEverInstalled()) return false
  if (isSnoozed()) return false
  return true
}

/**
 * מסמן על ``<html>`` את מצב ההרצה, כדי ש-CSS יוכל להגיב בלי JS נוסף:
 *   ``veya-standalone`` — רצים כאפליקציה מותקנת (safe-area, בלי רמזי Safari).
 *   ``veya-ios``        — מכשיר iOS.
 * בנוסף מדליק פעם אחת את הדגל הקבוע "כבר הותקן".
 */
function markRuntimeFlags(): void {
  const root = document.documentElement
  const standalone = isStandalone()
  root.classList.toggle('veya-standalone', standalone)
  root.classList.toggle('veya-ios', isIos())
  if (standalone && !wasEverInstalled()) writeFlag(INSTALLED_KEY, '1')
}

/**
 * מפרסם את גובה החלון **הנראה** ל-CSS, כדי שדיאלוגים לא ייחתכו מאחורי
 * המקלדת של iOS.
 *
 * למה זה נחוץ: ``100vh`` ואפילו ``100dvh`` לא מתכווצים כשהמקלדת נפתחת
 * ב-iOS — הם מודדים את חלון הפריסה, והמקלדת פשוט מכסה אותו. הדבר היחיד
 * שיודע את האמת הוא ``visualViewport``. מתוכו נגזרים:
 *   ``--app-vh``  — הגובה הפנוי בפועל (ברירת מחדל: 100dvh, כשאין תמיכה).
 *   ``veya-kb-open`` על ``<html>`` — המקלדת פתוחה כרגע.
 */
function trackVisualViewport(): void {
  const vv = window.visualViewport
  if (!vv) return
  const root = document.documentElement
  let frame = 0
  const apply = () => {
    root.style.setProperty('--app-vh', `${Math.round(vv.height)}px`)
    // חפיפה = כמה מהחלון מכוסה מלמטה. מעל 120px זו מקלדת ולא סרגל דפדפן.
    const overlap = window.innerHeight - vv.height - vv.offsetTop
    root.classList.toggle('veya-kb-open', overlap > 120)
  }
  const schedule = () => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(apply)
  }
  apply()
  vv.addEventListener('resize', schedule)
  vv.addEventListener('scroll', schedule)
}

/**
 * רישום ה-Service Worker.
 *
 * מה הוא עושה: **רק** מסך "אין חיבור" מעוצב במקום שגיאת הדפדפן, ובזכות
 * קיומו אנדרואיד/כרום בכלל מציעים "התקנה". מה הוא **לא** עושה: הוא לא
 * שומר את מעטפת האפליקציה (כדי שלעולם לא תיפתח גרסה ישנה אחרי עדכון),
 * ולא נוגע ב-API — הבקאנד יושב בדומיין אחר לגמרי, ו-Service Worker
 * לא רואה בכלל בקשות לדומיין זר. ראו ``public/sw.js``.
 *
 * רק בייצור: בפיתוח SW רק מסתיר שינויים ומבלבל.
 */
function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return
  if (!('serviceWorker' in navigator)) return
  const register = () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* נכשל? VEYA עובדת בדיוק כמו קודם. אין כאן תלות. */
    })
  }
  // מחכים לסיום הטעינה כדי לא להתחרות על הרשת עם המסך הראשון — אבל אם
  // ``load`` כבר קרה (טעינה מהירה, חזרה מה-cache של הדפדפן), מאזין
  // חדש לעולם לא ייקרא. לכן בודקים קודם את המצב בפועל.
  if (document.readyState === 'complete') register()
  else window.addEventListener('load', register, { once: true })
}

/** נקודת כניסה אחת שנקראת פעם אחת מ-main.tsx. */
export function initPwa(): void {
  markRuntimeFlags()
  trackVisualViewport()
  registerServiceWorker()
  // המשתמש יכול להתקין באמצע השימוש (Safari לא מרענן) — או להיפך, לפתוח
  // מהאייקון. מאזינים לשינוי כדי שהסימונים לא יישארו תקועים.
  window.matchMedia?.('(display-mode: standalone)').addEventListener?.('change', markRuntimeFlags)
}
