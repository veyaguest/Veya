import type { ReactElement } from 'react'

/**
 * אייקוני מצבי מסירה שאינם חלק משפת WhatsApp.
 *
 * הווי-ים (✓ / ✓✓ / ✓✓ כחול) נשארים כפי שהם — הם *ציטוט* מכוון של
 * WhatsApp, וזוג שרואה אותם מזהה מיד מה קרה. אבל ארבעת המצבים שהם
 * תוצר פנימי של VEYA (נכשל / אין מספר / חסום / בתור) הוצגו באימוג'י
 * (⚠️ 📵 🚫 ⏳), וכך ישבו זה לצד זה שני עולמות ויזואליים באותה שורה.
 * כאן הם מקבלים את אותה שפה קווית של שאר המערכת.
 */
export type DeliveryIconName = 'failed' | 'no_number' | 'blocked' | 'queued'

const PATHS: Record<DeliveryIconName, ReactElement> = {
  // משולש אזהרה — השליחה נכשלה
  failed: (
    <>
      <path d="M12 4.8 21 19.5H3L12 4.8Z" />
      <path d="M12 10.4v3.6M12 16.6v.2" />
    </>
  ),
  // טלפון עם קו חוצה — אין מספר תקין
  no_number: (
    <>
      <path d="M8.6 4.8H6.4A1.9 1.9 0 0 0 4.5 6.9c0 6.9 5.7 12.6 12.6 12.6a1.9 1.9 0 0 0 1.9-1.9v-2.2l-3.8-1.3-1.6 1.9a13.9 13.9 0 0 1-5.4-5.4l1.9-1.6L8.6 4.8Z" />
      <path d="M4 20 20 4" />
    </>
  ),
  // עיגול עם קו חוצה — המוזמן חסם
  blocked: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M6.2 6.2 17.8 17.8" />
    </>
  ),
  // שעון חול — ממתין בתור
  queued: (
    <>
      <path d="M7 4.5h10M7 19.5h10" />
      <path d="M8 4.5c0 3.2 4 4.6 4 7.5s-4 4.3-4 7.5" />
      <path d="M16 4.5c0 3.2-4 4.6-4 7.5s4 4.3 4 7.5" />
    </>
  ),
}

export function DeliveryIcon({ name }: { name: DeliveryIconName }) {
  return (
    <svg
      className="delivery-status-icon"
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}
