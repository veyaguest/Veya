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
 * ## תנועה מופחתת
 *
 * מי שביקש ``prefers-reduced-motion`` לא רואה הקלדה: המעטפות כבר
 * שמורות, והמסך נפתח על התוצאה. אותם רכיבים, בלי התנועה.
 */
import { useEffect, useRef, useState } from 'react'
import { FinancePage } from '../components/FinancePage'
import { DEMO_ENVELOPES, installDemoServer, seedAllEnvelopes } from './demoServer'
import './demo.css'

// מותקן ברגע הטעינה של המודול — לפני ש-``FinancePage`` מספיק לבקש נתונים.
installDemoServer()
// תנועה מופחתת: אין הקלדה, ולכן המעטפות כבר ספורות והמסך נפתח על התוצאה.
if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) seedAllEnvelopes()

/** קצב ההקלדה — מהיר מספיק כדי לא לשעמם, איטי מספיק כדי להיקרא. */
const CHAR_MS = 28
const DIGIT_MS = 78
const STEP_MS = 170

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

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
  const cursorRef = useRef<HTMLDivElement>(null)
  const [reduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  )

  useEffect(() => {
    if (reduced) return
    let alive = true

    /** מזיז את הסמן למרכז האלמנט, בקואורדינטות של הבמה. */
    async function moveTo(el: Element, settle = 260): Promise<void> {
      const stage = stageRef.current
      const cursor = cursorRef.current
      if (!stage || !cursor) return
      // בטלפון המסך ארוך מהמסגרת — מגלגלים לשדה שעליו עובדים עכשיו,
      // בדיוק כמו מי שסופר מעטפות בטלפון. במסך רחב זה לא זז בכלל.
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
      await sleep(180)
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
      await sleep(90)
      cursorRef.current?.classList.remove('is-press')
      el.click()
      await sleep(90)
    }

    async function type(el: HTMLInputElement, text: string, speed: number): Promise<void> {
      for (let i = 1; i <= text.length; i += 1) {
        if (!alive) return
        setValue(el, text.slice(0, i))
        await sleep(speed)
      }
    }

    async function run(): Promise<void> {
      // פותחים את מצב הספירה — בדיוק בלחיצה שהזוג לוחץ במוצר.
      const start = await waitFor<HTMLButtonElement>('.fin-counter-cta button')
      if (!alive || !start) return
      await moveTo(start)
      await press(start)

      for (const envelope of DEMO_ENVELOPES) {
        if (!alive) return
        const search = await waitFor<HTMLInputElement>('.fin-search')
        if (!alive || !search) return
        await moveTo(search)
        await press(search)
        search.focus()
        // מקלידים את השם המלא ולא קיצור: קיצור היה יכול להחזיר כמה
        // מוזמנים ("משפ…"), והלחיצה הייתה נופלת על השם הלא נכון.
        await type(search, envelope.name, CHAR_MS)
        await sleep(STEP_MS)

        // בחירת המוזמן מהתוצאות — לחיצה על השורה, כמו ביד.
        const result = await waitFor<HTMLButtonElement>('.fin-result')
        if (!alive || !result) return
        await moveTo(result, 220)
        await press(result)

        const amount = await waitFor<HTMLInputElement>('.fin-amount-input input')
        if (!alive || !amount) return
        await moveTo(amount)
        await press(amount)
        amount.focus()
        await type(amount, String(envelope.amount), DIGIT_MS)
        await sleep(STEP_MS)

        const save = await waitFor<HTMLButtonElement>('.fin-counter-actions button[type="submit"]')
        if (!alive || !save) return
        await moveTo(save, 220)
        await press(save)
        await sleep(380)
      }
      cursorRef.current?.classList.remove('is-on')
    }

    const stage = stageRef.current
    if (!stage) return
    // מתחילים רק כשההדגמה באמת על המסך.
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return
          io.disconnect()
          void run()
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
      <FinancePage />
      <div className="demo-cursor" ref={cursorRef} aria-hidden="true" />
    </div>
  )
}

