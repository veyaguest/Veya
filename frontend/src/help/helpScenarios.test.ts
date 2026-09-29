/**
 * תרחישים מקצה לקצה של העזרה — המנוע + הידע האמיתי, על מצבים אמיתיים של VEYA.
 *
 * הרצה: `npm run test:help`.
 *
 * כל תרחיש כאן הוא "משתמש פותח עזרה במסך X, והאירוע שלו במצב Y" — ובודק
 * מה בדיוק הוא רואה: אילו נושאים, באיזה סדר, איזו תשובה, איזו פעולה, ומה
 * עץ התקלות מסיק. הודעות השגיאה מועתקות מהשרת (ובבדיקת השלמות נאכף שהן
 * עדיין קיימות שם).
 */
import type { Facts } from './facts'
import type { ScopeId } from './scopes'
import { FLOWS, TOPICS, TREES } from './kb/index'
import { MOCK_NOTICE } from './kb/shared'
import { rankTopics, resolveTopic } from './engine/topics'
import type { RankContext } from './engine/topics'
import { runTree } from './engine/diagnose'
import { activeSteps, canStartFlow } from './engine/flows'
import { search } from './engine/search'
import type { TextContext } from './engine/text'
import { strings } from '../strings/he'
import { getEventTerms } from '../strings/eventTypes'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}
function eq<T>(actual: T, expected: T, msg: string): void {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  if (a !== b) throw new Error(`✗ ${msg}\n  התקבל:  ${a}\n  ציפינו: ${b}`)
}

