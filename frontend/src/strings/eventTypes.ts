/**
 * מנוע המונחים של VEYA — מקור אמת יחיד לשפה הדינמית לפי סוג אירוע.
 *
 * העיקרון: VEYA = Wedding-first, Event-ready. המערכת חזקה מאוד לחתונות,
 * אבל השפה, החוויה והארכיטקטורה מוכנות לכל סוג אירוע. במקום לקבע "חתן/כלה/
 * זוג" בכל מסך, כל טקסט תלוי-אירוע נשאב מכאן לפי event_type של האירוע.
 *
 * למה כאן ולא בתוך הקומפוננטות: כדי שאפשר יהיה להוסיף סוג אירוע חדש
 * (או לתקן ניסוח) ממקום אחד, בלי לחפש בין עשרות קבצים.
 *
 * הרחבה עתידית: להוסיף סוג אירוע = להוסיף ערך ל-EventType (types.ts),
 * רשומה ל-EVENT_TERMS כאן, ופריט ל-EVENT_TYPE_OPTIONS. שום מסך לא צריך
 * להשתנות — כולם נשענים על getEventTerms().
 *
 * עקרונות הניסוח (עקבי עם strings/he.ts): עברית מדוברת-מקצועית וחמה,
 * בלי ניסוחים מתורגמים, כתיב מלא. חתונה נשארת ברירת המחדל בכל מקום.
 */
import { getActiveEventType } from '../authStore'
import type { EventType, Side } from '../types'

export interface EventTerms {
  type: EventType
  /** שם הסוג לתצוגה בבורר סוג האירוע */
  label: string
  /** אימוג'י מלווה בבורר */
  icon: string
  /** האם יש שני בעלי אירוע (חתן+כלה) או בעל שמחה יחיד */
  hasTwoHosts: boolean
  /** כינוי קיבוצי לבעלי האירוע: "בני הזוג" / "בעל השמחה" / "מארגני האירוע" */
  hostsLabel: string
  /** תווית שדה השם הראשון: "שם החתן" / "שם חתן בר המצווה" / "שם האירוע" */
  hostAField: string
  /** תווית שדה השם השני (רלוונטי רק כש-hasTwoHosts): "שם הכלה" */
  hostBField: string
  /** תוויות הצדדים — מחליף את SIDE_LABELS הקבוע לפי סוג האירוע */
  sideLabels: Record<Side, string>
  /** שם האירוע המיודע: "החתונה" / "אירוע בר המצווה" / "האירוע" */
  eventNoun: string
  /** תווית ההזמנה: "הזמנה לחתונה" / "הזמנה לאירוע" */
  inviteLabel: string
  /** כותרת ברירת מחדל כשאין עדיין שמות: "החתונה שלנו" / "האירוע שלנו" */
  defaultTitle: string
  /** בונה "החתונה של דני ומאיה" / "אירוע בר המצווה של איתי" */
  celebrationOf: (names: string) => string
}

const WEDDING: EventTerms = {
  type: 'wedding',
  label: 'חתונה',
  icon: '💍',
  hasTwoHosts: true,
  hostsLabel: 'בני הזוג',
  hostAField: 'שם החתן',
  hostBField: 'שם הכלה',
  sideLabels: { groom: 'חתן', bride: 'כלה', shared: 'משותף' },
  eventNoun: 'החתונה',
  inviteLabel: 'הזמנה לחתונה',
  defaultTitle: 'החתונה שלנו',
  celebrationOf: (names) => `החתונה של ${names}`,
}

