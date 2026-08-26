import type { ReactElement } from 'react'
import type { EventType } from '../types'

/**
 * אייקון לכל סוג אירוע — קווי, באותו משקל ובאותו גודל לכל הסוגים.
 *
 * קודם ישבו כאן אימוג'י (💍 🌿 ✡️ 🍼 🎀 💼). בורר סוג האירוע הוא המסך
 * הראשון שכל לקוח חדש רואה, ורשת של אימוג'י צבעוניים בעוצמות שונות היא
 * הדבר הראשון שמסגיר "תבנית" ולא מוצר. בנוסף אימוג'י מצויר בכל מערכת
 * הפעלה אחרת — אותה רשת נראית שונה במק, בווינדוס ובאנדרואיד.
 */
const PATHS: Record<EventType, ReactElement> = {
  // שתי טבעות משולבות
  wedding: (
    <>
      <circle cx="9.4" cy="14" r="5" />
      <circle cx="14.6" cy="14" r="5" />
      <path d="M8 6.4h2.8L9.4 8.8 8 6.4Z" />
    </>
  ),
  // ענף חינה
  henna: (
    <>
      <path d="M12 20.5V9" />
      <path d="M12 12.5C12 9.6 9.9 7.3 7 6.8c-.5 2.9 1.3 5.6 5 5.7Z" />
      <path d="M12 16.2c0-2.9 2.1-5.2 5-5.7.5 2.9-1.3 5.6-5 5.7Z" />
    </>
  ),
  // ספר תורה פתוח
  bar_mitzvah: (
    <>
      <path d="M12 7.2c-1.7-1.2-3.7-1.8-6-1.8v12c2.3 0 4.3.6 6 1.8 1.7-1.2 3.7-1.8 6-1.8v-12c-2.3 0-4.3.6-6 1.8Z" />
      <path d="M12 7.2v11.9" />
    </>
  ),
  bat_mitzvah: (
    <>
      <path d="M12 7.2c-1.7-1.2-3.7-1.8-6-1.8v12c2.3 0 4.3.6 6 1.8 1.7-1.2 3.7-1.8 6-1.8v-12c-2.3 0-4.3.6-6 1.8Z" />
      <path d="M12 7.2v11.9" />
      <path d="M9 11h1.6M13.4 11H15" />
    </>
  ),
  // עריסה
  brit: (
    <>
      <path d="M4.5 10.5h15" />
      <path d="M6 10.5v5a4 4 0 0 0 4 4h4a4 4 0 0 0 4-4v-5" />
      <path d="M8.2 10.5c.4-3.2 2-5 3.8-5s3.4 1.8 3.8 5" />
    </>
  ),
  brita: (
    <>
      <path d="M4.5 10.5h15" />
      <path d="M6 10.5v5a4 4 0 0 0 4 4h4a4 4 0 0 0 4-4v-5" />
      <path d="M8.2 10.5c.4-3.2 2-5 3.8-5s3.4 1.8 3.8 5" />
      <path d="M10.4 6.6 12 4.5l1.6 2.1" />
    </>
  ),
  // תיק עסקי
  business: (
    <>
      <rect x="3.5" y="8" width="17" height="11.5" rx="2.2" />
      <path d="M9 8V6.4A1.9 1.9 0 0 1 10.9 4.5h2.2A1.9 1.9 0 0 1 15 6.4V8" />
      <path d="M3.5 12.8h17" />
    </>
  ),
}

/** גיבוי לכל ערך שאינו מוכר — אותה נפילה-רכה כמו getEventTerms(). */
const FALLBACK: ReactElement = (
  <path d="M12 4.5 14.1 9l4.9.6-3.6 3.4.9 4.9-4.3-2.4-4.3 2.4.9-4.9L5 9.6 9.9 9 12 4.5Z" />
)

export function EventTypeIcon({ type, size = 22 }: { type: EventType; size?: number }) {
  return (
    <svg
      className="event-type-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[type] ?? FALLBACK}
    </svg>
  )
}