function uiText(path: string): string | undefined {
  let cur: unknown = strings
  for (const key of path.split('.')) {
    if (cur === null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[key]
  }
  return typeof cur === 'string' ? cur : undefined
}

function text(type: string, facts: Facts): TextContext {
  const t = getEventTerms(type)
  return {
    facts,
    terms: {
      guests: t.guestsLabel,
      guest: t.guestsLabel === 'משתתפים' ? 'משתתף' : 'מוזמן',
      hosts: t.hostsLabel,
      event: t.eventNoun,
    },
    ui: uiText,
  }
}

/** אירוע חתונה טיפוסי, בעלים, דסקטופ, WhatsApp אמיתי, המסלול באמצע. */
const BASE: Facts = {
  'user.role': 'owner',
  'layout.guestCards': false,
  'layout.hallDesktop': true,
  'client.contactPicker': false,
  'client.online': true,
  'event.days_to_event': 30,
  'event.has_date': true,
  'event.commit_chosen': true,
  'event.edit_unlocked': false,
  'event.postpone': 'none',
  'event.can_request_postpone': true,
  'rsvp.phase': 'running',
  'rsvp.start_date': '2026-10-15',
  'rsvp.commit_date': '2026-10-29',
  'rsvp.next_date': '2026-10-20',
  'rsvp.next_label': 'תזכורת שנייה',
  'rsvp.today_is_weekend': false,
  'messaging.mode': 'live',
  'messaging.emergency_stop': false,
  'messaging.invitation_empty': false,
  'invites.sent': 40,
  'invites.not_yet': 0,
  'guests.total': 120,
  'guests.bad_phone': 0,
  'guests.confirmed': 60,
  'feature.calls': true,
  'gifts.eligible': false,
  'seating.undo_available': false,
}

function ctx(scopes: ScopeId[], facts: Facts, type = 'wedding'): RankContext {
  return {
    scopes,
    facts,
    text: text(type, facts),
    recentErrors: [],
    now: 1_000_000,
    notHelped: new Set(),
    flows: FLOWS,
  }
}

const ids = (r: ReturnType<typeof rankTopics>) => r.topics.map((t) => t.topic.id)
const topic = (id: string) => TOPICS.find((t) => t.id === id)!
const tree = (id: string) => TREES.find((t) => t.id === id)!
const outcome = (id: string, facts: Facts, answers: Record<string, number> = {}) => {
  const s = runTree(tree(id), facts, answers).step
  return s.kind === 'outcome' ? s.node : s.kind === 'ask' ? `ask:${s.node}` : `cant-check:${s.node}`
}

// ─── ניהול הודעות ──────────────────────────────────────────────────────────

function scenarioFirstInvitation(): void {
  const f: Facts = { ...BASE, 'invites.sent': 0, 'invites.not_yet': 118, 'rsvp.phase': 'before', 'messages.wizardStep': 1 }
  const r = rankTopics(TOPICS, ctx(['messages.wizard.design', 'messages'], f))
  eq(
    ids(r),
    ['invitation.wording', 'invitation.how-to-send', 'invitation.vs-rsvp', 'rsvp.when-requests'],
    'אשף ההזמנה, שלב העיצוב: נוסח → איך שולחים → הזמנה≠אישור → מתי בקשות האישור',
  )
  const how = r.topics[1]
  eq(how.answer[0], 'במסך "ניהול הודעות": בוחרים נוסח, בודקים את המוזמנים, ולוחצים "שליחת הזמנות".', 'תשובת "איך שולחים" להזמנה ראשונה')
  eq(how.mockNotice, false, 'WhatsApp אמיתי → בלי הודעת הדגמה')
  eq(r.topics[3].answer[0], 'הבקשה הראשונה תצא ביום חמישי, 15 באוקטובר. עד אז לא יוצאת אף בקשה.', 'התאריך האמיתי בתשובה')

  const withBad = rankTopics(TOPICS, ctx(['messages.wizard.recipients', 'messages'], { ...f, 'guests.bad_phone': 2 }))
  eq(withBad.urgent?.topic.id, 'invitation.who-wont-get', 'יש מספרים לא תקינים ויש למי לשלוח → "חשוב עכשיו"')
  eq(withBad.urgent?.answer[0], 'ל-2 מוזמנים אין מספר טלפון תקין — ההזמנה לא תצא עד שהמספר יתוקן.', 'המספר האמיתי')

  const mock = rankTopics(TOPICS, ctx(['messages.wizard.design', 'messages'], { ...f, 'messaging.mode': 'mock' }))
  eq(mock.topics.filter((t) => t.mockNotice).map((t) => t.topic.id), ['invitation.how-to-send', 'invitation.vs-rsvp', 'rsvp.when-requests'], 'מצב הדגמה: כל נושא על שליחה מקבל הודעה כנה')
  eq(mock.topics.find((t) => t.topic.id === 'invitation.wording')?.mockNotice, false, 'בחירת נוסח — לא על שליחה')
  console.log('✓ ניהול הודעות לפני הזמנה ראשונה: הנושאים הנכונים, תאריך אמיתי, ובמצב הדגמה — הודעה כנה')
}

function scenarioSendInvitationSteps(): void {
  const flow = FLOWS['send-invitations']
  const first: Facts = { ...BASE, 'invites.sent': 0, 'invites.not_yet': 50, 'messages.wizardStep': 1 }
  eq(canStartFlow(flow, first), true, 'יש למי לשלוח → אפשר להתחיל')
  eq(activeSteps(flow, first).map((s) => s.target), ['messages.wizardToGuests', 'messages.wizardToReview', 'messages.wizardSend', 'messages.sendConfirm'], 'הזמנה ראשונה מתחילת האשף')
  eq(activeSteps(flow, { ...first, 'messages.wizardStep': 3 }).map((s) => s.target), ['messages.wizardSend', 'messages.sendConfirm'], 'באשף בשלב 3 — לא חוזרים לשלבים שעברו')
  eq(activeSteps(flow, { ...BASE, 'invites.not_yet': 3 }).map((s) => s.target), ['messages.sendMore', 'messages.sendConfirm'], 'אחרי שכבר יצאו הזמנות — הכפתור שמתחת לכרטיסים')
  eq(canStartFlow(flow, BASE), false, 'אין למי לשלוח → לא מציעים הדרכת שליחה')
  const noMode = { ...first }
  delete noMode['messaging.mode']
  eq(canStartFlow(flow, noMode), false, 'מצב השליחה לא ידוע → לא מתחילים')
  console.log('✓ הדרכת שליחת הזמנות: הצעדים לפי המצב האמיתי — בלי צעדים שכבר עברו')
}

// ─── אישורי הגעה ───────────────────────────────────────────────────────────

function scenarioRsvpWaiting(): void {
  const f: Facts = { ...BASE, 'rsvp.phase': 'waiting', 'event.commit_chosen': false, 'invites.sent': 0, 'invites.not_yet': 100 }
  const r = rankTopics(TOPICS, ctx(['rsvp'], f))
  eq(r.urgent?.topic.id, 'event.commit-date', 'לא נבחר מועד סגירה → "חשוב עכשיו"')
  eq(r.urgent?.primary?.action, { kind: 'tour', flow: 'choose-commit-date' }, 'עם "תראו לי" לבחירת המועד')
  eq(r.topics[0].topic.id, 'rsvp.when-requests', 'הנושא הראשון: מתי יוצאות הבקשות')
  eq(r.topics[0].answer[0], 'הן יוצאות רק אחרי שתבחרו מועד סגירת רשימה, ב"עריכת פרטי האירוע".', 'מסבירים למה עוד לא יצאו')
  console.log('✓ אישורי הגעה בלי מועד סגירה: הדבר הדחוף הוא לבחור מועד — עם הדרכה')
}

function scenarioRsvpRunningAndCalls(): void {
  const r = rankTopics(TOPICS, ctx(['rsvp'], BASE))
  eq(r.urgent, null, 'מסלול רץ כרגיל → אין דחוף')
  const when = r.topics.find((t) => t.topic.id === 'rsvp.when-requests')!
  eq(when.answer, ['הצעד הבא: תזכורת שנייה, ביום שלישי, 20 באוקטובר.', 'בשישי ובשבת לא יוצאות הודעות.'], 'הצעד הבא האמיתי')
  eq(when.primary, null, 'מסלול רץ — אין מה לעשות, אין כפתור')
  const maybeOn = resolveTopic(topic('rsvp.maybe'), ctx(['rsvp'], BASE))!
  assert(maybeOn.answer[0].includes('רשימת השיחות'), 'שיחות פעילות → "לא החליטו" נשארים בשיחות')
  const maybeOff = resolveTopic(topic('rsvp.maybe'), ctx(['rsvp'], { ...BASE, 'feature.calls': false }))!
  assert(!maybeOff.answer.join(' ').includes('שיחות'), 'שיחות כבויות לאירוע → לא מבטיחים שיחות')
  const how = resolveTopic(topic('rsvp.how-it-works'), ctx(['rsvp'], { ...BASE, 'feature.calls': false }))!
  assert(!how.answer.join(' ').includes('שיחת טלפון'), 'שיחות כבויות → לא מזכירים שיחות')
  console.log('✓ אישורי הגעה במסלול רץ: הצעד הבא האמיתי, ושיחות רק כשהן פעילות לאירוע')
}

// ─── תמונת מצב ─────────────────────────────────────────────────────────────

function scenarioDashboardNoCommit(): void {
  const f: Facts = { ...BASE, 'event.commit_chosen': false, 'rsvp.phase': 'unscheduled' }
  const r = rankTopics(TOPICS, ctx(['dashboard'], f))
  eq(r.urgent?.topic.id, 'event.commit-date', 'תמונת מצב: מועד סגירה חסר → דחוף')
  eq(ids(r)[0], 'event.edit-details', 'אחריו: איך משנים פרטים')
  const change = resolveTopic(topic('event.change-date'), ctx(['dashboard'], f))!
  eq(change.answer[1], 'אם האירוע זז: ב"עריכת פרטי האירוע" ← "בקשה לשינוי מועד". אחרי אישור קצר של צוות VEYA אפשר לעדכן תאריך, שעה ומקום.', 'תאריך נעול → הדרך האמיתית: בקשה לשינוי מועד')
  const pending = resolveTopic(topic('event.change-date'), ctx(['dashboard'], { ...f, 'event.postpone': 'pending', 'event.can_request_postpone': false }))!
  eq(pending.answer, ['הבקשה לשינוי מועד ממתינה לאישור. אחרי האישור אפשר יהיה לעדכן את התאריך.'], 'בקשה ממתינה → לא מציעים לבקש שוב')
  console.log('✓ תמונת מצב: מועד סגירה חסר = דחוף; שינוי תאריך — רק בדרך שקיימת באמת')
}

// ─── סידור הושבה ───────────────────────────────────────────────────────────

function scenarioHall(): void {
  const desk = rankTopics(TOPICS, ctx(['hall'], BASE))
  eq(ids(desk), ['seating.how', 'seating.one-click', 'seating.guide', 'seating.undo'], 'מסך ההושבה: 4 הנושאים')
  eq(desk.topics[0].primary?.action, { kind: 'guide', guide: 'hall', label: 'למדריך "איך זה עובד?"' }, 'מפנים למדריך הקיים — לא מערכת עזרה שנייה')
  eq(desk.topics[3].answer[0], 'הכפתור "החזרת הסידור הקודם" מופיע רק אחרי "הושבה בקליק", ומחזיר רק את הסידור שלפני ההרצה האחרונה.', 'אין מה להחזיר → מסבירים מתי יש')
  const phone = resolveTopic(topic('seating.how'), ctx(['hall'], { ...BASE, 'layout.hallDesktop': false }, 'business'))!
  eq(phone.answer, ['לוחצים "משתתפים" בפס התחתון, בוחרים משתתף ומקישים על שולחן במפה.'], 'טלפון + אירוע עסקי: הלשונית האמיתית "משתתפים"')
  eq(canStartFlow(FLOWS['one-click-seating'], { ...BASE, 'guests.confirmed': 0 }), false, 'אין מאשרים → לא מציעים הושבה בקליק')
  console.log('✓ סידור הושבה: מפנים למדריך הקיים, ותשובות לפי פריסה וסוג אירוע')
}

// ─── עצי תקלות ─────────────────────────────────────────────────────────────

function scenarioInviteNotReceived(): void {
  const id = 'invite-not-received'
  eq(outcome(id, { ...BASE, 'messaging.mode': 'mock' }), 'out-mock', 'מצב הדגמה → אומרים את זה, בלי לבדוק מעבר')
  const mockText = runTree(tree(id), { ...BASE, 'messaging.mode': 'mock' }).step
  eq(mockText.kind === 'outcome' ? mockText.def.text : [], [MOCK_NOTICE], 'הניסוח של המייסד, מילה במילה')
  eq(outcome(id, { ...BASE, 'messaging.emergency_stop': true }), 'out-stopped', 'עצירת חירום')
  eq(outcome(id, BASE), 'cant-check:phone', 'בלי פרטי המוזמן — "אי אפשר לבדוק", לא ניחוש')
  const g = (x: Facts) => ({ ...BASE, 'guest.phone': 'valid', 'guest.rsvp': 'pending', ...x }) as Facts
  eq(outcome(id, g({ 'guest.phone': 'invalid' })), 'out-bad-phone', 'מספר לא תקין')
  eq(outcome(id, g({ 'guest.invitation': 'none' })), 'out-not-sent', 'לא נשלחה')
  eq(outcome(id, g({ 'guest.invitation': 'failed' })), 'out-failed', 'נכשלה')
  eq(outcome(id, g({ 'guest.invitation': 'blocked' })), 'out-blocked', 'חסום')
  eq(outcome(id, g({ 'guest.invitation': 'read' })), 'out-delivered', 'נקראה')
  eq(outcome(id, g({ 'guest.invitation': 'sent' })), 'out-sent', 'יצאה, בלי אישור מסירה')
  console.log('✓ "ההזמנה לא הגיעה": מצב הדגמה קודם, ואז בדיקה אמיתית של המוזמן — בלי ניחוש')
}

function scenarioInviteNotSent(): void {
  const id = 'invite-not-sent'
  eq(outcome(id, { ...BASE, 'client.online': false }), 'out-offline', 'אין אינטרנט')
  eq(outcome(id, { ...BASE, 'messaging.emergency_stop': true }), 'out-stopped', 'עצירת חירום → הבעיה אצלנו')
  eq(outcome(id, { ...BASE, 'guests.total': 0 }), 'out-no-guests', 'אין מוזמנים')
  eq(outcome(id, { ...BASE, 'messaging.invitation_empty': true }), 'out-empty', 'נוסח ריק נבדק לפני הטלפונים')
  eq(outcome(id, { ...BASE, 'guests.bad_phone': 3 }), 'out-only-bad', 'כל מי שנשאר — בלי מספר')
  eq(outcome(id, BASE), 'out-all-sent', 'כולם כבר קיבלו')
  eq(outcome(id, { ...BASE, 'invites.not_yet': 5 }), 'out-unknown', 'יש למי לשלוח ולא ידוע למה נעצר → אומרים שלא זיהינו')
  console.log('✓ "לא מצליחים לשלוח": כל סיבה אמיתית מהקוד, בסדר הנכון')
}

function scenarioRemindersNotSent(): void {
  const id = 'reminders-not-sent'
  eq(outcome(id, { ...BASE, 'event.has_date': false }), 'out-no-date', 'אין תאריך')
  eq(outcome(id, { ...BASE, 'rsvp.phase': 'waiting' }), 'out-no-commit', 'אין מועד סגירה')
  eq(outcome(id, { ...BASE, 'event.postpone': 'pending' }), 'out-postponed', 'בקשה לשינוי מועד פתוחה')
  eq(outcome(id, { ...BASE, 'event.postpone': 'approved' }), 'out-postponed', 'שינוי מועד מאושר ועוד לא הושלם')
  eq(outcome(id, { ...BASE, 'rsvp.phase': 'before' }), 'out-before', 'עוד לא הגיע הזמן')
  eq(outcome(id, { ...BASE, 'rsvp.today_is_weekend': true }), 'out-weekend', 'סוף שבוע')
  eq(outcome(id, BASE), 'out-running', 'רץ כרגיל — מסבירים את הכללים')
  console.log('✓ "בקשות אישור לא יוצאות": תאריך → מועד סגירה → שינוי מועד → עצירה → זמן → סוף שבוע')
}

function scenarioGuestCantConfirm(): void {
  const id = 'guest-cant-confirm'
  eq(outcome(id, BASE), 'ask:what', 'שואלים שאלה סגורה: מה כתוב בקישור')
  eq(outcome(id, { ...BASE, 'rsvp.phase': 'waiting' }, { what: 0 }), 'out-no-commit', '"עדיין לא נפתחו" + אין מועד סגירה')
  eq(outcome(id, { ...BASE, 'rsvp.phase': 'before' }, { what: 0 }), 'out-before', '"עדיין לא נפתחו" לפני הבקשה הראשונה — תקין')
  eq(outcome(id, BASE, { what: 1 }), 'out-dead-link', '"הקישור כבר לא פעיל"')
  eq(outcome(id, BASE, { what: 2 }), 'out-other', 'משהו אחר → לא מנחשים')
  console.log('✓ "אי אפשר לאשר בקישור": שאלה סגורה אחת, ואז תשובה לפי המצב האמיתי')
}

function scenarioEventAndSeatingErrors(): void {
  const e = (message: string, extra: Facts = {}) =>
    outcome('event-save-failed', { ...BASE, 'error.last.status': 409, 'error.last.message': message, ...extra })
  eq(e('תאריך האירוע נעול לעריכה, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.'), 'out-locked', 'שדה נעול')
  eq(e('תאריך האירוע נעול לעריכה, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.', { 'event.postpone': 'pending' }), 'out-pending', 'שדה נעול + בקשה ממתינה')
  eq(e('מועד סגירת הרשימה כבר נקבע — כל לוח הזמנים של אישורי ההגעה נבנה סביבו.'), 'out-commit-set', 'מועד סגירה נעול')
  eq(e('בתאריך הזה הרשימה כבר הייתה סגורה. אפשר לבחור פחות ימים לפני האירוע.'), 'out-commit-past', 'מועד סגירה בעבר')
  eq(e('שעת השליחה חייבת להיות בין 10:00 ל-19:00'), 'out-send-time', 'שעת שליחה')
  const s = (message: string) => outcome('seating-failed', { ...BASE, 'error.last.status': 400, 'error.last.message': message })
  eq(s('אין מוזמנים לשיבוץ'), 'out-no-guests', 'אין מוזמנים')
  eq(s('אין מוזמנים שאישרו הגעה לשיבוץ'), 'out-no-confirmed', 'אין מאשרים')
  eq(s('חבורה גדולה ממספר הכיסאות לשולחן: משפחת לוי'), 'out-big-party', 'חבורה גדולה')
  eq(s('הרזרבה גדולה מדי: אחרי השארת 20 מקומות פנויים נשארו 80 מקומות ל-95 אנשים. הקטינו את הרזרבה או הוסיפו שולחנות.'), 'out-reserve', 'רזרבה')
  console.log('✓ שגיאות שמירת פרטי אירוע והושבה בקליק — כל הודעת שרת מגיעה לפתרון שלה')
}

function scenarioSearchIncludesSymptoms(): void {
  const items = [
    ...TOPICS.map((t) => ({ id: t.id, texts: [t.title.replace(/\{[^}]*\}/g, ''), ...t.aliases] })),
    ...TREES.map((t) => ({ id: t.id, texts: [t.symptom.replace(/\{[^}]*\}/g, '')] })),
  ]
  eq(search('ההזמנה לא הגיעה', items)[0], 'invite-not-received', 'סימפטום בחיפוש → עץ התקלות')
  eq(search('מתנות באשראי', items)[0], 'gifts.unavailable', 'מתנות באשראי → תשובה כנה')
  eq(search('לשנות תאריך', items)[0], 'event.change-date', 'שינוי תאריך')
  console.log('✓ חיפוש מוצא גם סימפטומים ("ההזמנה לא הגיעה") וגם מתנות — עם תשובה כנה')
}

