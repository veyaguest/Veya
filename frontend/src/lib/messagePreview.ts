/**
 * תצוגה מקדימה של הודעה למוזמן — מקור אמת יחיד בצד הלקוח.
 *
 * למה זה קיים כמודול משותף ולא בתוך כל מסך: עד עכשיו כל מסך החזיק מפת ערכי
 * דוגמה משלו, ושתיהן היו חלקיות. במסך "שליחת הזמנות" — המסך האחרון שהזוג
 * רואה לפני שההודעה יוצאת — המפה הכילה שמונה מפתחות ישנים בלבד, ולכן
 * ``[שם פרטי]``, ``[שמות בעלי האירוע]`` ו-``[קישור אישור]`` הוחלפו במחרוזת
 * ריקה והזוג ראה הודעה קטועה שאינה מה שנשלח בפועל.
 *
 * ``renderMessagePreview`` הוא תאום מדויק של ``render_automation_template``
 * בשרת (backend/app/messaging.py): אותה מחיקת שורה שכל הפרטים בה ריקים,
 * אותה מחיקת מפריד שנשען על פרט שנעלם, ואותו איחוד שורות ריקות. שינוי
 * בכללים שם מחייב שינוי מקביל כאן.
 */
import { getEventTerms, hostNames } from '../strings/eventTypes'
import type { EventDetails } from '../types'

/** תווי הפרדה שמחברים שני ערכים באותה שורה — נמחקים עם ערך שנעלם. */
const SEPARATORS = /[,·|–—]/

/**
 * ערכי הדוגמה לכל טוקן שהמערכת מכירה — החדשים, הידידותיים והישנים כאחד.
 *
 * ערך *ריק* הוא משמעותי: הוא מדמה פרט שעדיין לא הוזן באירוע, וגורם לשורה
 * שלמה להיעלם — בדיוק כפי שיקרה בשליחה. לכן אין כאן טקסטי מציין-מקום כמו
 * "תאריך האירוע"; אירוע בלי תאריך צריך להיראות בתצוגה בלי שורת תאריך.
 */
