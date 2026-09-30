/**
 * הדרכות "תראו לי" — כללי הבטיחות של HELP_CENTER_PLAN.md §9.2 (שלב 6).
 *
 * הרצה: `npm run test:help`.
 *
 *  1. צעד שמבצע פעולה שקשה/אי אפשר לבטל (שליחה, קביעה סופית, סידור מחדש)
 *     מסומן בשורת אזהרה — והאזהרה אומרת את מה שהאפליקציה עצמה אומרת במסך.
 *  2. צעד עם אזהרה ממשיך רק לפי אישור מהשרת — אף פעם לא "הבא" ולא לחיצה.
 *  3. כל הדרכה נגמרת רק באישור מהשרת, והצעד האחרון מחכה לאותו אישור.
 *  4. כרטיס ההדרכה: האזהרה והשורה מוצגות רק כשהיעד גלוי; כשהכפתור לא נמצא —
 *     לא מציגים את ההוראה שמפנה אליו, אלא "חזרה לעזרה" או סגירה.
 */
import { FLOWS, TOPICS } from './kb/index'
import type { GuidedFlow } from './types'
import type { Facts } from './facts'
import { canStartFlow } from './engine/flows'
import { resolveTopic } from './engine/topics'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
}
declare function require(name: 'fs'): Fs
declare const __dirname: string
const SRC = `${__dirname}/../../src`
const fs = require('fs')
const readSrc = (rel: string) => fs.readFileSync(`${SRC}/${rel}`, 'utf8')

/**
 * הצעדים שמבצעים פעולה שקשה או אי אפשר לבטל, והמשפט שהאפליקציה עצמה אומרת
 * עליה (חייב להופיע גם בקובץ המקור וגם באזהרה — כך האזהרה לא ממציאה).
 * פעולה חדשה כזו בהדרכה בלי שורה כאן → הבדיקה נכשלת (ראו testEveryIrreversibleStep).
 */
const IRREVERSIBLE: readonly { flow: string; target: string; says: string; source: string }[] = [
  { flow: 'send-invitations', target: 'messages.sendConfirm', says: 'פעם אחת בלבד', source: 'components/MessagesPage.tsx' },
  { flow: 'choose-commit-date', target: 'dashboard.saveDetails', says: 'אחרי השמירה אי אפשר לשנות את הבחירה', source: 'strings/he.ts' },
  { flow: 'one-click-seating', target: 'hall.oneClick', says: 'אפשר להחזיר את הסידור הקודם', source: 'strings/he.ts' },
]

/** בקשות שמבצעות פעולה כזו — כל צעד שמחכה להן חייב להופיע ב-IRREVERSIBLE. */
const IRREVERSIBLE_ROUTES: readonly string[] = ['POST /automation/track/activate', 'POST /seating/generate']

function flow(id: string): GuidedFlow {
  const f = FLOWS[id]
  assert(!!f, `אין הדרכה ${id}`)
  return f
}

/** נמצא בבדיקת שלב 6: בלי נוסח להזמנה — השליחה לא שולחת כלום, אז לא מדריכים אליה. */
function testNoSendTourWithoutInvitationText(): void {
  const base: Facts = {
    'user.role': 'owner', 'messaging.mode': 'mock', 'invites.sent': 0, 'invites.not_yet': 5,
  }
  const send = flow('send-invitations')
  assert(canStartFlow(send, { ...base, 'messaging.invitation_empty': false }), 'עם נוסח — ההדרכה לשליחה זמינה')
  assert(!canStartFlow(send, { ...base, 'messaging.invitation_empty': true }), 'בלי נוסח — ההדרכה לשליחה לא מתחילה')
  assert(!canStartFlow(send, base), 'לא ידוע אם יש נוסח — לא מתחילים (לא מנחשים)')
  const topic = TOPICS.find((t) => t.id === 'invitation.how-to-send')!
  const terms = { guests: 'מוזמנים', guest: 'מוזמן', hosts: 'הזוג', event: 'החתונה' }
  const ui = () => undefined
  const r = resolveTopic(topic, { facts: { ...base, 'messaging.invitation_empty': true }, text: { facts: { ...base, 'messaging.invitation_empty': true }, terms, ui }, flows: FLOWS })
  assert(!!r, 'בלי נוסח — עדיין יש תשובה')
  assert(r!.answer.join(' ').includes('עוד אין נוסח'), `בלי נוסח — התשובה אומרת שקודם בוחרים נוסח: "${r!.answer.join(' ')}"`)
  assert(r!.primary === null, 'בלי נוסח — אין "תראו לי" לשליחה')
  console.log('✓ בלי נוסח להזמנה: אין הדרכה לשליחה, והתשובה אומרת לבחור נוסח קודם')
}

function testWarningsOnIrreversibleSteps(): void {
  for (const x of IRREVERSIBLE) {
    const step = flow(x.flow).steps.find((s) => s.target === x.target)
    assert(!!step, `${x.flow}: אין צעד על ${x.target}`)
    assert(!!step!.warning, `${x.flow}/${x.target}: פעולה שקשה לבטל בלי שורת אזהרה`)
    assert(step!.warning!.text.includes(x.says), `${x.flow}/${x.target}: האזהרה לא אומרת "${x.says}" — "${step!.warning!.text}"`)
    assert(readSrc(x.source).includes(x.says), `${x.flow}: "${x.says}" לא מופיע ב-${x.source} — האזהרה לא נשענת על מה שהמסך אומר`)
  }
  // "אפשר להחזיר" — אסור שהאזהרה תגיד "אי אפשר לבטל" על פעולה שאפשר לבטל.
  const seating = flow('one-click-seating').steps.find((s) => s.target === 'hall.oneClick')!
  assert(!/אי אפשר/.test(seating.warning!.text), 'הושבה בקליק: האזהרה מגזימה — אפשר להחזיר את הסידור הקודם')
  console.log(`✓ ${IRREVERSIBLE.length} צעדים שקשה לבטל מסומנים באזהרה, בניסוח שהמסך עצמו משתמש בו`)
}

