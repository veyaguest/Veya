/**
 * הדגמת ספירת המעטפות לדף הנחיתה.
 *
 * ## מה מוצג כאן
 *
 * ``FinancePage`` האמיתי, בלשונית ספירת המתנות: מסך הזנת המעטפות
 * (``EnvelopeCounter``) ומתחתיו יומן המתנות — שני הרכיבים של המוצר,
 * כמו שהם. הקובץ הזה לא מצייר מסך משלו ולא מעתיק שורה מהם.
 *
 * ## מה כן נוסף
 *
 * 1. שרת בזיכרון (``demoServer``) שעונה במקום ה-API.
 * 2. "אצבע" — סמן שנע על המסך, לוחץ בשדות ומקליד תו-תו, כמו אדם שיושב
 *    עם ערימת מעטפות. ההקלדה היא אמיתית: אותם אירועי ``input``/``click``
 *    שהדפדפן שולח, ולכן הרכיב האמיתי מגיב בדיוק כרגיל ובאמת שומר.
 *
 * ## ההדגמה לא נוגעת בדף שמסביב
 *
 * - **אין גלילה בכלל** — לא של הדף ולא פנימית. הבמה לא ניתנת לגלילה;
 *   כשצריך להראות חלק נמוך יותר, התוכן זז פנימה עם ``transform``.
 * - **אין focus** — אף שדה לא מקבל מיקוד אוטומטי, ולכן במובייל לא נפתחת
 *   מקלדת, גם לא כשחוזרים לדף.
 * - **קצב רגוע** — שלוש מעטפות מוקלדות לאט; השאר נספרות בשקט, והדוח
 *   בסוף מציג את כולן.
 * - **נעצרת מחוץ למסך** — כשההדגמה לא נראית, היא מחכה במקום.
 *
 * ## תנועה מופחתת
 *
 * מי שביקש ``prefers-reduced-motion`` לא רואה הקלדה: המעטפות כבר
 * שמורות, והמסך נפתח על התוצאה. אותם רכיבים, בלי התנועה.
 */
import { useEffect, useRef, useState } from 'react'
import { FinancePage } from '../components/FinancePage'
import {
  DEMO_ENVELOPES,
  installDemoServer,
  seedAllEnvelopes,
  seedRemainingEnvelopes,
} from './demoServer'
import './demo.css'

// ---- שכבת הדגמה: אין מיקוד אוטומטי בכלל ----
// ``EnvelopeCounter`` האמיתי ממקד שדות (``autoFocus`` ואחרי כל שמירה) —
// התנהגות נכונה במוצר. בהדגמה בתוך iframe זה פותח מקלדת במובייל ומחזיר
// אותה כשחוזרים לדף. במקום לשנות את הרכיב, ההדגמה מבטלת כאן את ``focus``
// הפרוגרמטי. מיקוד של המשתמש עצמו (לחיצה) לא עובר דרך הפונקציה הזו.
HTMLElement.prototype.focus = function noAutoFocus() {}

// מותקן ברגע הטעינה של המודול — לפני ש-``FinancePage`` מספיק לבקש נתונים.
installDemoServer()
// תנועה מופחתת: אין הקלדה, ולכן המעטפות כבר ספורות והמסך נפתח על התוצאה.
if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) seedAllEnvelopes()

/** כמה מעטפות מוקלדות בפועל. השאר נספרות בשקט לפני הדוח. */
const TYPED_ENVELOPES = 3
/** קצב ההקלדה — איטי מספיק כדי להבין מה קורה, בלי לחכות. */
const CHAR_MS = 70
const DIGIT_MS = 150
const STEP_MS = 480
const SETTLE_MS = 380
const PAN_MS = 700

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** מוריד מיקוד שנשאר (למשל אחרי חזרה ללשונית), כדי שלא תיפתח מקלדת. */
function dropFocus(): void {
  const el = document.activeElement as HTMLElement | null
  if (el && el !== document.body) el.blur()
}

/** ממתין שאלמנט יופיע ב-DOM (הרכיב האמיתי מרנדר בזמן שלו). */
async function waitFor<T extends Element>(selector: string, timeout = 6000): Promise<T | null> {
  const started = Date.now()
  for (;;) {
    const el = document.querySelector<T>(selector)
    if (el) return el
    if (Date.now() - started > timeout) return null
    await sleep(60)
  }
}

/**
 * כותב לשדה של React.
 *
 * הצבה ישירה ל-``value`` לא מפעילה את ה-setter ש-React עוקב אחריו,
 * והרכיב לא היה רואה את הטקסט. לכן קוראים ל-setter המקורי של
 * ``HTMLInputElement`` ואז משדרים ``input`` — בדיוק מה שהדפדפן עושה.
 */