export const EVENT_TERMS: Record<EventType, EventTerms> = {
  wedding: WEDDING,
  henna: {
    type: 'henna',
    label: 'חינה',
    icon: '🌿',
    hasTwoHosts: true,
    hostsLabel: 'בני הזוג',
    hostAField: 'שם החתן',
    hostBField: 'שם הכלה',
    sideLabels: { groom: 'חתן', bride: 'כלה', shared: 'משותף' },
    eventNoun: 'החינה',
    inviteLabel: 'הזמנה לחינה',
    defaultTitle: 'החינה שלנו',
    celebrationOf: (names) => `החינה של ${names}`,
  },
  bar_mitzvah: {
    type: 'bar_mitzvah',
    label: 'בר מצווה',
    icon: '✡️',
    hasTwoHosts: false,
    hostsLabel: 'בעל השמחה',
    hostAField: 'שם חתן בר המצווה',
    hostBField: '',
    sideLabels: { groom: 'צד האב', bride: 'צד האם', shared: 'משותף' },
    eventNoun: 'אירוע בר המצווה',
    inviteLabel: 'הזמנה לבר מצווה',
    defaultTitle: 'אירוע בר המצווה',
    celebrationOf: (names) => `אירוע בר המצווה של ${names}`,
  },
  bat_mitzvah: {
    type: 'bat_mitzvah',
    label: 'בת מצווה',
    icon: '✡️',
    hasTwoHosts: false,
    hostsLabel: 'בעלת השמחה',
    hostAField: 'שם בת המצווה',
    hostBField: '',
    sideLabels: { groom: 'צד האב', bride: 'צד האם', shared: 'משותף' },
    eventNoun: 'אירוע בת המצווה',
    inviteLabel: 'הזמנה לבת מצווה',
    defaultTitle: 'אירוע בת המצווה',
    celebrationOf: (names) => `אירוע בת המצווה של ${names}`,
  },
  brit: {
    type: 'brit',
    label: 'ברית / בריתה',
    icon: '🍼',
    hasTwoHosts: false,
    hostsLabel: 'המשפחה',
    hostAField: 'שם המשפחה',
    hostBField: '',
    sideLabels: { groom: 'צד האב', bride: 'צד האם', shared: 'משותף' },
    eventNoun: 'הברית',
    inviteLabel: 'הזמנה לברית',
    defaultTitle: 'הברית שלנו',
    celebrationOf: (names) => `הברית של ${names}`,
  },
  family: {
    type: 'family',
    label: 'אירוע משפחתי',
    icon: '🎈',
    hasTwoHosts: false,
    hostsLabel: 'המשפחה',
    hostAField: 'שם בעל/ת השמחה',
    hostBField: '',
    sideLabels: { groom: 'צד א׳', bride: 'צד ב׳', shared: 'משותף' },
    eventNoun: 'האירוע המשפחתי',
    inviteLabel: 'הזמנה לאירוע',
    defaultTitle: 'האירוע שלנו',
    celebrationOf: (names) => `האירוע של ${names}`,
  },
  business: {
    type: 'business',
    label: 'אירוע עסקי',
    icon: '💼',
    hasTwoHosts: false,
    hostsLabel: 'מארגני האירוע',
    hostAField: 'שם האירוע / הארגון',
    hostBField: '',
    sideLabels: { groom: 'צד א׳', bride: 'צד ב׳', shared: 'משותף' },
    eventNoun: 'האירוע',
    inviteLabel: 'הזמנה לאירוע',
    defaultTitle: 'האירוע שלנו',
    celebrationOf: (names) => `האירוע של ${names}`,
  },
  other: {
    type: 'other',
    label: 'אחר',
    icon: '✨',
    hasTwoHosts: false,
    hostsLabel: 'מארגני האירוע',
    hostAField: 'שם האירוע',
    hostBField: '',
    sideLabels: { groom: 'צד א׳', bride: 'צד ב׳', shared: 'משותף' },
    eventNoun: 'האירוע',
    inviteLabel: 'הזמנה לאירוע',
    defaultTitle: 'האירוע שלנו',
    celebrationOf: (names) => `האירוע של ${names}`,
  },
}

/** רשימת סוגי האירוע לבורר, בסדר התצוגה הרצוי (חתונה ראשונה — Wedding-first). */
export const EVENT_TYPE_OPTIONS: { type: EventType; label: string; icon: string }[] = [
  'wedding',
  'bar_mitzvah',
  'bat_mitzvah',
  'henna',
  'brit',
  'family',
  'business',
  'other',
].map((t) => {
  const terms = EVENT_TERMS[t as EventType]
  return { type: terms.type, label: terms.label, icon: terms.icon }
})

/**
 * שולף את מנוע המונחים לסוג אירוע. חתונה היא ברירת המחדל הבטוחה — כל ערך
 * חסר/לא מוכר נופל אליה, כך שאף מסך לא יישבר אם event_type ריק.
 */
export function getEventTerms(type: EventType | string | null | undefined): EventTerms {
  if (type && type in EVENT_TERMS) return EVENT_TERMS[type as EventType]
  return WEDDING
}

/**
 * מנוע המונחים של האירוע הפעיל (נקרא מ-authStore). שימושי במסכים שלא
 * מקבלים event_type ב-prop — למשל תוויות צדדים ברשימת המוזמנים ובמפת האולם.
 * חתונה היא ברירת המחדל הבטוחה.
 */
export function activeEventTerms(): EventTerms {
  return getEventTerms(getActiveEventType())
}

/** תווית הצד לפי סוג האירוע הפעיל (חתן/כלה לחתונה, צד האב/האם לבר מצווה וכו'). */
export function sideLabel(side: Side): string {
  return activeEventTerms().sideLabels[side]
}

/**
 * מרכיב את שמות בעלי האירוע לתצוגה: "דני ומאיה" לחתונה, או שם יחיד לבעל
 * שמחה. מחזיר מחרוזת ריקה כשאין שמות (הקורא נופל ל-defaultTitle).
 */
export function hostNames(terms: EventTerms, groomName: string, brideName: string): string {
  const a = (groomName || '').trim()
  const b = (brideName || '').trim()
  if (terms.hasTwoHosts) {
    if (a && b) return `${a} ו${b}`
    return a || b
  }
  return a || b
}

/**
 * הכותרת המלאה של האירוע: "החתונה של דני ומאיה" / "אירוע בר המצווה של איתי".
 * כשאין שמות — מחזיר את כותרת ברירת המחדל של הסוג.
 */
export function celebrationTitle(
  type: EventType | string | null | undefined,
  groomName: string,
  brideName: string,
): string {
  const terms = getEventTerms(type)
  const names = hostNames(terms, groomName, brideName)
  return names ? terms.celebrationOf(names) : terms.defaultTitle
}