function testEveryIrreversibleStep(): void {
  const listed = new Set(IRREVERSIBLE.map((x) => `${x.flow}/${x.target}`))
  for (const f of Object.values(FLOWS)) {
    for (const s of f.steps) {
      const sig = s.advanceOn
      const route = sig.kind === 'api' ? `${sig.method} ${sig.path}` : ''
      if (IRREVERSIBLE_ROUTES.includes(route)) {
        assert(listed.has(`${f.id}/${s.target}`), `${f.id}/${s.target}: מחכה ל-${route} — פעולה שקשה לבטל, בלי שורה ב-IRREVERSIBLE`)
      }
      // ולהפך: אזהרה רק על צעד שבאמת מופיע ברשימה (לא אזהרות "ליתר ביטחון").
      if (s.warning) assert(listed.has(`${f.id}/${s.target}`), `${f.id}/${s.target}: אזהרה על צעד שלא ברשימת הפעולות שקשה לבטל`)
    }
  }
  console.log('✓ כל צעד שמחכה לשליחה/לסידור מחדש מופיע ברשימה — ואין אזהרות מיותרות')
}

function testWarningStepsWaitForTheServer(): void {
  let n = 0
  for (const f of Object.values(FLOWS)) {
    for (const s of f.steps) {
      if (!s.warning) continue
      n++
      assert(s.advanceOn.kind === 'api', `${f.id}/${s.target}: צעד עם אזהרה חייב לחכות לאישור מהשרת, לא ל-${s.advanceOn.kind}`)
    }
    // "סיימנו" רק באישור השרת, והצעד האחרון מחכה בדיוק לו.
    const last = f.steps[f.steps.length - 1].advanceOn
    assert(
      last.kind === 'api' && last.method === f.success.method && last.path === f.success.path,
      `${f.id}: הצעד האחרון לא מחכה לאישור ההצלחה מהשרת`,
    )
  }
  assert(n === IRREVERSIBLE.length, `ציפינו ל-${IRREVERSIBLE.length} צעדים עם אזהרה, נמצאו ${n}`)
  console.log('✓ צעד עם אזהרה אף פעם לא "הבא" — ממשיכים רק אחרי שהשרת אישר; כל הדרכה נגמרת באישור')
}

function testCoachCard(): void {
  const src = readSrc('help/ui/TourRunner.tsx')
  // "הבא" מוצג רק לצעד ידני — ולכן לעולם לא מעל צעד עם אזהרה (שתמיד api).
  assert(/advanceOn\.kind === 'manual' && target && \(/.test(src), 'כפתור "הבא" לא מוגבל לצעד ידני עם יעד גלוי')
  assert(/\{target && warningText && /.test(src), 'האזהרה מוצגת גם כשהיעד לא נמצא')
  assert(/\{target \? stepText/.test(src), 'שורת ההדרכה מוצגת גם כשהיעד לא נמצא')
  // "לא נמצא": בלי שורת הצעד, עם חזרה לעזרה.
  const notFound = src.slice(src.indexOf("phase.kind === 'notfound' && ("), src.indexOf("phase.kind === 'error' && ("))
  assert(notFound.length > 0, 'אין מצב "לא נמצא" בכרטיס')
  assert(!/stepText|warningText/.test(notFound), 'במצב "לא נמצא" עדיין מוצגת הוראה שמפנה לכפתור החסר')
  assert(/onBackToHelp/.test(notFound), 'במצב "לא נמצא" אין "חזרה לעזרה"')
  // נמצא בשלב 6: "עריכה" בשורת מוזמן שקוף עד hover. יעד שקוף לא נחשב גלוי,
  // ובזמן הדרכה כפתורי השורה נחשפים (help.css) — אחרת ההדרכה מצביעה על כלום.
  const tour = readSrc('help/ui/tour.ts')
  assert(/opacity\)\s*<\s*0\.1\) return false/.test(tour), 'isVisible לא בודק שקיפות — יעד שקוף ייחשב גלוי')
  assert(/TOUR_ATTR = 'data-help-tour'/.test(tour) && /setAttribute\(TOUR_ATTR/.test(src) && /removeAttribute\(TOUR_ATTR/.test(src), 'הסימון "הדרכה רצה" לא מוצב/מוסר')
  assert(/\[data-help-tour\] \.row-actions \{\s*opacity: 1;/.test(readSrc('help/ui/help.css')), 'בזמן הדרכה כפתורי השורה לא נחשפים')
  console.log('✓ כרטיס ההדרכה: הוראה ואזהרה רק כשהיעד גלוי; "לא נמצא" → חזרה לעזרה, בלי הוראה לכפתור החסר')
  console.log('✓ יעד שקוף לא נחשב גלוי; בזמן הדרכה כפתורי שורת המוזמן (hover) נחשפים')
}

testWarningsOnIrreversibleSteps()
testNoSendTourWithoutInvitationText()
testEveryIrreversibleStep()
testWarningStepsWaitForTheServer()
testCoachCard()
console.log('OK — ההדרכות מסמנות פעולות שקשה לבטל ולא ממשיכות בלי אישור מהשרת.')