function setValue(el: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(el, value)
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

export function DemoGiftCounting() {
  const stageRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)
  const [reduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  )

  useEffect(() => {
    dropFocus()
    window.addEventListener('pageshow', dropFocus)
    window.addEventListener('focus', dropFocus)
    document.addEventListener('visibilitychange', dropFocus)
    return () => {
      window.removeEventListener('pageshow', dropFocus)
      window.removeEventListener('focus', dropFocus)
      document.removeEventListener('visibilitychange', dropFocus)
    }
  }, [])

  useEffect(() => {
    if (reduced) return
    let alive = true
    let visible = false
    let offset = 0

    /** כשההדגמה לא על המסך — מחכים במקום, בלי להמשיך "לרוץ" מאחורי הגב. */
    async function whenVisible(): Promise<void> {
      while (alive && (!visible || document.hidden)) await sleep(250)
    }

    async function pause(ms: number): Promise<void> {
      await whenVisible()
      await sleep(ms)
    }

    /** מביא את האלמנט לתוך הבמה בהזזת התוכן — לא בגלילה. */
    async function bringIntoView(el: Element): Promise<void> {
      const stage = stageRef.current
      const track = trackRef.current
      if (!stage || !track) return
      const s = stage.getBoundingClientRect()
      const r = el.getBoundingClientRect()
      const pad = s.height * 0.18
      if (r.top >= s.top + pad && r.bottom <= s.bottom - pad) return
      const max = Math.max(0, track.offsetHeight - stage.clientHeight)
      const next = Math.max(0, Math.min(max, offset + (r.top + r.height / 2 - (s.top + s.height / 2))))
      if (Math.abs(next - offset) < 8) return
      offset = next
      track.style.transform = `translateY(${-offset}px)`
      await sleep(PAN_MS)
    }

    /** מזיז את הסמן למרכז האלמנט, בקואורדינטות של הבמה. */
    async function moveTo(el: Element, settle = SETTLE_MS): Promise<void> {
      const stage = stageRef.current
      const cursor = cursorRef.current
      if (!stage || !cursor) return
      await whenVisible()
      await bringIntoView(el)
      const s = stage.getBoundingClientRect()
      const r = el.getBoundingClientRect()
      cursor.style.transform = `translate(${r.left + r.width / 2 - s.left}px, ${
        r.top + r.height / 2 - s.top
      }px)`
      cursor.classList.add('is-on')
      await sleep(settle)
    }

    async function press(el: HTMLElement): Promise<void> {
      cursorRef.current?.classList.add('is-press')
      await sleep(140)
      cursorRef.current?.classList.remove('is-press')
      el.click()
      dropFocus()
      await sleep(160)
    }

    async function type(el: HTMLInputElement, text: string, speed: number): Promise<void> {
      for (let i = 1; i <= text.length; i += 1) {
        if (!alive) return
        await whenVisible()
        setValue(el, text.slice(0, i))
        await sleep(speed)
      }
    }

    async function run(): Promise<void> {
      await whenVisible()
      // פותחים את מצב הספירה — בדיוק בלחיצה שהזוג לוחץ במוצר.
      const start = await waitFor<HTMLButtonElement>('.fin-counter-cta button')
      if (!alive || !start) return
      await moveTo(start)
      await press(start)

      for (const envelope of DEMO_ENVELOPES.slice(0, TYPED_ENVELOPES)) {
        if (!alive) return
        const search = await waitFor<HTMLInputElement>('.fin-search')
        if (!alive || !search) return
        await moveTo(search)
        // מקלידים את השם המלא ולא קיצור: קיצור היה יכול להחזיר כמה
        // מוזמנים ("משפ…"), והלחיצה הייתה נופלת על השם הלא נכון.
        await type(search, envelope.name, CHAR_MS)
        await pause(STEP_MS)

        // בחירת המוזמן מהתוצאות — לחיצה על השורה, כמו ביד.
        const result = await waitFor<HTMLButtonElement>('.fin-result')
        if (!alive || !result) return
        await moveTo(result)
        await press(result)

        const amount = await waitFor<HTMLInputElement>('.fin-amount-input input')
        if (!alive || !amount) return
        await moveTo(amount)
        await type(amount, String(envelope.amount), DIGIT_MS)
        await pause(STEP_MS)

        const save = await waitFor<HTMLButtonElement>('.fin-counter-actions button[type="submit"]')
        if (!alive || !save) return
        await moveTo(save)
        await press(save)
        await pause(900)
      }
      cursorRef.current?.classList.remove('is-on')

      // שאר הערימה נספרת בשקט, והדוח מציג את כל המעטפות.
      seedRemainingEnvelopes()

      // ובסוף — הדוח האמיתי של המוצר. עוברים ללשונית הסיכום ולוחצים
      // "הצגת הדוח", בדיוק כמו הזוג אחרי האירוע. הטבלה שנפתחת היא
      // ``ReportTable`` של ``FinancePage``, עם העמודות שלה.
      await pause(700)
      const tabs = [].slice.call(document.querySelectorAll('.fin-tabs button')) as HTMLButtonElement[]
      const summaryTab = tabs[tabs.length - 1]
      if (summaryTab) {
        await moveTo(summaryTab, 500)
        await press(summaryTab)
      }
      const show = await waitFor<HTMLButtonElement>('.fin-section-head button, .fin-report button')
      if (show) {
        await moveTo(show, 500)
        await press(show)
      }
      const report = await waitFor<HTMLElement>('.fin-report-card')
      if (report) {
        await pause(400)
        await bringIntoView(report)
      }
      // נעצרים על הדוח.
      cursorRef.current?.classList.remove('is-on')
    }

    const stage = stageRef.current
    if (!stage) return
    let started = false
    // מתחילים כשההדגמה על המסך, ועוצרים כשהיא יוצאת ממנו.
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          visible = e.isIntersecting
          if (visible && !started) {
            started = true
            void run()
          }
        })
      },
      { threshold: 0.3 },
    )
    io.observe(stage)
    return () => {
      alive = false
      io.disconnect()
    }
  }, [reduced])

  return (
    <div className="demo-stage" ref={stageRef}>
      <div className="demo-track" ref={trackRef}>
        <FinancePage />
      </div>
      <div className="demo-cursor" ref={cursorRef} aria-hidden="true" />
    </div>
  )
}
