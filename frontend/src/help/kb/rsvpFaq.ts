/**
 * ידע: "שאלות נפוצות על אישורי הגעה" במסך אישורי ההגעה (HELP_CENTER_PLAN.md
 * שלב 10 — סנכרון ידע).
 *
 * עד שלב 10 הטקסט הזה ישב קשיח בתוך ``RsvpPage.tsx`` — בניגוד ל"חוק המקור
 * היחיד" של veya-copy, ובלי שאף בדיקה משווה אותו לעזרה. עכשיו הוא חלק מבסיס
 * הידע: המסך מציג אותו מכאן, וכל שאלה מקושרת לנושא העזרה שמסביר את אותו
 * הדבר (``topic``). helpKb.test.ts בודק ששניהם אומרים את אותם מספרים, שהטקסט
 * עובד לכל סוגי האירוע (``{guests}`` / ``{guest}`` מהלקסיקון), ושהמסך לא
 * מחזיק עותק משלו.
 *
 * עובדות (אומתו 2026-10-05):
 * - 14 ימים לפני מועד הסגירה: בקשה ראשונה + 3 תזכורות WhatsApp, ו-3 סבבי
 *   שיחות (rsvp_timeline.CYCLE). חלון קצר — נדחס, לא מתקצר.
 * - יום האירוע: הודעה רק למי שאישרו הגעה (communication: event_day → confirmed).
 * - שיחות: לוח הזמנים במסך הזה מציג אותן תמיד (rsvp_timeline לא בודק את
 *   ``features.calls``), ולכן גם השאלות כאן. העזרה עצמה מסבירה שיחות רק
 *   כשהן פעילות לאירוע — ראו HELP_CENTER_PLAN.md §24.
 */
export interface ScreenFaqItem {
  id: string
  /** נושא העזרה שמסביר את אותו הדבר — חייב להסכים איתו (helpKb.test.ts). */
  topic: string
  q: string
  /** שורה שמתחילה ב-"• " היא פריט ברשימה. */
  a: readonly string[]
  sources: readonly string[]
  verifiedAt: string
}

const VERIFIED_FAQ = '2026-10-05'
const SERVER = ['../../backend/app/rsvp_timeline.py', '../../backend/app/communication.py']

export const RSVP_SCREEN_FAQ: readonly ScreenFaqItem[] = [
  {
    id: 'faq.rsvp.how-it-works',
    topic: 'rsvp.how-it-works',
    q: 'איך עובדים אישורי ההגעה ב-VEYA?',
    a: [
      'VEYA בונה את לוח אישורי ההגעה לאחור ממועד סגירת הרשימה, ומנהלת אותו לבד. לא צריך להפעיל שום דבר.',
      '14 ימים לפני מועד סגירת הרשימה יוצאת הבקשה הראשונה, ובמהלך הימים האלה:',
      '• בקשת אישור הגעה ראשונה ועוד 3 תזכורות ב-WhatsApp',
      '• שיחות טלפון למי שעוד לא ענו, עד 3 פעמים',
      'כשנשארים פחות מ-14 ימים, כל השלבים נשארים והלוח נעשה צפוף יותר — לפעמים תזכורת ושיחת טלפון באותו יום.',
      'ההזמנה עצמה נפרדת: היא יוצאת מיד כשאתם שולחים אותה, והיא לא משנה את לוח הזמנים.',
    ],
    sources: SERVER,
    verifiedAt: VERIFIED_FAQ,
  },
  {
    id: 'faq.rsvp.final-count',
    topic: 'rsvp.when-requests',
    q: 'מתי נדע כמה מגיעים סופית?',
    a: [
      'במועד סגירת הרשימה שהוגדר לאירוע.',
      'VEYA מנהלת את אישורי ההגעה ב-14 הימים שלפני המועד הזה, בהודעות WhatsApp ובשיחות טלפון, כדי שבסיום יהיה לכם מספר סופי של ה{guests} שמגיעים.',
    ],
    sources: SERVER,
    verifiedAt: VERIFIED_FAQ,
  },
  {
    id: 'faq.rsvp.phone-calls',
    topic: 'rsvp.how-it-works',
    q: 'האם יש גם תזכורות טלפוניות אנושיות?',
    a: [
      'כן.',
      'בנוסף להודעות ב-WhatsApp, מי שעוד לא ענו מקבלים שיחת טלפון, עד 3 פעמים במהלך 14 ימי אישורי ההגעה.',
      'כלומר, VEYA לא מסתמכת רק על הודעות — ה{guests} שלא השלימו את האישור מקבלים גם טיפול טלפוני כחלק מהתהליך.',
    ],
    sources: [...SERVER, '../../backend/app/call_center.py'],
    verifiedAt: VERIFIED_FAQ,
  },
  {
    id: 'faq.rsvp.event-day',
    topic: 'rsvp.event-day',
    q: 'מה קורה ביום האירוע?',
    a: [
      'ביום האירוע ה{guests} שאישרו הגעה מקבלים הודעת תזכורת אחרונה, שכוללת את הפרטים החשובים להגעה:',
      '• מספר השולחן',
      '• ניווט לאירוע',
      '• תזכורת לאירוע',
      'כך ה{guests} לא צריכים לחפש את פרטי האירוע ברגע האחרון.',
    ],
    sources: SERVER,
    verifiedAt: VERIFIED_FAQ,
  },
]
