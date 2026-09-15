/**
 * מועד סגירת הרשימה — כמה ימים לפני האירוע אפשר לבחור בלי שהרשימה תיסגר
 * בתאריך שכבר עבר. זו רק חסימה של אפשרויות בבורר; האכיפה עצמה ומדיניות
 * ברירת המחדל לאירוע קרוב נמצאות בשרת (``rsvp_timeline.max_commit_days``,
 * ``resolve_commit_days``).
 */
export const MAX_COMMIT_DAYS = 10

/** הבחירה הגדולה ביותר שעדיין סוגרת את הרשימה היום או אחריו (0 = אין). */
export function maxCommitDays(eventDateIso: string, today: Date = new Date()): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(eventDateIso)
  if (!m) return MAX_COMMIT_DAYS
  const event = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  const daysOut = Math.round((event - now) / 86_400_000)
  return Math.max(0, Math.min(MAX_COMMIT_DAYS, daysOut))
}