export function buildSampleTokens(
  event: EventDetails | null,
  guestFullName: string,
  // מוזמן-דוגמה אמיתי (השולחן שלו כרגע, אם יש) — כשמועבר, [מספר שולחן]
  // בתצוגה המקדימה משקף שיבוץ אמיתי במקום מספר קבוע, בדיוק כמו בשליחה
  // בפועל (כולל היעלמות השורה אם המוזמן עדיין לא שובץ). לא מועבר → מספר
  // קבוע לדוגמה, כמו קודם (למשל כשעוד אין אף מוזמן באירוע).
  realGuestTableNumber?: number | null,
): Record<string, string> {
  const terms = getEventTerms(event?.event_type)
  // דרך hostNames, שמכבד סוג אירוע עם בעל שמחה יחיד — חיבור ידני ב-' ו'
  // היה מייצר "יונתן ושרה" בבר מצווה שיש בו שם שיורי בשדה השני.
  const hosts =
    hostNames(terms, event?.groom_name || '', event?.bride_name || '') || terms.hostsLabel
  const first = (guestFullName || '').split(/\s+/)[0] || ''
  const date = event?.event_date || ''
  const time = event?.event_time || ''
  const venue = event?.venue_name || ''
  const addr = event?.venue_address || ''
  const groomParents = event?.groom_parents_line || ''
  const brideParents = event?.bride_parents_line || ''
  // קישורי הניווט נגזרים מהכתובת — בלי כתובת אין ניווט, וגם השורה נעלמת.
  const nav = addr ? 'https://maps.google.com/…' : ''
  const waze = addr ? 'https://waze.com/ul?q=…' : ''
  const rsvp = 'https://veya.co.il/confirm/…'
  const tableNumber =
    realGuestTableNumber === undefined
      ? '12'
      : realGuestTableNumber != null
        ? String(realGuestTableNumber)
        : ''

  return {
    // שם המוזמן (טכני, ידידותי וישן)
    '{{first_name}}': first, '{{guest_name}}': first,
    '[שם פרטי]': first, '[שם אורח]': first,
    // בעלי האירוע — כל הווריאציות של TOKEN_VOCABULARY בשרת (messaging.py).
    // כולן מצביעות לאותו ערך; מה שמשתנה בין סוגי האירוע הוא רק איזו מהן
    // כתובה בנוסח ומוצעת בבורר.
    '{{event_name}}': hosts, '{{couple_names}}': hosts,
    '[שמות בעלי האירוע]': hosts, '[שמות בני הזוג]': hosts,
    '[שם החוגג]': hosts, '[שם החוגגת]': hosts, '[שם בעל השמחה]': hosts,
    '[שם המשפחה]': hosts, '[שם החברה]': hosts, '[שם האירוע]': hosts,
    '[משפחת התינוק]': hosts, // כינוי ותיק — נשמר כדי שנוסח שנשמר איתו יעבוד
    '{{groom_name}}': event?.groom_name || '', '[שם החתן]': event?.groom_name || '',
    '{{bride_name}}': event?.bride_name || '', '[שם הכלה]': event?.bride_name || '',
    // שורת המשפחה/ההורים בהזמנה דתית
    '{{groom_parents_line}}': groomParents,
    '[הורי החתן]': groomParents, '[הורי החוגג]': groomParents,
    '[משפחת החוגג]': groomParents, '[משפחת החוגגת]': groomParents,
    '{{bride_parents_line}}': brideParents, '[הורי הכלה]': brideParents,
    // שם האירוע לפי סוגו
    '{{celebration}}': terms.celebration, '[האירוע]': terms.celebration,
    '{{celebration_of}}': terms.celebrationConstruct, '[שמחת]': terms.celebrationConstruct,
    // מתי ואיפה
    '{{event_date}}': date, '[תאריך]': date, '[תאריך האירוע]': date,
    '{{event_time}}': time, '[שעה]': time,
    '{{venue_name}}': venue, '[שם האולם]': venue,
    '{{venue_address}}': addr, '[כתובת]': addr,
    // קישורים
    '{{confirmation_link}}': rsvp, '{{rsvp_link}}': rsvp, '[קישור אישור]': rsvp,
    '{{navigation_link}}': nav, '{{maps_link}}': nav, '[קישור ניווט]': nav,
    '{{waze_link}}': waze, '[קישור וייז]': waze,
    // פרטי המוזמן בשיבוץ
    '{{table_number}}': tableNumber, '[מספר שולחן]': tableNumber,
    '{{guest_count}}': '2', '[כמות מקומות]': '2',
    // ממולא רק בשליחת עדכון אירוע — ריק כאן, ולכן השורה נעלמת.
    '{{update_details}}': '', '[פרטי שינוי]': '',
    // טוקנים שהוצאו מהבורר אך עשויים להופיע בתבנית שמורה ותיקה.
    '{{gift_link}}': '', '[קישור מתנה]': '',
    '{{photo_gallery}}': '', '[גלריית תמונות]': '',
    '{{video_gallery}}': '', '[גלריית וידאו]': '',
  }
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * מפריד שורות שמכילות קישור (URL) משאר גוף ההודעה.
 *
 * כשוואטסאפ מחובר, קישור אישור/ניווט/מתנה מוצג ככפתור CTA בתחתית הבועה —
 * לא כשורת URL בתוך הטקסט. הפונקציה מחזירה את הטקסט בלי שורות הקישור,
 * ודגל האם הייתה שורת קישור בכלל (כדי להחליט אם להציג כפתור).
 */
export function splitMessageLinks(text: string): { body: string; hasLink: boolean } {
  const linkRe = /https?:\/\//
  const lines = text.split('\n')
  const drop = new Array(lines.length).fill(false)
  let hasLink = false
  lines.forEach((line, i) => {
    if (!linkRe.test(line)) return
    hasLink = true
    drop[i] = true
    // שורת תווית שקדמה לקישור ("לאישור הגעה:") — יורדת יחד איתו, כדי
    // שלא תישאר תווית מיותמת מעל הכפתור.
    for (let j = i - 1; j >= 0; j--) {
      if (lines[j].trim() === '') continue
      if (/[:：]\s*$/.test(lines[j])) drop[j] = true
      break
    }
  })
  const body = lines
    .filter((_, i) => !drop[i])
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return { body, hasLink }
}

/**
 * ממלא תבנית בערכי דוגמה, בדיוק כמו השרת בשליחה בפועל.
 *
 * שלושת הכללים שחייבים להישאר זהים ל-``render_automation_template``:
 * 1. שורה שכל הפרטים שבה ריקים — נמחקת כולה.
 * 2. מפריד שנשען על פרט ריק — נמחק יחד איתו ("דנה ויואב · " ← "דנה ויואב").
 * 3. נקודתיים שהבטיחו שורות שנמחקו — יורדות.
 */
export function renderMessagePreview(
  text: string,
  sample: Record<string, string>,
): string {
  // טוקנים ארוכים לפני קצרים, כדי ש-"[תאריך האירוע]" לא ייחתך ל-"[תאריך]".
  const tokens = Object.keys(sample).sort((a, b) => b.length - a.length)
  const lines: string[] = []
  let droppedAny = false

  for (const raw of text.split('\n')) {
    let line = raw
    const present = tokens.filter((tok) => line.includes(tok))
    if (present.length > 0 && present.every((tok) => sample[tok] === '')) {
      droppedAny = true
      continue
    }
    for (const tok of present) {
      if (sample[tok] !== '') continue
      const esc = escapeRe(tok)
      line = line.replace(new RegExp(`[ \\t]*${SEPARATORS.source}[ \\t]*${esc}`, 'g'), '')
      line = line.replace(new RegExp(`${esc}[ \\t]*${SEPARATORS.source}[ \\t]*`, 'g'), '')
    }
    for (const tok of tokens) {
      if (line.includes(tok)) line = line.split(tok).join(sample[tok])
    }
    if (present.length > 0) line = line.replace(/[ \t]{2,}/g, ' ').replace(/[ \t]+$/, '')
    lines.push(line)
  }

  let out = lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()
  if (droppedAny) out = out.replace(/\s*:\s*$/, '')
  return out
}
