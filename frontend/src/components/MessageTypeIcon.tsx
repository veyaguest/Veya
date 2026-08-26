import type { ReactElement } from 'react'
import type { MessageType } from '../types'

/**
 * אייקון לכל סוג הודעה — קווי, בצבע הטקסט שסביבו.
 *
 * קודם ישבו כאן אימוג'י (💌 👋 🔔 ⏰ 🎉 ❤️). אימוג'י נראה אחרת בכל מערכת
 * הפעלה, אי אפשר לשלוט בצבע או במשקל הקו שלו, והוא נקרא כאפליקציית
 * צ'אט ולא כמוצר בתשלום. סט אייקונים אחד — אותו משקל קו, אותו גודל,
 * אותו צבע — הוא ההבדל בין "ממשק" לבין "אוסף סמלים".
 */
const PATHS: Record<MessageType, ReactElement> = {
  // מעטפה — הזמנה
  invitation: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
      <path d="M3.6 7.2 12 13l8.4-5.8" />
    </>
  ),
  // בועת הודעה — תזכורת ראשונה
  reminder_1: (
    <>
      <path d="M20.5 12.4c0 4-3.8 7.2-8.5 7.2a9.7 9.7 0 0 1-2.6-.35L4.5 20.5l1.3-3.5A6.9 6.9 0 0 1 3.5 12.4c0-4 3.8-7.2 8.5-7.2s8.5 3.2 8.5 7.2Z" />
    </>
  ),
  // פעמון — תזכורת שנייה
  reminder_2: (
    <>
      <path d="M18 16.5V11a6 6 0 1 0-12 0v5.5L4.5 18.5h15L18 16.5Z" />
      <path d="M10 21h4" />
    </>
  ),
  // שעון — תזכורת אחרונה
  final_reminder: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.2V12l3.2 2" />
    </>
  ),
  // כוסות הרמת כוסית — יום האירוע
  event_day: (
    <>
      <path d="M5 4h6l-1.2 6a1.8 1.8 0 0 1-3.6 0L5 4Z" />
      <path d="M8 12.2V20M6 20h4" />
      <path d="M14 6.5h6l-1.2 6a1.8 1.8 0 0 1-3.6 0l-1.2-6Z" />
      <path d="M17 14.7V20M15 20h4" />
    </>
  ),
  // לב קווי — תודה
  thank_you: (
    <>
      <path d="M12 19.5s-7-4.35-7-9a3.9 3.9 0 0 1 7-2.35A3.9 3.9 0 0 1 19 10.5c0 4.65-7 9-7 9Z" />
    </>
  ),
  // עיגול עם קו — אירוע נדחה
  postponement: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 1.8" />
      <path d="M6.5 5.5 4.5 7.8M17.5 5.5l2 2.3" />
    </>
  ),
}

export function MessageTypeIcon({ type }: { type: MessageType }) {
  return (
    <svg
      className="msg-type-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[type]}
    </svg>
  )
}
