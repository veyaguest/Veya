/**
 * מדריכים שכבר קיימים בתוך מסכים — העזרה פותחת אותם במקום להמציא הסבר מקביל.
 *
 * "איך זה עובד?" של סידור ההושבה (``hm-help-btn`` ב-HallPage) הוא מדריך אמיתי
 * עם הדגמה. במסך ההושבה אין כפתור עזרה שני (החלטת המייסד 2026-09-29): העזרה
 * מפנה לאותו מדריך, כדי שתהיה חוויית עזרה אחת.
 *
 * ``target`` — הכפתור שפותח את המדריך (help/targets.ts), ו-``opener`` — הקוד
 * שחייב להופיע **על הכפתור הזה עצמו** (נבדק ב-helpKb.test.ts). כך אם הכפתור
 * יוסר או יפסיק לפתוח את המדריך — הבדיקה נכשלת, ולא נשארת פעולה שלא עושה
 * כלום. החיבור בפועל (פתיחה מתוך העזרה) נבנה בשלב 4.
 */
import type { HelpPage, TargetId } from './targets'

export const GUIDES = {
  hall: {
    file: 'components/HallPage.tsx',
    page: 'hall',
    target: 'hall.guideButton',
    opener: 'onClick={() => setGuideOpen(true)}',
    note: 'המדריך של סידור ההושבה — כפתור "איך זה עובד?" בפס העליון של המסך (דסקטופ וטלפון)',
  },
} as const satisfies Record<string, { file: string; page: HelpPage; target: TargetId; opener: string; note: string }>

export type GuideId = keyof typeof GUIDES
