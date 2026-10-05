import { strings } from '../strings/he'

/**
 * כפתורים שפותחים את תפריט הנגישות (הגדרות תצוגה).
 *
 * התפריט עצמו לא חי ב-React: הוא ``public/veya-a11y.js`` — קובץ אחד
 * שרץ גם באתר הסטטי ובדפים המשפטיים, ונטען ב-``app.html`` לפני הציור
 * הראשון. כאן רק כפתורים מסומנים ב-``data-veya-a11y-open``; הסקריפט
 * מאזין להם, פותח את החלון, מעדכן ``aria-expanded`` ומחזיר אליהם פוקוס.
 */

export function A11yIcon({ size = 20 }: { size?: number }) {
  return (
    <svg
      className="va11y-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="4.6" r="1.9" />
      <path d="M5 8.6c2.3.7 4.6 1 7 1s4.7-.3 7-1" />
      <path d="M12 9.6v4.9" />
      <path d="m8.6 20.8 3.4-6.3 3.4 6.3" />
    </svg>
  )
}

/** בסרגל הצד (דסקטופ) / בפס העליון (טלפון) — אותה צורה כמו "עזרה". */
export function A11yLauncher() {
  return (
    <button
      type="button"
      className="a11y-launcher"
      data-veya-a11y-open=""
      aria-haspopup="dialog"
      aria-label={strings.common.a11yMenu}
      title={strings.common.a11yMenu}
    >
      <A11yIcon />
      <span className="a11y-launcher-label">{strings.common.a11yMenuShort}</span>
    </button>
  )
}

/** כפתור טקסט — בפוטר, ליד "הצהרת נגישות". */
export function A11yTextButton({ className = '' }: { className?: string }) {
  return (
    <button
      type="button"
      className={className}
      data-veya-a11y-open=""
      aria-haspopup="dialog"
    >
      {strings.common.a11yMenu}
    </button>
  )
}

/** כפתור עגול עם אייקון בלבד — בדף המוזמן. */
export function A11yIconButton({ className = '' }: { className?: string }) {
  return (
    <button
      type="button"
      className={className}
      data-veya-a11y-open=""
      aria-haspopup="dialog"
      aria-label={strings.common.a11yMenu}
      title={strings.common.a11yMenu}
    >
      <A11yIcon />
    </button>
  )
}