function scenarioGiftsHonest(): void {
  const t = topic('gifts.unavailable')
  eq(resolveTopic(t, ctx([], BASE))?.answer, ['השירות עדיין לא זמין לאירוע שלכם.'], 'לא זכאי → אומרים בפשטות')
  eq(resolveTopic(t, ctx([], { ...BASE, 'gifts.eligible': true })), null, 'זכאי → הנושא הזה לא מוצג')
  eq(rankTopics(TOPICS, ctx(['dashboard'], BASE)).topics.some((x) => x.topic.id === 'gifts.unavailable'), false, 'לא מוצג בבית של העזרה — רק בחיפוש')
  console.log('✓ מתנות באשראי: לא מוצגות כפעילות, ולא מוצעות סתם')
}

scenarioFirstInvitation()
scenarioSendInvitationSteps()
scenarioRsvpWaiting()
scenarioRsvpRunningAndCalls()
scenarioDashboardNoCommit()
scenarioHall()
scenarioInviteNotReceived()
scenarioInviteNotSent()
scenarioRemindersNotSent()
scenarioGuestCantConfirm()
scenarioEventAndSeatingErrors()
scenarioSearchIncludesSymptoms()
scenarioGiftsHonest()
console.log('OK — תרחישי העזרה מתנהגים כמו ש-VEYA מתנהגת באמת.')
