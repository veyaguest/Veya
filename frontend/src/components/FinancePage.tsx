import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
// מונוגרם VEYA הרשמי — data URI מוטבע בזמן build, כי חלון ההדפסה נפתח
// כ-``about:blank`` ולא פותר כתובת יחסית/מוחלטת כמו ``/logo_nobg.png``.
// ראו ``printReport``.
import { VEYA_MONOGRAM_DATA_URI as veyaMonogram } from '../assets/veyaMonogramBase64'
import {
  applyExpenseTemplate,
  createExpense,
  createPayment,
  deleteEnvelope,
  deleteExpense,
  updateEnvelope,
  getExpenseCategories,
  getFinance,
  getGiftCounting,
  getFinanceReport,
  getGiftsByGuest,
  getRsvpTimeline,
  setAttendance,
  setCountingDone,
  updateExpense,
  type GuestFilter,
} from '../api'
import type {
  Attendance,
  Commitment,
  Expense,
  ExpenseCategory,
  ExpenseCategoryTotal,
  EnvelopeInput,
  ExpenseInput,
  FinanceReport,
  FinanceSummary,
  GiftCounting,
  GiftEntry,
  GuestGiftRow,
  RsvpTimelineView,
} from '../types'
import { strings } from '../strings/he'
import { activeEventTerms } from '../strings/eventTypes'
import { EnvelopeCounter } from './EnvelopeCounter'
import { ExpenseEditor, type AfterSave, type Prepaid } from './ExpenseEditor'
import { GiftEditDialog } from './GiftEditDialog'
import { downloadWorkbook, type Cell } from '../lib/xlsx'
import './FinancePage.css'
import { useHelpScope } from '../help/useHelpScope'
import { announce } from '../lib/announce'

const t = strings.finance
const o = t.overview
const g = t.giftsView

/**
 * "מאזן האירוע" — המסך שעונה על ארבע שאלות, בסדר הזה: כמה האירוע עולה,
 * כמה נכנס, כמה נשאר — ומה עושים עכשיו.
 *
 * ## סקירה אחת במקום שלוש לשוניות (2026-09-29)
 *
 * עד היום המסך התפצל ל"עלות", "ספירת מתנות" ו"סיכום", ואף לשונית לא ענתה
 * לבד על "כמה יישאר לנו". עכשיו יש סקירה אחת, מהכללי לפרטני: הגיבור
 * (מאזן או עלות), אבני הדרך, מה נשאר לעשות, כסף שנכנס, כמה האירוע עולה,
 * ובסוף הפירוט המלא — מקופל. **שום נתון לא נמחק**: מה שהיה בלשונית
 * הסיכום יושב בפירוט, וספירת המעטפות היא מסך-עבודה משני (``?tab=counting``)
 * שנפתח מהסקירה.
 *
 * ## אין "הכנסה צפויה"
 *
 * VEYA לא יודעת כמה ייתנו, ולא מנחשת (החלטת בעלים 2026-09-29). לפני
 * ספירת המתנות הגיבור הוא העלות, ומשפט אחד אומר מתי יתברר המאזן; מהמתנה
 * הראשונה — המאזן עצמו.
 *
 * ## המסך לא מחשב כסף
 *
 * כל מספר כאן מגיע מוכן מהשרת (``total_display``, ``next_attendee_display``
 * וכו'). אותו כלל שכבר נאכף במתנות (``app/gift.py``): שני מקורות חישוב
 * לאותו מספר הם ההגדרה של באג שמתגלה מול חשבונית. מה שהמסך כן עושה הוא
 * **לבחור מה להציג** — מיון קבוצות לפי הסכום שהשרת חישב, וספירת שורות
 * בלי סכום. היוצא מן הכלל היחיד הוא ייצוא הדוח, שמעצב מספרים שכבר חושבו.
 *
 * ## Event-first
 *
 * "האירוע" הוא מונח משותף לכל שבעת הסוגים; מה שתלוי בסוג (תבנית
 * ההוצאות, כותרות הדוח) עובר דרך הלקסיקון (``activeEventTerms``). שם
 * העמוד (``t.navTitle``) קבוע: "מאזן האירוע" (החלטת בעלים 2026-09-15).
 */
type View = 'overview' | 'counting'

function viewFromUrl(): View {
  // ``cost``/``summary`` הישנים (לפני 2026-09-29) נופלים לסקירה.
  return new URLSearchParams(window.location.search).get('tab') === 'counting'
    ? 'counting'
    : 'overview'
}

/** לאן המסך יכול לשלוח — אותו ``goTo`` של ``App``. */
export type FinanceNavigate = (
  target: 'guests' | 'rsvp' | 'dashboard',
  options?: { guestFilter?: GuestFilter },
) => void

export function FinancePage({
  onNavigate,
  initialView,
}: {
  onNavigate?: FinanceNavigate
  /** ההדגמה בדף הנחיתה נפתחת ישר על ספירת המעטפות. */
  initialView?: View
}) {
  const terms = activeEventTerms()

  const [data, setData] = useState<FinanceSummary | null>(null)
  const [categories, setCategories] = useState<ExpenseCategory[]>([])
  const [counting, setCounting] = useState<GiftCounting | null>(null)
  const [byGuest, setByGuest] = useState<GuestGiftRow[] | null>(null)
  // מועד סגירת הרשימה — מיומן אישורי ההגעה. **תוספת ולא תנאי**: אם הקריאה
  // נכשלת, פשוט אין אבן דרך/משימה שנשענת עליו. המסך הכספי לא נופל בגללו.
  const [timeline, setTimeline] = useState<RsvpTimelineView | null>(null)

  // המסך נשמר בכתובת (?tab=counting) — כך רענון מחזיר לאותו מקום.
  const [view, setViewState] = useState<View>(() => initialView ?? viewFromUrl())
  const rootRef = useRef<HTMLDivElement>(null)
  /** מעבר מסך מתחיל מראשו — רק אם ראש המסך כבר גלול מעל הקצה, כדי לא
   *  להזיז דף שמטמיע את המסך (ההדגמה בדף הנחיתה). */
  const scrollToTop = useCallback(() => {
    const top = rootRef.current?.getBoundingClientRect().top ?? 0
    if (top < 0) rootRef.current?.scrollIntoView({ block: 'start' })
  }, [])

  /**
   * ## "חזור" של הטלפון מספירת המתנות חוזר לסקירה
   *
   * הכניסה לספירה מוסיפה רשומת היסטוריה משלה (``?tab=counting``), ולכן
   * "חזור" מחזיר לסקירה ולא יוצא מהמאזן. "חזרה למאזן" שבמסך עושה בדיוק
   * את אותו דבר (``history.back``) — כך אין רשומה יתומה שה"חזור" הבא ייתקע
   * עליה. מי שנכנס ישר לכתובת הספירה (רענון, קישור) אין לו רשומה כזו,
   * ואז הכתובת פשוט מתנקה במקום.
   *
   * לא ``useBackToClose``: הוא נועד לחלונות באותה כתובת, וכאן הכתובת
   * עצמה משתנה.
   */
  const setView = useCallback(
    (next: View) => {
      if (next === 'counting') {
        const url = new URL(window.location.href)
        url.searchParams.set('tab', 'counting')
        window.history.pushState(
          { ...(window.history.state ?? {}), veyaFinanceCounting: true },
          '',
          url.pathname + url.search,
        )
        setViewState('counting')
      } else if (window.history.state?.veyaFinanceCounting) {
        window.history.back() // ה-popstate למטה מחזיר לסקירה
        // רשת ביטחון: אחרי רענון הדף הסימון נשאר על הרשומה, אבל ה"חזור"
        // לא תמיד מגיע לסקירה. אם עדיין במסך המתנות — עוברים ישירות.
        window.setTimeout(() => {
          if (viewFromUrl() !== 'counting') return
          const url = new URL(window.location.href)
          url.searchParams.delete('tab')
          window.history.replaceState(null, '', url.pathname + url.search)
          setViewState('overview')
        }, 400)
      } else {
        const url = new URL(window.location.href)
        url.searchParams.delete('tab')
        window.history.replaceState(window.history.state, '', url.pathname + url.search)
        setViewState('overview')
      }
      scrollToTop()
    },
    [scrollToTop],
  )
  useEffect(() => {
    // ההדגמה בדף הנחיתה קובעת את המסך בעצמה ולא מאזינה לכתובת.
    if (initialView) return
    const onPop = () => {
      setViewState(viewFromUrl())
      scrollToTop()
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [initialView, scrollToTop])
  useHelpScope('finance')
  useHelpScope(view === 'counting' ? 'finance.counting' : 'finance.cost')
  useHelpScope(view === 'counting' ? null : 'finance.summary')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const [editing, setEditing] = useState<Expense | null | undefined>(undefined)
  // הקבוצה שממנה נלחץ "הוספה ל…" — הקטלוג נפתח עליה במקום על תשע קבוצות.
  const [addCategory, setAddCategory] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  // "מילוי ברצף" — נפתח מ"X הוצאות עדיין בלי סכום": הטופס עובר מהוצאה
  // להוצאה עד שכולן קיבלו סכום, בלי לחזור לרשימה ולחפש את הבאה.
  const [fillQueue, setFillQueue] = useState(false)
  // "שמירה והוספת עוד" — מונה שמרכיב מחדש טופס ריק (מפתח חדש).
  const [addNonce, setAddNonce] = useState(0)
  // אישור אחרי שמירה/מחיקה: שורה ראשית + פרט ("DJ · 4,500 ₪").
  const [toast, setToast] = useState<{ title: string; detail?: string } | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)
  const flashToast = useCallback((title: string, detail?: string) => {
    window.clearTimeout(toastTimer.current)
    setToast({ title, detail })
    // הטוסט נולד מלא, ולכן קורא מסך לא מכריז עליו לבד (lib/announce).
    announce(detail ? `${title}. ${detail}` : title)
    toastTimer.current = window.setTimeout(() => setToast(null), 4000)
  }, [])
  useEffect(() => () => window.clearTimeout(toastTimer.current), [])
  const [countingNow, setCountingNow] = useState(false)
  // עריכת מתנה (מעטפה) — חלון אחד: ממי? כמה? הערה, ומחיקה.
  const [editingGift, setEditingGift] = useState<GiftEntry | null>(null)
  const [giftBusy, setGiftBusy] = useState(false)
  const [giftError, setGiftError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  // "סיימנו לספור" / ביטול — פעולה אחת בכל רגע, ושגיאה שמוצגת ליד הכפתור.
  const [markingDone, setMarkingDone] = useState(false)
  const [markError, setMarkError] = useState<string | null>(null)
  // אחרי סימון/ביטול שמעבירים מסך — גוללים לראש המסך החדש, כדי ש"המאזן
  // הסופי" ייראה מיד. המעבר עצמו אסינכרוני (history.back ⇒ popstate), ולכן
  // הגלילה קורית ב-effect של ``view`` ולא מיד אחרי הקריאה.
  const scrollOnViewChange = useRef(false)
  useEffect(() => {
    if (!scrollOnViewChange.current) return
    scrollOnViewChange.current = false
    rootRef.current?.scrollIntoView({ block: 'start' })
  }, [view])

  // רשימת ההוצאות המלאה — סגורה כברירת מחדל (רואים את הקבוצות הגדולות),
  // ונפתחת מ"הצגת כל ההוצאות", ממשימה, או אחרי שמירה.
  const [showAllExpenses, setShowAllExpenses] = useState(false)
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set())
  const expensesRef = useRef<HTMLElement>(null)
  // הפירוט המלא — מקופל. נפתח בלחיצה, או מ"לדוח המלא" אחרי האירוע.
  const [detailsOpen, setDetailsOpen] = useState(false)

  // מסלול טעינה אחד בלבד, עם אותו ניקוי — בדיוק כמו ב-GiftsPage. כפתור
  // "ניסיון חוזר" מגדיל את המונה וה-effect רץ מחדש.
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    Promise.all([getFinance(), getExpenseCategories(), getGiftCounting()])
      .then(([summary, cats, count]) => {
        if (!alive) return
        setData(summary)
        setCategories(cats)
        setCounting(count)
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : t.loadError))
      .finally(() => alive && setLoading(false))
    getRsvpTimeline()
      .then((tl) => alive && setTimeline(tl))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [attempt])

  /**
   * **רק התשובה האחרונה נכנסת למסך.** שתי טעינות יכולות לרוץ במקביל — למשל
   * "סגירה" במונה בזמן שמעטפה עוד נשמרת — ותשובה ישנה שמגיעה אחרונה הייתה
   * דורסת את המספרים החדשים (נמצא בבדיקה: המעטפה נשמרה, והסכום במסך נשאר
   * ישן). כל טעינה מקבלת מספר, ורק האחרונה מעדכנת. גם כתיבה שמחזירה סיכום
   * (סיום ספירה, "כמה הגיעו") מקדמת את המונה, כדי שטעינה ישנה לא תדרוס אותה.
   */
  const loadSeq = useRef(0)
  const applySummary = useCallback((summary: FinanceSummary) => {
    loadSeq.current += 1
    setData(summary)
  }, [])
  const reload = useCallback(async (): Promise<FinanceSummary> => {
    const seq = ++loadSeq.current
    const [summary, count] = await Promise.all([getFinance(), getGiftCounting()])
    if (seq === loadSeq.current) {
      setData(summary)
      setCounting(count)
    }
    return summary
  }, [])

  /** רענון אחרי כל שינוי — מהשרת, כדי שהסיכום והשורות לא יסטו זה מזה. */
  const refresh = useCallback(() => {
    reload().catch(() => undefined)
    // "לפי מוזמן" נטען רק אם הוא כבר פתוח — אין טעם למשוך רשימה של 500
    // שורות שאיש לא מסתכל עליה.
    if (byGuest !== null) getGiftsByGuest().then(setByGuest).catch(() => undefined)
  }, [byGuest])

  /** פותח את רשימת ההוצאות המלאה (ואת הקבוצות שביקשו) וגולל אליה. */
  const openExpenses = useCallback((groups: string[] = []) => {
    setShowAllExpenses(true)
    setOpenGroups((prev) => new Set([...prev, ...groups]))
    requestAnimationFrame(() => expensesRef.current?.scrollIntoView({ block: 'start' }))
  }, [])

  /** פותח את הפירוט המלא וגולל לדוח. */
  const openReport = useCallback(() => {
    setDetailsOpen(true)
    requestAnimationFrame(() =>
      document.getElementById('fin-report')?.scrollIntoView({ block: 'start' }),
    )
  }, [])

  /**
   * "סיימנו לספור" או ביטולו. אחרי הסימון חוזרים לסקירה — שם מופיע "המאזן
   * הסופי", וזו התוצאה שהמשתמש רצה לראות. "המשך ספירה" מבטל ופותח את
   * מסך הספירה.
   */
  async function markCounting(done: boolean, then?: View): Promise<boolean> {
    setMarkingDone(true)
    setMarkError(null)
    try {
      applySummary(await setCountingDone(done))
      if (then) {
        scrollOnViewChange.current = true
        setView(then)
      }
      return true
    } catch (e) {
      setMarkError(e instanceof Error ? e.message : t.saveError)
      return false
    } finally {
      setMarkingDone(false)
    }
  }

  function applyTemplate() {
    setApplying(true)
    applyExpenseTemplate()
      .then(refresh)
      .catch(() => undefined)
      .finally(() => setApplying(false))
  }

  function startAdd(category?: string) {
    setAddCategory(category ?? null)
    setEditing(null)
  }

  /** ההוצאות שעדיין בלי סכום, לפי סדר הרשימה — התור של "מילוי ברצף". */
  function waitingIn(summary: FinanceSummary, exceptId?: number): Expense[] {
    return summary.expenses.filter((x) => x.total_agorot === 0 && x.id !== exceptId)
  }

  /** "X הוצאות עדיין בלי סכום" ⇒ ישר לטופס של הראשונה, לא לרשימה. */
  function startFillQueue() {
    const first = data ? waitingIn(data)[0] : undefined
    if (!first) return
    setAddCategory(null)
    setSaveError(null)
    setFillQueue(true)
    setEditing(first)
  }

  async function handleSaveExpense(
    input: ExpenseInput,
    prepaid: Prepaid | undefined,
    after: AfterSave,
  ) {
    setSaving(true)
    setSaveError(null)
    try {
      let saved: Expense
      if (editing) {
        saved = await updateExpense(editing.id, input)
      } else {
        saved = await createExpense(input)
        // "כבר שילמתם?" מהטופס — נרשם כתשלום ראשון, עם התאריך שנבחר. אי
        // אפשר לרשום תשלום על הוצאה שעוד לא נוצרה, ולכן זה קורה כאן.
        if (prepaid) saved = await createPayment(saved.id, prepaid)
      }
      // הסיכום נטען מחדש **לפני** שממשיכים — המאזן מתעדכן מיד, והתור
      // הבא נבנה מהנתונים האמיתיים ולא מהעותק הישן.
      const fresh = await reload()

      const detail = `${saved.label} · ${saved.total_display}`
      // סוף התור — האישור אומר שהמשימה כולה נגמרה, לא רק השורה הזו.
      const queueDone = fillQueue && waitingIn(fresh).length === 0
      flashToast(
        queueDone
          ? t.editor.allFilledToast
          : editing
            ? t.editor.savedToast
            : t.editor.addedToast,
        detail,
      )

      if (after === 'another') {
        // טופס ריק, באותו חלון — בלי לסגור ולפתוח מחדש.
        setAddNonce((n) => n + 1)
        setEditing(null)
        return
      }
      if (after === 'next') {
        const next = waitingIn(fresh, saved.id)[0]
        if (next) {
          setEditing(next)
          return
        }
      }
      setEditing(undefined)
      setAddCategory(null)
      setFillQueue(false)
      // הקבוצה של ההוצאה שנשמרה נפתחת, כדי שהשורה תיראה במקומה.
      setShowAllExpenses(true)
      setOpenGroups((prev) => new Set(prev).add(saved.category))
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteExpense() {
    if (!editing) return
    setSaving(true)
    try {
      await deleteExpense(editing.id)
      setEditing(undefined)
      setFillQueue(false)
      refresh()
      flashToast(t.editor.deletedToast, editing.label)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setSaving(false)
    }
  }

  /**
   * אחרי עריכה או מחיקה של מתנה: נטען מחדש, ואם זה החזיר את המאזן מ"הספירה
   * הסתיימה" ל"עד עכשיו" (תיקון סכום או מחיקה — בשרת), אומרים את זה במילים.
   */
  async function afterGiftChange(title: string, detail: string) {
    const wasDone = data?.counting_done ?? false
    const fresh = await reload()
    if (byGuest !== null) getGiftsByGuest().then(setByGuest).catch(() => undefined)
    flashToast(title, wasDone && !fresh.counting_done ? g.changedBody : detail)
  }

  async function handleSaveGift(input: EnvelopeInput) {
    if (!editingGift) return
    setGiftBusy(true)
    setGiftError(null)
    try {
      const saved = await updateEnvelope(editingGift.id, input)
      setEditingGift(null)
      await afterGiftChange(
        g.savedToast,
        `${saved.guest_name || g.unknownFrom} · ${saved.amount_display}`,
      )
    } catch (e) {
      setGiftError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setGiftBusy(false)
    }
  }

  async function handleDeleteGift() {
    if (!editingGift) return
    const gone = editingGift
    setGiftBusy(true)
    setGiftError(null)
    try {
      await deleteEnvelope(gone.id)
      setEditingGift(null)
      await afterGiftChange(
        g.deletedToast,
        `${gone.guest_name || g.unknownFrom} · ${gone.amount_display}`,
      )
    } catch (e) {
      setGiftError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setGiftBusy(false)
    }
  }

  if (loading) return <p className="load-text">{strings.common.loading}</p>
  if (error) {
    return (
      <div className="fin-page">
        <p className="form-error" role="alert">{error}</p>
        <div className="empty-actions">
          <button type="button" className="btn-ghost" onClick={() => setAttempt((n) => n + 1)}>
            {strings.common.retry}
          </button>
        </div>
      </div>
    )
  }
  if (!data || !counting) return null

  return (
    <div className="fin-page" ref={rootRef}>
      {view === 'counting' ? (
        <>
          <button type="button" className="btn-link fin-back" onClick={() => setView('overview')}>
            {o.back}
          </button>
          <GiftsView
            data={data}
            counting={counting}
            byGuest={byGuest}
            countingNow={countingNow}
            onStart={() => setCountingNow(true)}
            onStop={() => {
              setCountingNow(false)
              refresh()
            }}
            onSaved={refresh}
            onLoadByGuest={() => getGiftsByGuest().then(setByGuest).catch(() => setByGuest([]))}
            onEditEntry={(entry) => {
              setGiftError(null)
              setEditingGift(entry)
            }}
            marking={markingDone}
            markError={markError}
            // נשארים במסך המתנות: "הספירה הסתיימה ✓" מופיע כאן, והמאזן
            // הסופי במרחק לחיצה ("למאזן הסופי").
            onMarkDone={() =>
              markCounting(true).then((ok) => ok && flashToast(g.doneToast, g.doneToastDetail))
            }
            onUndoDone={() => markCounting(false)}
            onBackToBalance={() => setView('overview')}
          />
        </>
      ) : (
        <>
          <p className="fin-lede">{o.lede}</p>

          {/* 1–2. התשובה: מאזן (או עלות, כשעוד אין מתנות) — ולצידו מתנות מול הוצאות. */}
          <BalanceHero
            data={data}
            onManageGifts={() => setView('counting')}
          />

          {/* 3. איפה אנחנו בדרך. */}
          <Journey data={data} counting={counting} timeline={timeline} />

          {/* 4. הצעד הבא — רק מה שיש לו בסיס בנתונים. */}
          <NextSteps
            data={data}
            counting={counting}
            timeline={timeline}
            onOpenExpenses={openExpenses}
            onFillWaiting={startFillQueue}
            onOpenReport={openReport}
            onCount={() => setView('counting')}
            onAttendance={applySummary}
            onNavigate={onNavigate}
          />

          {/* 5. כסף שנכנס. */}
          <IncomeSection data={data} counting={counting} onCount={() => setView('counting')} />

          {/* 6. כמה האירוע עולה. */}
          <ExpensesSection
            sectionRef={expensesRef}
            data={data}
            celebration={terms.celebration}
            applying={applying}
            onApplyTemplate={applyTemplate}
            showAll={showAllExpenses}
            onShowAll={setShowAllExpenses}
            openGroups={openGroups}
            onOpenGroups={setOpenGroups}
            onOpenExpenses={openExpenses}
            onAdd={startAdd}
            onEdit={setEditing}
            onAttendance={applySummary}
            onNavigate={onNavigate}
          />

          {/* 7. הפירוט המלא — מקופל. */}
          <DetailsSection
            data={data}
            terms={terms}
            open={detailsOpen}
            onToggle={() => setDetailsOpen((v) => !v)}
          />
        </>
      )}

      {editing !== undefined && (
        <ExpenseEditor
          // מפתח לפי השורה: מעבר מ"הוספה" לשורה קיימת מתחיל טופס נקי.
          key={editing?.id ?? `new-${addNonce}`}
          existing={data.expenses}
          onOpenExisting={(e) => {
            setAddCategory(null)
            setFillQueue(false)
            setEditing(e)
          }}
          categories={categories}
          expense={editing}
          initialCategory={addCategory}
          // הכמויות שהמערכת כבר יודעת — הטופס מציג אותן ולא שואל עליהן.
          attendees={data.cost.attendees}
          invited={data.cost.invited}
          busy={saving}
          error={saveError}
          queueRemaining={
            fillQueue && editing ? waitingIn(data, editing.id).length : 0
          }
          onSave={handleSaveExpense}
          // יומן התשלומים משנה את השורה בשרת — הדיאלוג מחזיק את הגרסה
          // המעודכנת, והמסך שמאחור נטען מחדש כדי שהסיכומים לא יסטו.
          onPaymentsChanged={(updated) => {
            setEditing(updated)
            refresh()
          }}
          onDelete={editing ? handleDeleteExpense : undefined}
          onCancel={() => {
            setEditing(undefined)
            setAddCategory(null)
            setFillQueue(false)
            setSaveError(null)
          }}
        />
      )}

      {/* אישור אחרי שמירה — לא משאירים ספק אם זה נשמר. */}
      {toast && (
        <div className="toast fin-toast" aria-hidden="true">
          <span className="fin-toast-check" aria-hidden="true">✓</span>
          <span className="toast-text">
            {toast.title}
            {toast.detail && <span className="fin-toast-detail">{toast.detail}</span>}
          </span>
        </div>
      )}

      {editingGift && (
        <GiftEditDialog
          key={editingGift.id}
          entry={editingGift}
          busy={giftBusy}
          error={giftError}
          onSave={handleSaveGift}
          onDelete={handleDeleteGift}
          onClose={() => {
            setEditingGift(null)
            setGiftError(null)
          }}
        />
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  1–2. הגיבור — התשובה לשאלה "איפה אנחנו עומדים"
// ════════════════════════════════════════════════════════════════════════

/**
 * הכרטיס היחיד בראש המסך. **שלושה מצבים, לפי מה שבאמת ידוע:**
 *
 * 1. **אין עדיין לא הוצאות ולא מתנות** — משפט, לא קיר של אפסים.
 * 2. **יש הוצאות, אין עדיין מתנות** — המספר הגדול הוא העלות ("צפוי
 *    לעלות" עד שמוזן כמה הגיעו), ומשפט אחד אומר מתי יתברר המאזן. מאזן
 *    "חסר ₪63,850" כאן היה אפס בצד אחד של המשוואה, לא תחזית.
 * 3. **נספרו מתנות** — המאזן עצמו, ומתחתיו מתנות מול עלות.
 *
 * אם סכומי האשראי חסומים (``bottom_line_agorot === null``) לא מוצג מאזן
 * בכלל — מספר שמחושב מנתון חלקי הוא הטעיה, לא קירוב.
 */
function BalanceHero({
  data,
  onManageGifts,
}: {
  data: FinanceSummary
  /** "ניהול מתנות" — מעבר למסך המתנות. לא מבטל את הסימון: שינוי שם
   *  מחזיר את המאזן ל"עד עכשיו" מעצמו. */
  onManageGifts: () => void
}) {
  const [how, setHow] = useState(false)
  const { cost, attendance, rsvp, income } = data
  const final = attendance.is_final
  const locked = data.bottom_line_agorot === null
  const bottom = data.bottom_line_agorot ?? 0
  const hasCost = cost.total_agorot > 0
  const hasGifts = !locked && (income.total_agorot ?? 0) > 0
  // "המספר עוד ישתנה" — רק לפני האירוע, ורק כשבאמת יש מי שלא ענה.
  const pending = attendance.event_passed ? 0 : rsvp.pending_guests

  if (!hasCost && !hasGifts) {
    return (
      <section className="fin-balance" aria-labelledby="fin-balance-title">
        <p className="fin-balance-eyebrow">{o.earlyLabel}</p>
        <h2 id="fin-balance-title" className="fin-balance-early">
          {o.earlyTitle}
        </h2>
        <p className="fin-balance-note">{locked ? t.bottomLineLocked : o.earlyBody}</p>
      </section>
    )
  }

  if (hasGifts) {
    const tone = bottom > 0 ? 'is-positive' : bottom < 0 ? 'is-negative' : ''
    return (
      <section className="fin-balance" aria-labelledby="fin-balance-title">
        {/* "המאזן הסופי" רק כשהשרת אומר שסיימתם לספור ומאז לא נכנסה
            מתנה (``counting_done``) — אף פעם לא רק כי יש מתנות. */}
        <h2 id="fin-balance-title" className="fin-balance-eyebrow">
          {data.counting_done ? o.balanceFinalLabel : o.balanceLabel}
        </h2>
        {/* הסכום המוחלט: הסימן נאמר במילים שמתחת, ומינוס לצידו היה אומר
            את אותו דבר פעמיים. */}
        <p className={`fin-balance-value ${bottom < 0 ? 'is-negative' : ''}`}>
          {stripSign(data.bottom_line_display)}
        </p>
        <p className={`fin-balance-status ${tone}`}>
          {bottom > 0 ? o.balanceSurplus : bottom < 0 ? o.balanceDeficit : o.balanceEven}
        </p>
        <p className="fin-balance-note">
          {data.counting_done
            ? o.balanceFinalNote
            : data.counting_reopened
              ? o.reopenedNote
              : data.counting_open
                ? o.balanceBasis
                : o.balanceBasisEarly}
        </p>
        {data.counting_done && (
          <button
            type="button"
            className="btn-link fin-how-btn"
            onClick={onManageGifts}
          >
            {o.continueCounting}
          </button>
        )}

        <dl className="fin-balance-vs">
          <div>
            <dt>{o.vsGifts}</dt>
            <dd>{income.total_display}</dd>
          </div>
          <div>
            <dt>{final ? o.vsCostFinal : o.vsCostEstimated}</dt>
            <dd className={hasCost ? '' : 'is-empty'}>
              {hasCost ? cost.total_display : o.stepExpensesNone}
            </dd>
          </div>
        </dl>

        <HowWeCalc open={how} onToggle={() => setHow((v) => !v)}>
          <p>{o.howBalance}</p>
          <p>{final ? o.howCost : `${o.howCost} ${o.howCostAfter}`}</p>
          <p>{t.noFeeNote}</p>
        </HowWeCalc>
      </section>
    )
  }

  const basis = final
    ? o.costBasisActual(attendance.actual ?? 0)
    : cost.attendees > 0
      ? o.costBasisConfirmed(cost.attendees)
      : o.costBasisNobody

  return (
    <section className="fin-balance" aria-labelledby="fin-balance-title">
      <h2 id="fin-balance-title" className="fin-balance-eyebrow">
        {final ? o.costLabelFinal : o.costLabelEstimated}
      </h2>
      <p className="fin-balance-value">{cost.total_display}</p>
      <p className="fin-balance-status">{locked ? t.bottomLineLocked : o.balanceLater}</p>
      <p className="fin-balance-note">
        {basis}
        {!final && pending > 0 && ` ${o.pendingNote(pending)}`}
      </p>

      <HowWeCalc open={how} onToggle={() => setHow((v) => !v)}>
        <p>{o.howCost}</p>
        {!final && <p>{o.howCostAfter}</p>}
      </HowWeCalc>
    </section>
  )
}

/** "איך חישבנו?" — מי שלא שואל לא רואה את החישוב. */
function HowWeCalc({
  open,
  onToggle,
  children,
}: {
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className="fin-how">
      <button
        type="button"
        className="btn-link fin-how-btn"
        aria-expanded={open}
        aria-controls="fin-how-body"
        onClick={onToggle}
      >
        {open ? o.howClose : o.howToggle}
      </button>
      {open && (
        <div id="fin-how-body" className="fin-how-body">
          {children}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  3. אבני הדרך
// ════════════════════════════════════════════════════════════════════════

type StepState = 'done' | 'current' | 'upcoming'

interface JourneyStep {
  key: string
  title: string
  detail: string
  done: boolean
}

/** כמה ימים עד סגירת הרשימה — ``null`` כשאין מועד (או שהיומן לא נטען). */
function daysToClosing(timeline: RsvpTimelineView | null): number | null {
  if (!timeline?.commitment_date || timeline.days_to_commitment === null) return null
  return timeline.days_to_commitment
}

/** הוצאות שנפתחו (למשל מהתבנית) ועדיין בלי סכום. ספירה, לא חישוב כספי. */
function waitingExpenses(data: FinanceSummary): Expense[] {
  return data.expenses.filter((e) => e.total_agorot === 0)
}

/**
 * חמש תחנות, **כל אחת נגזרת מנתון קיים** — אין כאן תחנה שמסומנת "הושלמה"
 * בלי שהנתונים אומרים את זה. "מתנות" ו"מאזן סופי" מסומנים כהושלמו רק לפי
 * ``counting_done`` מהשרת ("סיימנו לספור", ומאז לא נכנסה מתנה).
 */
function journeySteps(
  data: FinanceSummary,
  counting: GiftCounting,
  timeline: RsvpTimelineView | null,
): JourneyStep[] {
  const { rsvp, attendance, cost, income } = data
  const closing = daysToClosing(timeline)
  const listClosed = attendance.event_passed || (closing !== null && closing < 0)
  const waiting = waitingExpenses(data).length
  const hasGifts = (income.total_agorot ?? 0) > 0

  let finalDetail: string
  let finalDone = false
  if (attendance.is_final) {
    finalDetail = o.stepFinalActual(attendance.actual ?? 0)
    finalDone = true
  } else if (attendance.event_passed) {
    finalDetail = o.stepFinalAskActual
  } else if (closing !== null && closing < 0) {
    finalDetail = o.stepFinalClosed(timeline!.commitment_date!)
    finalDone = true
  } else if (closing !== null) {
    finalDetail = o.stepFinalCloses(timeline!.commitment_date!)
  } else {
    // בלי יומן (לא נטען) לא טוענים שלא נבחר מועד — אומרים רק מה שידוע.
    finalDetail = timeline ? o.stepFinalNoDate : ''
  }

  let expensesDetail: string
  let expensesDone = false
  if (data.expenses.length === 0) expensesDetail = o.stepExpensesNone
  else if (cost.total_agorot === 0) expensesDetail = o.stepExpensesWaiting(waiting)
  else if (cost.unpaid_agorot === 0 && waiting === 0) {
    expensesDetail = o.stepExpensesPaid
    expensesDone = true
  } else expensesDetail = o.stepExpensesEntered(cost.total_display)

  return [
    {
      key: 'rsvp',
      title: o.stepRsvp,
      detail: rsvp.total_guests === 0 ? o.stepRsvpNone : o.stepRsvpConfirmed(rsvp.confirmed_people),
      done: rsvp.total_guests > 0 && (listClosed || rsvp.pending_guests === 0),
    },
    { key: 'final', title: o.stepFinal, detail: finalDetail, done: finalDone },
    { key: 'expenses', title: o.stepExpenses, detail: expensesDetail, done: expensesDone },
    {
      key: 'gifts',
      title: o.stepGifts,
      detail: data.counting_done
        ? o.stepGiftsDone
        : !counting.counting_open
          ? o.stepGiftsLater
          : hasGifts
            ? o.stepGiftsCounted(income.total_display)
            : o.stepGiftsOpen,
      // "הושלם" רק לפי הסימון שבשרת — לא כי יש מתנות.
      done: data.counting_done,
    },
    {
      key: 'balance',
      title: o.stepBalance,
      detail: data.counting_done
        ? o.stepBalanceDone
        : hasGifts
          ? o.stepBalanceLive
          : o.stepBalanceLater,
      done: data.counting_done,
    },
  ]
}

/**
 * התקדמות, לא צ'קליסט: ✓ מה שמאחוריכם, ● איפה אתם, ○ מה לפניכם. "איפה
 * אתם" היא התחנה הראשונה שעוד לא הושלמה — נקודה אחת, כדי שהעין תדע
 * לאן להסתכל.
 */
function Journey({
  data,
  counting,
  timeline,
}: {
  data: FinanceSummary
  counting: GiftCounting
  timeline: RsvpTimelineView | null
}) {
  const steps = journeySteps(data, counting, timeline)
  const currentIndex = steps.findIndex((s) => !s.done)

  return (
    <section className="fin-journey" aria-labelledby="fin-journey-title">
      <h2 id="fin-journey-title" className="fin-section-title">
        {o.journeyTitle}
      </h2>
      <ol className="fin-journey-list">
        {steps.map((s, i) => {
          const state: StepState = s.done ? 'done' : i === currentIndex ? 'current' : 'upcoming'
          return (
            <li
              key={s.key}
              className={`fin-mile is-${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="fin-mile-marker" aria-hidden="true" />
              <span className="fin-mile-text">
                <span className="fin-mile-title">
                  {s.title}
                  <span className="fin-sr"> · {o.stepState[state]}</span>
                </span>
                {s.detail && <span className="fin-mile-detail">{s.detail}</span>}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  4. מה נשאר לעשות?
// ════════════════════════════════════════════════════════════════════════

interface Todo {
  key: string
  title: string
  desc: string
  cta: string
  onClick: () => void
}

/** עד כמה ימים לפני הסגירה היא נחשבת "משימה" ולא סתם תאריך בלוח. */
const CLOSING_SOON_DAYS = 14

/**
 * הצעד הבא — **רק פריטים שיש להם בסיס בנתונים**, כל אחד עם הפעולה
 * שפותרת אותו. אותו עיקרון כמו "צריכים אתכם" בתמונת המצב: מה שתלוי
 * בבעלי האירוע, ולא מה שהמערכת עושה לבד.
 *
 * אחרי האירוע הצעד הראשון הוא "כמה הגיעו בפועל" — ולכן הטופס עצמו יושב
 * כאן, ולא מאחורי כפתור. אחרי השמירה הוא יורד לאזור העלות.
 */
function NextSteps({
  data,
  counting,
  timeline,
  onOpenExpenses,
  onFillWaiting,
  onOpenReport,
  onCount,
  onAttendance,
  onNavigate,
}: {
  data: FinanceSummary
  counting: GiftCounting
  timeline: RsvpTimelineView | null
  onOpenExpenses: (groups?: string[]) => void
  onFillWaiting: () => void
  onOpenReport: () => void
  onCount: () => void
  onAttendance: (data: FinanceSummary) => void
  onNavigate?: FinanceNavigate
}) {
  const { attendance, rsvp, income } = data
  const askAttendance = attendance.event_passed && !attendance.is_final
  const items: Todo[] = []

  // אחרי "סיימנו לספור" הספירה היא כבר לא משימה פתוחה. מתנה חדשה מחזירה
  // את המצב (``counting_done`` נהיה false) — והפריט חוזר מעצמו.
  if (counting.counting_open && !data.counting_done) {
    const hasGifts = income.envelopes_count + income.credit_count > 0
    items.push({
      key: 'count',
      title: hasGifts
        ? o.todoCountMore(income.total_display || income.envelopes_display)
        : o.todoCountStart,
      desc: hasGifts ? o.todoCountMoreDesc : o.todoCountDesc,
      cta: hasGifts ? o.todoCountMoreCta : o.todoCountCta,
      onClick: onCount,
    })
  }

  // אחרי האירוע, כשכבר נספרה מתנה — הדוח המלא הוא הצעד שסוגר את הסיפור.
  // בלי הפריט הזה הוא נשאר קבור בתוך הפירוט המקופל.
  if (attendance.event_passed && income.envelopes_count + income.credit_count > 0) {
    items.push({
      key: 'report',
      title: o.todoReport,
      desc: o.todoReportDesc,
      cta: o.todoReportCta,
      onClick: onOpenReport,
    })
  }

  if (!attendance.event_passed && rsvp.pending_guests > 0 && onNavigate) {
    items.push({
      key: 'pending',
      title: o.todoPending(rsvp.pending_guests),
      desc: o.todoPendingDesc,
      cta: o.todoPendingCta,
      onClick: () => onNavigate('guests', { guestFilter: 'pending' }),
    })
  }

  const waiting = waitingExpenses(data)
  if (data.expenses.length === 0) {
    items.push({
      key: 'expenses',
      title: o.todoNoExpenses,
      desc: o.todoNoExpensesDesc,
      // התבנית עצמה יושבת באזור ההוצאות — כאן רק מובילים אליה, כדי שלא
      // יהיו שני כפתורי "להתחיל מתבנית" באותו מסך.
      cta: t.summaryEmptyCta,
      onClick: () => onOpenExpenses(),
    })
  } else if (waiting.length > 0) {
    items.push({
      key: 'expenses',
      title: o.todoEmptyRows(waiting.length),
      desc: o.todoEmptyRowsDesc,
      cta: o.todoEmptyRowsCta,
      // ישר לטופס של הראשונה, ומשם לבאה — בלי לחפש שורות ברשימה.
      onClick: onFillWaiting,
    })
  }

  const closing = daysToClosing(timeline)
  if (!attendance.event_passed && onNavigate) {
    if (closing !== null && closing >= 0 && closing <= CLOSING_SOON_DAYS) {
      items.push({
        key: 'closing',
        title: o.todoClosing(closing),
        desc: o.todoClosingDesc,
        cta: o.todoClosingCta,
        onClick: () => onNavigate('rsvp'),
      })
    } else if (timeline?.track_phase === 'waiting') {
      items.push({
        key: 'closing',
        title: o.todoNoClosing,
        desc: o.todoNoClosingDesc,
        cta: o.todoNoClosingCta,
        onClick: () => onNavigate('dashboard'),
      })
    }
  }

  return (
    <section className="fin-section fin-todo" aria-labelledby="fin-todo-title">
      <h2 id="fin-todo-title" className="fin-section-title">
        {o.todoTitle}
      </h2>

      {askAttendance && (
        <AttendanceCard attendance={attendance} onSaved={onAttendance} onNavigate={onNavigate} />
      )}

      {items.length > 0 ? (
        <ul className="fin-card fin-todo-list">
          {items.map((it, i) => (
            <li key={it.key} className="fin-todo-item">
              <div className="fin-todo-text">
                <p className="fin-todo-title">{it.title}</p>
                <p className="fin-todo-desc">{it.desc}</p>
              </div>
              <button
                type="button"
                // פעולה ראשית אחת — הראשונה ברשימה, אלא אם הטופס שמעל הוא הצעד.
                className={`${i === 0 && !askAttendance ? 'btn-primary' : 'btn-ghost'} btn-sm fin-todo-btn`}
                onClick={it.onClick}
              >
                {it.cta}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        !askAttendance && <p className="fin-todo-empty">{o.todoEmpty}</p>
      )}
    </section>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  5. מתנות — התוצאה
// ════════════════════════════════════════════════════════════════════════

/**
 * המתנות — **כתוצאה, לא כמקום ניהול.** לפני יום האירוע: מתי והיכן, בלי
 * "0 ₪". מיום האירוע: "מתנות שנספרו" ו"ניהול מתנות" — הפירוט, הרשימה
 * וסטטוסי האשראי יושבים במסך המתנות. אין "הכנסה צפויה".
 */
function IncomeSection({
  data,
  counting,
  onCount,
}: {
  data: FinanceSummary
  counting: GiftCounting
  onCount: () => void
}) {
  const { income } = data

  if (!counting.counting_open) {
    const days = counting.days_until_open
    return (
      <section className="fin-section" aria-labelledby="fin-income-title">
        <h2 id="fin-income-title" className="fin-section-title">
          {o.incomeTitle}
        </h2>
        <div className="fin-quiet">
          <p className="fin-quiet-title">{o.incomeBeforeTitle}</p>
          <p className="fin-hint">
            {days !== null && days > 0 && `${o.incomeBeforeDays(days)} `}
            {o.incomeBeforeBody}
          </p>
          {/* מתנה באשראי יכולה להגיע גם לפני האירוע. */}
          {income.credit_count > 0 && (
            <dl className="fin-kv">
              <div>
                <dt>{o.incomeCreditEarly}</dt>
                <dd>{income.credit_display || String(income.credit_count)}</dd>
              </div>
            </dl>
          )}
        </div>
      </section>
    )
  }

  const hasGifts = income.envelopes_count + income.credit_count > 0

  // המאזן מציג את **התוצאה** ומוביל לניהול — הפירוט (מעטפות/אשראי),
  // הרשימה, ההתקדמות וסטטוסי האשראי יושבים במסך המתנות (2026-09-30).
  return (
    <section className="fin-section" aria-labelledby="fin-income-title">
      <h2 id="fin-income-title" className="fin-section-title">
        {o.incomeTitle}
      </h2>
      <div className="fin-gifts-result">
        <div className="fin-amount">
          <span className="fin-amount-label">{g.totalLabel}</span>
          <span className={hasGifts ? 'fin-amount-value' : 'fin-quiet-title'}>
            {hasGifts ? income.total_display || income.envelopes_display : g.noneYet}
          </span>
          {data.counting_done && <span className="fin-hint">{g.doneTitle}</span>}
          {income.total_agorot === null && hasGifts && (
            <span className="fin-hint">{t.totalPartialNote}</span>
          )}
        </div>
        <button type="button" className="btn-ghost" onClick={onCount}>
          {g.manage}
        </button>
      </div>
    </section>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  6. כמה האירוע עולה
// ════════════════════════════════════════════════════════════════════════

/** כמה קבוצות מוצגות לפני "הצגת כל ההוצאות". */
const TOP_GROUPS = 5

/**
 * **סכום קודם, פירוט אחר כך.** ברירת המחדל היא הסכום, כמה שולם, וחמש
 * הקבוצות הגדולות — שורה אחת לכל אחת. הרשימה המלאה (קבוצות מקופלות,
 * עריכת שורות) נפתחת ב"הצגת כל ההוצאות", מלחיצה על קבוצה, או ממשימה.
 *
 * הסכום של כל קבוצה מגיע **מהשרת** (``cost.categories``); המסך רק ממיין.
 */
function ExpensesSection({
  sectionRef,
  data,
  celebration,
  applying,
  onApplyTemplate,
  showAll,
  onShowAll,
  openGroups,
  onOpenGroups,
  onOpenExpenses,
  onAdd,
  onEdit,
  onAttendance,
  onNavigate,
}: {
  sectionRef: React.RefObject<HTMLElement | null>
  data: FinanceSummary
  celebration: string
  applying: boolean
  onApplyTemplate: () => void
  showAll: boolean
  onShowAll: (v: boolean) => void
  openGroups: Set<string>
  onOpenGroups: (groups: Set<string>) => void
  onOpenExpenses: (groups?: string[]) => void
  onAdd: (category?: string) => void
  onEdit: (e: Expense) => void
  onAttendance: (data: FinanceSummary) => void
  onNavigate?: FinanceNavigate
}) {
  const { cost, attendance } = data
  const grouped = useMemo(() => groupByCategory(data.expenses), [data.expenses])
  const top = useMemo(
    () =>
      cost.categories
        .filter((c) => c.total_agorot > 0)
        .sort((a, b) => b.total_agorot - a.total_agorot)
        .slice(0, TOP_GROUPS),
    [cost.categories],
  )
  const allOpen = cost.categories.length > 0 && openGroups.size >= cost.categories.length
  const hasCost = cost.total_agorot > 0

  function toggle(key: string) {
    const next = new Set(openGroups)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onOpenGroups(next)
  }

  return (
    <section
      ref={sectionRef}
      className="fin-section fin-cost"
      aria-labelledby="fin-cost-title"
    >
      <div className="fin-section-head">
        <h2 id="fin-cost-title" className="fin-section-title">
          {o.costTitle}
        </h2>
        {/* כשאין עדיין הוצאות, המסך הריק למטה כבר מציע גם "הוספת הוצאה" —
            שני כפתורים זהים זה מעל זה מבלבלים מה הצעד הראשון. */}
        {data.expenses.length > 0 && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => onAdd()}>
            {o.addExpense}
          </button>
        )}
      </div>

      {data.expenses.length === 0 ? (
        // מסך ריק שמבקש להמציא רשימת הוצאות של אירוע הוא מסך שנשאר ריק.
        // התבנית של סוג האירוע נותנת נקודת פתיחה — בסכום 0, כי VEYA יודעת
        // **מה** משלמים ולא **כמה**.
        <div className="fin-quiet">
          <p className="fin-quiet-title">{t.expensesEmptyTitle}</p>
          <p className="fin-hint">{t.expensesEmptyBody}</p>
          <div className="empty-actions fin-quiet-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={applying}
              onClick={onApplyTemplate}
            >
              {applying ? t.templateApplying : t.templateCta(celebration)}
            </button>
            <button type="button" className="btn-ghost" onClick={() => onAdd()}>
              {t.addExpense}
            </button>
          </div>
          <p className="fin-hint">{t.templateHint}</p>
        </div>
      ) : (
        <>
          {hasCost ? (
            <div className="fin-amount">
              <span className="fin-amount-label">
                {attendance.is_final ? t.totalCostLabel : t.estimatedCostLabel}
              </span>
              <span className="fin-amount-value">{cost.total_display}</span>
            </div>
          ) : (
            <p className="fin-hint">{o.costWaiting}</p>
          )}

          {/* שולם / נשאר לשלם — זוג מספרים אחד. הפס הוא היחס ביניהם ותו
              לא: הוא לא מוסיף מידע, הוא חוסך את החישוב בראש. */}
          {hasCost && (
            <div className="fin-paybar">
              <div className="fin-paybar-track" aria-hidden="true">
                <div
                  className="fin-paybar-fill"
                  style={{ width: `${Math.min(100, (cost.paid_agorot / cost.total_agorot) * 100)}%` }}
                />
              </div>
              <div className="fin-paybar-legend">
                <span className="fin-paybar-paid">
                  <span className="fin-paybar-label">{t.paidSummary}</span>
                  <strong>{cost.paid_display}</strong>
                </span>
                <span className="fin-paybar-left">
                  <span className="fin-paybar-label">{t.unpaidSummary}</span>
                  <strong>{cost.unpaid_display}</strong>
                </span>
              </div>
            </div>
          )}

          {/* מה מספר המגיעים אומר על העלות — לפני האירוע בלבד, ובקטן.
              הממוצע הוא ממוצע; מה שאדם נוסף מוסיף מגיע מ-``next_attendee``
              (ההפרש המדויק), ולא נגזר מהממוצע — הם שני מספרים שונים. */}
          {hasCost && !attendance.event_passed && cost.cost_per_attendee_agorot !== null && (
            <PerPerson cost={cost} />
          )}

          {showAll ? (
            <div className="fin-card fin-groups">
              {cost.categories.map((group) => (
                <ExpenseGroup
                  key={group.key}
                  group={group}
                  rows={grouped.get(group.key) ?? []}
                  open={openGroups.has(group.key)}
                  onToggle={() => toggle(group.key)}
                  onEdit={onEdit}
                  onAdd={() => onAdd(group.key)}
                />
              ))}
            </div>
          ) : (
            top.length > 0 && (
              <ul className="fin-top">
                {top.map((g) => (
                  <li key={g.key}>
                    <button
                      type="button"
                      className="fin-top-row"
                      onClick={() => onOpenExpenses([g.key])}
                    >
                      <span className="fin-top-name">{g.label}</span>
                      <span className="fin-top-total">{g.total_display}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )
          )}

          <div className="fin-cost-actions">
            <button type="button" className="btn-link" onClick={() => onShowAll(!showAll)}>
              {showAll ? o.hideAllExpenses : o.showAllExpenses(data.expenses.length)}
            </button>
            {showAll && cost.categories.length > 1 && (
              <button
                type="button"
                className="btn-link"
                onClick={() =>
                  onOpenGroups(allOpen ? new Set() : new Set(cost.categories.map((c) => c.key)))
                }
              >
                {allOpen ? t.collapseAll : t.expandAll}
              </button>
            )}
          </div>

          {/* ההתחייבות מול הספק — במשפט אחד כאן; המספרים המלאים בפירוט. */}
          {cost.commitments.map((c) => (
            <p key={c.expense_id} className="fin-hint fin-commit-line">
              <strong>{c.label}:</strong>{' '}
              {c.unused_quantity > 0
                ? t.underCommitment(c.committed_quantity, c.attendees)
                : c.over_commitment > 0
                  ? t.overCommitment(c.attendees, c.over_commitment)
                  : t.exactCommitment}
            </p>
          ))}
        </>
      )}

      {/* אחרי האירוע, כשכבר הוזן כמה הגיעו — המספר שהעלות נשענת עליו, עם
          אפשרות לשנות. בסוף האזור ולא בראשו: הסכום קודם. לפני שהוזן, הטופס
          נמצא ב"מה נשאר לעשות". */}
      {attendance.event_passed && attendance.is_final && (
        <AttendanceCard attendance={attendance} onSaved={onAttendance} onNavigate={onNavigate} />
      )}
    </section>
  )
}

/**
 * קבוצת הוצאות אחת — **סכום קודם, פירוט אחר כך.**
 *
 * הכותרת עונה על השאלה הנפוצה ("כמה יוצא לנו על מוזיקה?") בלי לפתוח
 * כלום, ומי שרוצה לדעת ממה הסכום מורכב לוחץ. זה ההבדל בין מסך שסורקים
 * לבין מסך שקוראים.
 *
 * הסכום מגיע **מהשרת** (``cost.categories``) ולא מחיבור השורות כאן:
 * שורת אחוז נגזרת משאר ההוצאות, וחיבור שלה בדפדפן היה חישוב כספי שני
 * שיכול לסטות מהסיכום שמעליו.
 */
function ExpenseGroup({
  group,
  rows,
  open,
  onToggle,
  onEdit,
  onAdd,
}: {
  group: ExpenseCategoryTotal
  rows: Expense[]
  open: boolean
  onToggle: () => void
  onEdit: (e: Expense) => void
  /** הוספה **בתוך הקבוצה הזו** — הקטלוג ייפתח עליה בלבד. */
  onAdd: () => void
}) {
  const panelId = `fin-group-${group.key}`

  return (
    <section className={`fin-group ${open ? 'open' : ''}`}>
      <h3 className="fin-group-head">
        <button
          type="button"
          className="fin-group-btn"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
        >
          <span className="fin-group-chevron" aria-hidden="true" />
          <span className="fin-group-name">
            {group.label}
            <span className="fin-group-meta">
              {t.groupCount(group.expense_count)}
              {/* יש בקבוצה סכום, ולצידו שורה שעדיין בלי — סימון שקט ולא
                  אזהרה: זה מצב תקין בתחילת התכנון. כשכל הקבוצה ריקה
                  התג מיותר, כי המילים כבר יושבות במקום הסכום. */}
              {group.has_empty && group.total_agorot > 0 && (
                <span className="fin-badge fin-badge-empty">{t.groupEmptyBadge}</span>
              )}
            </span>
          </span>
          {/* קבוצה שכולה עדיין בלי סכומים: "0 ₪" נקרא כמו הצהרה שהסעיף
              הזה לא עולה כלום. אמירה במילים נכונה יותר וגם שקטה יותר. */}
          <span className={`fin-group-total ${group.total_agorot ? '' : 'is-empty'}`}>
            {group.total_agorot ? group.total_display : t.groupEmptyBadge}
          </span>
        </button>
      </h3>

      {open && (
        <div id={panelId} className="fin-group-body">
          <ul className="fin-expense-list">
            {rows.map((e) => (
              <ExpenseRow key={e.id} expense={e} onEdit={() => onEdit(e)} />
            ))}
          </ul>
          <button type="button" className="btn-link fin-group-add" onClick={onAdd}>
            {t.addToGroup(group.label)}
          </button>
        </div>
      )}
    </section>
  )
}

/**
 * ההתחייבות מול הספק — האזור החשוב ביותר במסך לפני האירוע.
 *
 * שלושה מספרים זה מול זה, כי זו בדיוק השאלה שהזוג שואל בשבועיים
 * האחרונים: על כמה התחייבנו, כמה מגיעים, ועל כמה אנחנו משלמים.
 * המשפט מתחת אומר את זה במילים, בלי סימן קריאה ובלי "שימו לב" — זו
 * עובדה חשבונאית, לא אזהרה.
 */
/**
 * "כמה אורחים הגיעו בפועל?" — הצעד שהופך עלות משוערת לעלות סופית.
 *
 * ## מספר אחד, לא סימון אדם-אדם
 *
 * אף זוג לא יעבור על 600 שורות ביום שאחרי החתונה. גם האולם לא מחייב
 * לפי רשימה — הוא סופר צלחות. מספר כולל הוא בדיוק הרזולוציה הנכונה.
 *
 * ## מה זה משנה
 *
 * מרגע שהוזן, הוא מחליף את מספר המגיעים מאישורי ההגעה **בכל החישוב**.
 * הנוסחה עצמה לא זזה: ``MAX(MAX(מגיעים, התחייבות) × מחיר, מינימום)``
 * נשארת, ורק מה שנכנס כ"מגיעים" משתנה. תמיד אפשר לנקות ולחזור.
 *
 * ## ומה זה **לא** משנה
 *
 * אישורי הגעה. מספר כולל אינו יודע מי מבין המאשרים לא הגיע, וניחוש כאן
 * היה דורס נתון שהמוזמן מסר בעצמו. במקום זה — המלצה, עם דלת יציאה.
 */
function AttendanceCard({
  attendance,
  onSaved,
  onNavigate,
}: {
  attendance: Attendance
  onSaved: (data: FinanceSummary) => void
  onNavigate?: (target: 'guests') => void
}) {
  const [value, setValue] = useState(
    attendance.actual != null ? String(attendance.actual) : '',
  )
  const [editing, setEditing] = useState(!attendance.is_final)
  // מיקוד רק אחרי "שינוי" — לא בטעינה. הטופס יושב בסקירה, ומיקוד אוטומטי
  // היה גולל את המסך אל מתחת למאזן ופותח מקלדת בטלפון.
  const [focusInput, setFocusInput] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState(false)

  async function save(next: number | null) {
    setBusy(true)
    setError(null)
    try {
      onSaved(await setAttendance(next))
      setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <section className="fin-card fin-attendance">
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (value.trim() === '') return
              save(parseInt(value, 10))
            }}
          >
            <h2 className="fin-card-title">{t.attendanceTitle}</h2>
            <p className="fin-hint">{t.attendanceBody}</p>
            <div className="fin-attendance-row">
              <label className="field">
                <span className="field-label">{t.attendanceLabel}</span>
                {/* גדול בכוונה: זה המספר היחיד שמוקלד כאן, והוא זה
                    שהופך את כל המסך מ"משוער" ל"סופי". */}
                <input
                  type="text"
                  inputMode="numeric"
                  className="fin-attendance-input"
                  value={value}
                  onChange={(e) => setValue(e.target.value.replace(/[^\d]/g, ''))}
                  placeholder={String(attendance.confirmed_people)}
                  dir="ltr"
                  autoFocus={focusInput}
                />
              </label>
              <button
                type="submit"
                className="btn-primary"
                disabled={busy || value.trim() === ''}
              >
                {busy ? strings.common.saving : t.attendanceSave}
              </button>
            </div>
            <p className="fin-hint">
              {t.attendanceConfirmedNote(attendance.confirmed_people)}
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </form>
        ) : (
          <div className="fin-attendance-done">
            <span className="fin-attendance-value">
              {t.attendanceFinal(attendance.actual ?? 0)}
            </span>
            <span className="fin-hint">
              {attendance.no_show
                ? t.attendanceNoShow(attendance.no_show)
                : attendance.extra
                  ? t.attendanceExtra(attendance.extra)
                  : t.attendanceConfirmedNote(attendance.confirmed_people)}
            </span>
            <span className="fin-attendance-actions">
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setFocusInput(true)
                  setEditing(true)
                }}
              >
                {t.attendanceEdit}
              </button>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setValue('')
                  save(null)
                }}
                disabled={busy}
              >
                {t.attendanceClear}
              </button>
            </span>
          </div>
        )}
      </section>

      {/* §10 — המלצה, לא חסימה ולא פעולה. מוצגת רק כשיש פער אמיתי, ורק
          עד שהזוג סוגר אותה. VEYA לא נוגעת באישורי ההגעה בעצמה. */}
      {attendance.is_final && !!attendance.no_show && !dismissed && (
        <section className="fin-card fin-reconcile">
          <h2 className="fin-card-title">{t.reconcileTitle}</h2>
          <p>{t.reconcileBody(attendance.no_show)}</p>
          <div className="fin-reconcile-actions">
            {onNavigate && (
              <button
                type="button"
                className="btn-primary btn-sm"
                onClick={() => onNavigate('guests')}
              >
                {t.reconcileYes}
              </button>
            )}
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={() => setDismissed(true)}
            >
              {t.reconcileNo}
            </button>
          </div>
        </section>
      )}
    </>
  )
}

/**
 * ההתחייבות מול הספק — בפירוט המלא. בסקירה היא משפט אחד (באזור העלות);
 * כאן — המספרים שמאחוריו, בשורות ולא ברשת תאים.
 */
function CommitmentDetail({
  commitment: c,
  attendance,
}: {
  commitment: Commitment
  attendance: Attendance
}) {
  // שלושה מספרים ולא חמישה. "משלמים על" ו"לא ינוצלו" נגזרים שניהם מאותם
  // שני נתונים, והמשפט שמתחת אומר אותם במילים.
  const rows: [string, string][] = [
    [t.committedLabel, String(c.committed_quantity)],
    [t.attendingNowLabel, String(c.attendees)],
  ]
  // רזרבה — ליד ההתחייבות כי זו אותה שיחה מול הספק, אבל **לא נספרת בעלות**.
  if (c.reserve_quantity) rows.push([t.reserveFact, String(c.reserve_quantity)])
  rows.push([attendance.is_final ? t.commitmentCostLabel : t.estimatedCostLabel, c.total_display])

  return (
    <div className="fin-detail">
      <h3 className="fin-subtitle">
        {t.commitmentTitle} · {c.label}
      </h3>
      <KeyValues rows={rows} />
      <p className="fin-commitment-note">
        {c.unused_quantity > 0
          ? t.underCommitment(c.committed_quantity, c.attendees)
          : c.over_commitment > 0
            ? t.overCommitment(c.attendees, c.over_commitment)
            : t.exactCommitment}
      </p>
      {!!c.reserve_quantity && <p className="fin-hint">{t.reserveNote(c.reserve_quantity)}</p>}
      {c.min_total_applied && <p className="fin-hint">{t.minTotalApplied}</p>}
    </div>
  )
}

/**
 * "כמה מוסיף כל אדם נוסף?"
 *
 * המספר מגיע מהשרת כהפרש בין שני מצבים, ולכן הוא נכון בשתי המדרגות:
 * ₪0 כשעדיין מתחת לכמות ההתחייבות (כבר משלמים על האדם הזה), ומחיר מלא
 * מעליה. זו הנקודה שבה המסך הזה שווה משהו — מחשבון שמכפיל במחיר מנה
 * היה נותן כאן תשובה שגויה.
 */
function NextPersonCard({ cost }: { cost: FinanceSummary['cost'] }) {
  const free = cost.next_attendee_agorot === 0
  const commitment = cost.commitments[0]

  return (
    <div className="fin-next">
      <h3 className="fin-subtitle">{t.nextPersonTitle}</h3>

      {free && commitment ? (
        <>
          <p className="fin-next-value">{t.nextPersonFreeTitle}</p>
          <p className="fin-hint">
            {t.nextPersonFreeBody(commitment.committed_quantity, commitment.label)}
          </p>
        </>
      ) : (
        <>
          <p className="fin-next-value">{cost.next_attendee_display}</p>
          {/* המספר לבדו לא מספיק כשיש התחייבות ברקע: "35 ₪" נראה כמו
              טעות למי שיודע שמנה עולה 320. המשפט הזה אומר למה. */}
          {commitment && commitment.unused_quantity > 0 && (
            <p className="fin-hint">
              {t.nextPersonPartialBody(commitment.committed_quantity, commitment.label)}
            </p>
          )}
          {commitment && commitment.over_commitment > 0 && (
            <p className="fin-hint">
              {t.nextPersonOverBody(commitment.committed_quantity)}
            </p>
          )}
        </>
      )}

      <p className="fin-next-intro">{t.stepsIntro}</p>
      <ul className="fin-steps">
        {cost.steps.map((s) => (
          <li key={s.guests}>
            <span className="fin-step-label">{t.stepLabel(s.guests)}</span>
            <span className="fin-step-value">{s.added_display}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ExpenseRow({ expense, onEdit }: { expense: Expense; onEdit: () => void }) {
  return (
    <li className="fin-expense">
      <button type="button" className="fin-expense-btn" onClick={onEdit}>
        <span className="fin-expense-name">
          {expense.label}
          {/* הספק, ואחריו שני המצבים. "שולם" בירוק כי זו בשורה טובה;
              "הערכה" באפור כי זו עובדה ניטרלית ולא חוסר. */}
          {expense.vendor && <span className="fin-expense-note">{expense.vendor}</span>}
          {/* מצב התשלום נגזר מהיומן, לא מדגל: שולם הכול ⇒ "שולם";
              שולם חלק ⇒ כמה **נשאר**, כי זו השאלה. הסכום בתוך התג —
              "שולם חלקית" לבדו שולח את הזוג לפתוח את השורה. */}
          {expense.paid_agorot > 0 && expense.remaining_agorot === 0 && (
            <span className="fin-badge fin-badge-paid">{t.paidLabel}</span>
          )}
          {expense.paid_agorot > 0 && expense.remaining_agorot > 0 && (
            <span className="fin-badge fin-badge-partial">
              {t.remainingBadge(expense.remaining_display)}
            </span>
          )}
          {/* "הערכה" על שורה בלי סכום היא תג על כלום. */}
          {expense.is_estimated && expense.total_agorot > 0 && (
            <span className="fin-badge">{t.estimatedLabel}</span>
          )}
          {expense.note && <span className="fin-expense-note">{expense.note}</span>}
        </span>
        <span className="fin-expense-calc">{describeCalc(expense)}</span>
        {/* שורה שנפתחה מהתבנית ועדיין בלי סכום: "0 ₪" נראה כמו הצהרה
            שההוצאה הזו לא עולה כלום. אמירה במילים היא מה שהיא באמת. */}
        <span className={`fin-expense-total ${expense.total_agorot ? '' : 'is-empty'}`}>
          {expense.total_agorot ? expense.total_display : t.expenseNoAmount}
        </span>
        {/* כל השורה לחיצה — וזה נאמר במילה, לא רק בסמן העכבר. */}
        <span className="fin-expense-edit" aria-hidden="true">{t.editRowLabel}</span>
      </button>
    </li>
  )
}

function ScenariosList({ scenarios }: { scenarios: FinanceSummary['cost']['scenarios'] }) {
  return (
    <div className="fin-scenarios">
      <h3 className="fin-subtitle">{t.scenariosTitle}</h3>
      <ul className="fin-scenario-list">
        {scenarios.map((s) => (
          <li
            key={s.attendees}
            className={`fin-scenario ${s.is_current ? 'current' : ''} ${
              s.is_commitment ? 'commitment' : ''
            }`}
          >
            <span className="fin-scenario-people">
              {t.scenarioPeople(s.attendees)}
              {/* שני התגים האלה הם מה שהופך לוח מספרים עגולים ללוח
                  שימושי: הם מסמנים איפה האירוע עומד ואיפה המחיר זז. */}
              {s.is_current && <em className="fin-tag">{t.scenarioCurrent}</em>}
              {s.is_commitment && !s.is_current && (
                <em className="fin-tag fin-tag-quiet">{t.scenarioCommitment}</em>
              )}
            </span>
            <span className="fin-scenario-total">{s.total_display}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  מסך "מתנות" — המקום שבו מנהלים את המתנות בפועל
// ════════════════════════════════════════════════════════════════════════

/**
 * **המאזן מציג את התוצאה; כאן מנהלים את המתנות** (2026-09-30). סדר המסך
 * עונה על שלוש שאלות, בסדר הזה: כמה נספר → האם סיימנו לספור → ואם לא, מה
 * עושים עכשיו.
 *
 * 1. **למעלה** — "מתנות שנספרו" ושורה אחת: מעטפות · אשראי. "מעטפות" ולא
 *    "מזומן": במעטפה יכול להיות גם צ'ק (החלטת מייסד).
 * 2. **"+ הוספת מתנה"** — המונה הקיים (ממי? כמה? שמירה והבאה).
 * 3. **"סיימתם לספור?"** — מיד אחרי ההוספה, לא בסוף רשימה של 150 שורות.
 * 4. **כל המתנות** — לחיצה על מעטפה פותחת עריכה (כולל מחיקה). מתנה
 *    באשראי מגיעה מנותן המתנה ולא נערכת כאן; סטטוסי סליקה נשארים במסך
 *    "מתנות באשראי".
 * 5. **לפי מוזמן** — מקופל, עם ההתקדמות ("נספרו X מתוך Y מוזמנים").
 *
 * שום מנגנון פנימי לא נאמר כאן: לא "סימון", לא "חותמת". הזוג רואה "הספירה
 * הסתיימה ✓" — או "נוספה מתנה חדשה" כשהמצב חזר ל"עד עכשיו".
 */
function GiftsView({
  data,
  counting,
  byGuest,
  countingNow,
  onStart,
  onStop,
  onSaved,
  onLoadByGuest,
  onEditEntry,
  marking,
  markError,
  onMarkDone,
  onUndoDone,
  onBackToBalance,
}: {
  data: FinanceSummary
  counting: GiftCounting
  byGuest: GuestGiftRow[] | null
  countingNow: boolean
  onStart: () => void
  onStop: () => void
  onSaved: () => void
  onLoadByGuest: () => void
  onEditEntry: (e: GiftEntry) => void
  marking: boolean
  markError: string | null
  onMarkDone: () => void
  onUndoDone: () => void
  onBackToBalance: () => void
}) {
  // הספירה נפתחת מיום האירוע ואילך (החלטת בעלים). הנעילה **מסבירה את
  // עצמה** ואומרת מתי היא נפתחת.
  if (!counting.counting_open) {
    return (
      <section className="fin-card fin-locked">
        <div className="empty">
          <p className="empty-title">{t.countingLockedTitle}</p>
          {counting.days_until_open !== null && (
            <p className="empty-desc">{t.countingLockedBody(counting.days_until_open)}</p>
          )}
        </div>
      </section>
    )
  }

  const { income } = counting
  const total = income.total_display || income.envelopes_display
  const hasGifts = counting.entries.length > 0
  const showCredit = counting.credit_service_active || income.credit_count > 0

  return (
    <>
      {/* ── 1. כמה נספר ─────────────────────────────────────────────── */}
      <section className="fin-gifts-head" aria-labelledby="fin-gifts-title">
        <h2 id="fin-gifts-title" className="fin-gifts-title">{g.title}</h2>
        {hasGifts ? (
          <>
            <p className="fin-balance-value">{total}</p>
            <p className="fin-balance-eyebrow">{g.totalLabel}</p>
          </>
        ) : (
          // עוד אין מתנות — משפט אחד, פעם אחת. בלי רשימה ריקה ובלי "0 מתוך 30".
          <>
            <p className="fin-quiet-title">{g.noneYet}</p>
            <p className="fin-hint">{t.giftsEmptyBody}</p>
          </>
        )}
        {hasGifts && (
          <p className="fin-gifts-split">
            <span>
              {g.envelopes} · <strong>{income.envelopes_display}</strong>
            </span>
            {showCredit && (
              <span>
                {g.credit} ·{' '}
                {/* הסכום חסום ⇒ המניין ולא "0 ₪": אפס היה טענה אחרת. */}
                <strong>{income.credit_display || String(income.credit_count)}</strong>
              </span>
            )}
          </p>
        )}
        {income.total_agorot === null && <p className="fin-hint">{t.totalPartialNote}</p>}
        {income.credit_count > 0 && !counting.credit_amounts_visible && (
          <p className="fin-hint">{t.creditLockedNote}</p>
        )}
      </section>

      {/* ── 2. הוספת מתנה ──────────────────────────────────────────── */}
      {countingNow ? (
        <EnvelopeCounter
          startNumber={counting.next_envelope_number}
          onSaved={onSaved}
          onClose={onStop}
        />
      ) : (
        <div className="fin-counter-cta">
          <button type="button" className="btn-primary" onClick={onStart}>
            {g.add}
          </button>
        </div>
      )}

      {/* ── 3. סיימתם לספור? — רק כשיש מה לסכם, ולא באמצע הזנה ──────── */}
      {!countingNow && hasGifts && (
        <section className="fin-quiet fin-done" aria-live="polite">
          {data.counting_done ? (
            <>
              <p className="fin-quiet-title">{g.doneTitle}</p>
              <p className="fin-done-total">{g.doneTotal(total)}</p>
              <div className="fin-done-actions">
                <button type="button" className="btn-ghost fin-done-btn" onClick={onBackToBalance}>
                  {g.toBalance}
                </button>
                <button
                  type="button"
                  className="btn-link fin-done-btn"
                  disabled={marking}
                  onClick={onUndoDone}
                >
                  {o.undoDone}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="fin-quiet-title">
                {data.counting_reopened ? g.reopenedTitle : g.askDone}
              </p>
              {data.counting_reopened && <p className="fin-hint">{g.reopenedBody}</p>}
              <button
                type="button"
                className="btn-primary fin-done-btn"
                disabled={marking}
                onClick={onMarkDone}
              >
                {/* "כן, …" עונה על השאלה שמעליו. כשנוספה מתנה אין שאלה על
                    המסך — ואז הכפתור אומר את הפעולה עצמה. */}
                {data.counting_reopened ? o.markDone : g.markDoneYes}
              </button>
            </>
          )}
          {markError && (
            <p className="form-error" role="alert">
              {markError}
            </p>
          )}
        </section>
      )}

      {/* ── 4. כל המתנות — רק כשיש מה להציג ───────────────────────── */}
      {hasGifts && (
      <section className="fin-section">
        <h2 className="fin-section-title">{t.giftsLogTitle}</h2>
        <GiftLog entries={counting.entries} onEdit={onEditEntry} />
        {income.unidentified_count > 0 && (
          <p className="fin-hint fin-unidentified">
            {t.unidentifiedSummary(income.unidentified_count, income.unidentified_display)}
          </p>
        )}
      </section>
      )}

      {/* ── 5. לפי מוזמן — מקופל, ורק כשכבר נספרה מתנה ─────────────── */}
      {hasGifts && (
      <section className="fin-section">
        <div className="fin-section-head">
          <h2 className="fin-section-title">{t.byGuestTitle}</h2>
          {byGuest === null && (
            <button type="button" className="btn-ghost btn-sm" onClick={onLoadByGuest}>
              {t.byGuestLoad}
            </button>
          )}
        </div>
        <p className="fin-hint">
          {t.countedProgress(data.breakdown.guests_counted, data.rsvp.total_guests)}
        </p>
        {byGuest !== null && <ByGuestList rows={byGuest} />}
      </section>
      )}
    </>
  )
}

/**
 * יומן המתנות — **חלון ולא ארכיון.** אחרי ערב ספירה יש כאן 150 שורות; מי
 * שבא לוודא שהמעטפה האחרונה נתפסה צריך את האחרונות. לחיצה על מעטפה פותחת
 * עריכה; מתנה באשראי היא עסקה של נותן המתנה ולא נערכת כאן.
 */
function GiftLog({
  entries,
  onEdit,
}: {
  entries: GiftEntry[]
  onEdit: (e: GiftEntry) => void
}) {
  const WINDOW = 12
  const [showAll, setShowAll] = useState(false)
  const shown = showAll ? entries : entries.slice(0, WINDOW)

  return (
    <div className="fin-gift-log">
      <ul className="fin-gift-list">
        {shown.map((e) => (
          <GiftRow key={`${e.source}-${e.id}`} entry={e} onEdit={onEdit} />
        ))}
      </ul>
      {entries.length > WINDOW && (
        <div className="fin-gift-more">
          <span className="fin-hint">
            {t.giftsShowingSome(shown.length, entries.length)}
          </span>
          {!showAll && (
            <button type="button" className="btn-link" onClick={() => setShowAll(true)}>
              {t.giftsShowMore(entries.length - WINDOW)}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function GiftRow({ entry, onEdit }: { entry: GiftEntry; onEdit: (e: GiftEntry) => void }) {
  const content = (
    <>
      <span className="fin-gift-who">
        {/* מעטפה בלי שיוך מוצגת כ"לא מזוהה" ולא כשורה ריקה: זה מצב
            מתועד שאפשר לחזור אליו ולשייך בעריכה. */}
        {entry.guest_name || <em className="fin-unknown">{t.envelopeUnknownBadge}</em>}
        {entry.is_external && (
          <span className="fin-badge fin-badge-external">{t.externalBadge}</span>
        )}
        {entry.shared_names.length > 0 && (
          <span className="fin-gift-shared">{t.sharedWith(entry.shared_names)}</span>
        )}
      </span>
      <span className="fin-gift-amount">{entry.amount_display || '•••'}</span>
      <span className="fin-gift-source">
        {entry.source === 'envelope'
          ? `${t.sourceEnvelope} #${entry.envelope_number}`
          : t.sourceCredit}
      </span>
    </>
  )
  return (
    <li className="fin-gift-item">
      {entry.source === 'envelope' ? (
        <button type="button" className="fin-gift fin-gift-btn" onClick={() => onEdit(entry)}>
          {content}
        </button>
      ) : (
        <div className="fin-gift">{content}</div>
      )}
    </li>
  )
}

/**
 * מצב המתנה לכל מוזמן.
 *
 * **ההבחנה שאסור לטשטש:** "עדיין לא נספרה" אינו "לא נתן". מוזמן בלי
 * שורת מתנה הוא מוזמן שהמעטפה שלו עוד לא הגיעה לערימה, ולא מישהו
 * שהחליט לא להעניק. המשפט מתחת לרשימה אומר את זה במפורש, כי הרשימה
 * לבדה מזמינה בדיוק את הפרשנות השגויה.
 */
function ByGuestList({ rows }: { rows: GuestGiftRow[] }) {
  const [filter, setFilter] = useState<'all' | 'counted' | 'not_counted'>('all')

  const shown = rows.filter((r) => {
    if (filter === 'all') return true
    if (filter === 'counted') return r.status !== 'not_counted'
    return r.status === 'not_counted'
  })

  return (
    <div className="fin-card">
      <div className="fin-filters">
        {(
          [
            ['all', t.filterAll],
            ['counted', t.filterCounted],
            ['not_counted', t.filterNotCounted],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`fin-filter ${filter === value ? 'active' : ''}`}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <ul className="fin-guest-list">
        {shown.map((r) => (
          <li key={r.guest_id} className="fin-guest-row">
            <span className="fin-guest-name">{r.full_name}</span>
            <span className="fin-guest-amount">{r.total_display}</span>
            <span className={`fin-guest-status fin-status-${r.status}`}>
              {t.statusLabels[r.status]}
            </span>
            {r.gift_count > 1 && (
              // כמה מתנות לאותו מוזמן מצטברות ולא דורסות זו את זו —
              // שתי מעטפות מדוד לוי הן ₪1,000, לא ₪500.
              <span className="fin-guest-count">{t.giftCountBadge(r.gift_count)}</span>
            )}
          </li>
        ))}
      </ul>

      <p className="fin-hint">{t.notCountedHint}</p>
    </div>
  )
}

/**
 * עלות ממוצעת לאדם, ומתחתיה משפט אחד על אדם נוסף — **רק כשהחישוב מצדיק
 * אותו.** ``next_attendee`` הוא ההפרש בין העלות עם עוד מגיע אחד לבין
 * העלות עכשיו, ולכן הוא נכון גם מתחת להתחייבות (0) וגם מעליה. בלי
 * התחייבות ובלי הוצאות לפי אדם, הוא 0 מסיבה אחרת — ואז אין משפט בכלל.
 */
function PerPerson({ cost }: { cost: FinanceSummary['cost'] }) {
  const next = cost.next_attendee_agorot
  const unused = cost.commitments.find((c) => c.unused_quantity > 0)
  let line: string | null = null
  if (next > 0) {
    line = o.nextAdds(cost.next_attendee_display)
    if (cost.cost_per_attendee_agorot !== null && next < cost.cost_per_attendee_agorot) {
      line += ` ${o.nextAddsLessThanAverage}`
    }
  } else if (unused) {
    line = o.nextFree(unused.committed_quantity, unused.label)
  }

  return (
    <div className="fin-per-person">
      <div className="fin-per-person-row">
        <span>{t.perPersonLabel}</span>
        <strong>{cost.cost_per_attendee_display}</strong>
      </div>
      {line && <p className="fin-hint">{line}</p>}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  7. הפירוט המלא
// ════════════════════════════════════════════════════════════════════════

/** שורות "תווית ····· ערך" — במקום רשת של תאים בגודל שווה. */
function KeyValues({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="fin-kv">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * **כל מה שהיה בלשונית "סיכום" — ועוד — מקופל לאזור אחד.** מבנה העלות,
 * ההתחייבות מול הספק, "מה אם", מתנות מול הגעה, אישורי ההגעה והדוח המלא.
 * אלה מספרים נכונים ושימושיים, אבל הם לא התשובה לשאלה "איפה אנחנו עומדים"
 * — ולכן הם כאן, ולא למעלה באותו גודל כמו המאזן.
 */
function DetailsSection({
  data,
  terms,
  open,
  onToggle,
}: {
  data: FinanceSummary
  terms: ReturnType<typeof activeEventTerms>
  open: boolean
  onToggle: () => void
}) {
  const { cost, rsvp, breakdown } = data
  const hasAmounts = data.expenses.some((e) => e.amount_agorot > 0 || e.total_agorot > 0)
  const noGiftsYet = (data.income.total_agorot ?? 0) === 0

  // הדוח המלא נטען לפי דרישה, לא עם המסך: הוא מכיל שורה לכל מוזמן
  // (מאות שורות באירוע טיפוסי), ואיש לא מסתכל עליו רוב הזמן.
  const [report, setReport] = useState<FinanceReport | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  function loadReport() {
    setLoadingReport(true)
    setReportError(null)
    getFinanceReport()
      .then(setReport)
      .catch((e) => setReportError(e instanceof Error ? e.message : t.reportError))
      .finally(() => setLoadingReport(false))
  }

  const costRows: [string, string][] = [
    [data.attendance.is_final ? t.totalCostLabel : t.estimatedCostLabel, cost.total_display],
    [t.paidSummary, cost.paid_display],
    [t.unpaidSummary, cost.unpaid_display],
    [t.fixedLabel, cost.fixed_display],
    [t.variableLabel, cost.variable_display],
    [t.perPersonLabel, cost.cost_per_attendee_display || t.perPersonEmpty],
  ]
  if (cost.estimated_agorot > 0) costRows.push([t.estimatedSummary, cost.estimated_display])

  const giftRows: [string, string][] = [
    [t.fromAttendees, breakdown.from_attendees_display],
    [t.fromNonAttendees, breakdown.from_non_attendees_display],
  ]
  if (breakdown.from_external_agorot > 0) {
    giftRows.push([t.externalLabel, breakdown.from_external_display])
  }
  if (breakdown.unattributed_agorot > 0) {
    giftRows.push([t.unattributedLabel, breakdown.unattributed_display])
  }
  giftRows.push(
    [t.guestsCounted, String(breakdown.guests_counted)],
    [t.guestsNotCounted, String(breakdown.guests_not_counted)],
  )

  return (
    <section className={`fin-card fin-details ${open ? 'open' : ''}`}>
      <h2 className="fin-card-title">
        <button
          type="button"
          className="fin-whatif-btn fin-details-btn"
          aria-expanded={open}
          aria-controls="fin-details-body"
          onClick={onToggle}
        >
          <span className="fin-group-chevron" aria-hidden="true" />
          <span className="fin-details-head">
            <span>{o.detailsTitle}</span>
            <span className="fin-details-hint">{o.detailsHint}</span>
          </span>
        </button>
      </h2>

      {open && (
        <div id="fin-details-body" className="fin-details-body">
          <div className="fin-detail">
            <h3 className="fin-subtitle">{t.costSplitTitle}</h3>
            <KeyValues rows={costRows} />
          </div>

          {cost.commitments.map((c) => (
            <CommitmentDetail key={c.expense_id} commitment={c} attendance={data.attendance} />
          ))}

          {/* רק כשיש לפחות סכום אחד — אחרת כל התרחישים יוצאים "0 ₪", וזה
              נראה כמו נתון ("לא עולה כלום") כשבפועל עוד אין נתונים. */}
          {hasAmounts && (
            <div className="fin-detail">
              <h3 className="fin-subtitle">{t.whatIfTitle}</h3>
              <NextPersonCard cost={cost} />
              {cost.scenarios.length > 0 && <ScenariosList scenarios={cost.scenarios} />}
            </div>
          )}

          {/* הפער בין הגעה למתנות. בלי מתנות — שורות של אפסים, ולכן לא מוצג. */}
          {!noGiftsYet && (
            <div className="fin-detail">
              <h3 className="fin-subtitle">{t.breakdownTitle}</h3>
              <KeyValues rows={giftRows} />
            </div>
          )}

          <div className="fin-detail">
            <h3 className="fin-subtitle">{t.rsvpTitle}</h3>
            {/* כולם במוזמנים (שורות ברשימה), כדי שהמספרים יסתכמו לסה"כ;
                מספר האנשים שאישרו — בנפרד ובשמו. */}
            <KeyValues
              rows={[
                [t.rsvpGuests, String(rsvp.total_guests)],
                [t.rsvpConfirmed, String(rsvp.confirmed_guests)],
                [t.rsvpMaybe, String(rsvp.maybe_guests)],
                [t.rsvpDeclined, String(rsvp.declined_guests)],
                [t.rsvpPending, String(rsvp.pending_guests)],
                [t.rsvpConfirmedPeople, String(rsvp.confirmed_people)],
              ]}
            />
          </div>

          {/* ── הדוח המלא ─────────────────────────────────────────── */}
          <div id="fin-report" className="fin-detail fin-report">
            <div className="fin-section-head">
              <h3 className="fin-subtitle">{t.reportTitle}</h3>
              {!report && (
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  onClick={loadReport}
                  disabled={loadingReport}
                >
                  {loadingReport ? t.reportLoading : t.byGuestLoad}
                </button>
              )}
            </div>
            <p className="fin-hint">{t.reportIntro}</p>

            {reportError && (
              <p className="form-error" role="alert">
                {reportError}
              </p>
            )}

            {report && (
              <>
                <div className="fin-report-card">
                  <ReportTable report={report} />
                </div>
                <div className="fin-download">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => downloadReport(report, terms.eventNoun)}
                  >
                    {t.downloadReport}
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => printReport(report)}
                  >
                    {t.printReport}
                  </button>
                </div>
              </>
            )}
          </div>

          {/* השורה שמונעת את השאלה "רגע, כמה ירד לנו?". */}
          <p className="fin-hint">{t.noFeeNote}</p>
        </div>
      )}
    </section>
  )
}

/**
 * טבלת הדוח — **שורה אחת מלאה לכל מוזמן.**
 *
 * שתי עמודות המפתח, "סטטוס הגעה" ו"סה״כ מתנה", יושבות זו לצד זו ואינן
 * נגזרות זו מזו: מוזמן שביטל הגעה ונתן ₪1,000 מופיע בדיוק כך. זה כל
 * הרעיון של הדוח — לא לחבר מידע משלושה מסכים.
 *
 * **תא "טרם נספרה" אינו "0 ₪".** מעטפה שנספרה בסכום אפס מוצגת כ-"0 ₪";
 * מוזמן שעדיין לא נספר מוצג כ"טרם נספרה". שני מצבים שונים, שתי מחרוזות.
 *
 * בטלפון הטבלה נגללת אופקית בתוך המכל שלה (``overflow-x``) ולא שוברת את
 * העמוד — עמודות שנדחסות לרוחב מסך טלפון הופכות ל-9 מילים שבורות.
 */
function ReportTable({ report }: { report: FinanceReport }) {
  const [onlyGifts, setOnlyGifts] = useState(false)
  const rows = onlyGifts ? report.guests.filter((g) => g.gift_count > 0) : report.guests

  return (
    <>
      <div className="fin-filters">
        <button
          type="button"
          className={`fin-filter ${!onlyGifts ? 'active' : ''}`}
          onClick={() => setOnlyGifts(false)}
        >
          {t.filterAll}
        </button>
        <button
          type="button"
          className={`fin-filter ${onlyGifts ? 'active' : ''}`}
          onClick={() => setOnlyGifts(true)}
        >
          {t.filterCounted}
        </button>
      </div>

      <div className="fin-table-scroll">
        <table className="fin-table">
          <thead>
            <tr>
              <th>{t.colGuest}</th>
              <th>{t.colPhone}</th>
              <th>{t.colRsvp}</th>
              <th>{t.colInvited}</th>
              <th>{t.colAttended}</th>
              <th>{t.colCredit}</th>
              <th>{t.colEnvelope}</th>
              <th>{t.colTotal}</th>
              <th>{t.colNotes}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.guest_id}>
                <td>{g.full_name}</td>
                <td className="fin-num">{g.phone}</td>
                <td>
                  <span className={`fin-guest-status rsvp-${g.rsvp_status}`}>
                    {t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status}
                  </span>
                </td>
                <td className="fin-num">{g.party_size}</td>
                <td className="fin-num">{g.attended_count}</td>
                <td className="fin-num">{g.credit_display || '—'}</td>
                <td className="fin-num">{g.envelope_display || '—'}</td>
                <td className="fin-num fin-strong">
                  {g.status === 'not_counted' ? (
                    <span className="fin-muted">{t.cellNotCounted}</span>
                  ) : (
                    g.total_display
                  )}
                </td>
                <td className="fin-note-cell">{g.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* מעטפות בלי שיוך לא נעלמות מהדוח — אחרת הסכום הכולל לא מסתדר
          עם סכום השורות שמעליו. */}
      {report.unidentified.length > 0 && (
        <p className="fin-hint fin-unidentified">
          {t.unidentifiedSummary(
            report.income.unidentified_count,
            report.income.unidentified_display,
          )}
        </p>
      )}
    </>
  )
}

// ── עזרים ────────────────────────────────────────────────────────────

/** מקבץ לפי **מפתח** ולא לפי תווית — כדי להתאים ל-``cost.categories``
 *  שמגיע מהשרת, שם גם הסכום של כל קבוצה כבר חושב. */
function groupByCategory(expenses: Expense[]): Map<string, Expense[]> {
  const map = new Map<string, Expense[]>()
  for (const e of expenses) {
    const list = map.get(e.category)
    if (list) list.push(e)
    else map.set(e.category, [e])
  }
  return map
}

/**
 * מאיפה הסכום הגיע — **בשפה של הזוג, לא בשפת המנוע.**
 *
 * "320 ₪ × 500 מנות" ולא "לפי מספר המגיעים", ו-"10% משאר ההוצאות" ולא
 * "0 ₪ × 10" — שורת אחוז אינה נושאת מחיר, והצגתה כמכפלה נתנה מספר
 * שנראה שבור בדיוק בשורה שהזוג הכי פחות מבין.
 *
 * "מנות" נאמר רק כשיש התחייבות על השורה — שם באמת מדובר בחוזה על מנות.
 * שורת אלכוהול לפי אדם היא "לפי מגיעים", ו"מנות" שם היה שקר קטן.
 */
function describeCalc(e: Expense): string {
  const price = `${Math.trunc(e.amount_agorot / 100).toLocaleString('he-IL')} ₪`

  if (e.calc_method === 'percent') return e.quantity ? t.calcPercent(e.quantity) : ''
  if (e.calc_method === 'fixed') return ''
  // בלי מחיר אין חישוב — "0 ₪ × 3 מגיעים" נראה כמו נתון.
  if (!e.amount_agorot) return ''
  if (e.billed_quantity === null) return ''

  if (e.calc_method === 'per_attendee') {
    return e.committed_quantity
      ? t.calcPerPortion(price, e.billed_quantity)
      : t.calcPerAttendee(price, e.billed_quantity)
  }
  if (e.calc_method === 'per_guest') return t.calcPerGuest(price, e.billed_quantity)
  return t.calcPerUnit(price, e.billed_quantity)
}

/** מסיר מינוס מוביל מסכום מעוצב — ראו ההסבר במקום השימוש. */
function stripSign(display: string): string {
  return display.replace(/^-/, '')
}

/**
 * הדוח הסופי — **מקור אחד לשני הפלטים**: PDF/הדפסה ו-Excel.
 *
 * שבעה חלקים (§19), בסדר שבו קוראים דוח: מי, כמה הגיעו, מה החוזה אמר,
 * על מה שולם, למי, מה התקבל, ומה השורה התחתונה. בלי המבנה המשותף כאן
 * היו שתי רשימות עמודות שצריך לזכור לעדכן יחד — ובדוח כספי זה בדיוק
 * המקום שבו קובץ הייצוא מתחיל לספר סיפור אחר מהמסך.
 *
 * **כל המספרים כאן כבר חושבו בשרת.** הפונקציות מסדרות אותם, לא מחשבות.
 */

/** ח"א — פרטי האירוע. */
function eventFacts(report: FinanceReport): string[][] {
  return [
    [t.repEventType, report.event_type_label],
    [t.repHosts, report.event_title],
    [t.repEventDate, formatEventDate(report.event_date)],
    [t.repVenue, report.venue_name],
  ].filter((r) => r[1])
}

/** ח"ב — נתוני מוזמנים. */
function guestFacts(report: FinanceReport): string[][] {
  const { rsvp, attendance } = report
  const rows = [
    [t.repGuestsTotal, String(rsvp.total_guests)],
    [t.repConfirmed, String(rsvp.confirmed_people)],
    [t.repDeclined, String(rsvp.declined_guests)],
    [t.repPending, String(rsvp.pending_guests)],
    [t.repActual, attendance.actual != null ? String(attendance.actual) : t.repNotEntered],
  ]
  // הפער מוצג רק כשיש מספר בפועל — אחרת הוא טענה בלי כיסוי.
  if (attendance.no_show) rows.push([t.repNoShow, String(attendance.no_show)])
  if (attendance.extra) rows.push([t.repExtra, String(attendance.extra)])
  return rows
}

/** ח"ג — ההתחייבות מול הספק. שורה לכל התחייבות, לא רק לאולם. */
function commitmentFacts(report: FinanceReport): string[][] {
  const rows: string[][] = []
  for (const c of report.cost.commitments) {
    rows.push(
      [c.label, ''],
      [t.repMealPrice, formatAgorot(c.unit_price_agorot)],
      [t.repCommitted, String(c.committed_quantity)],
      [t.repConfirmed, String(c.attendees)],
      [t.repBilled, String(c.billed_quantity)],
    )
    if (c.reserve_quantity) rows.push([t.reserveFact, String(c.reserve_quantity)])
    if (c.over_commitment) rows.push([t.repOver, String(c.over_commitment)])
    if (c.unused_quantity) rows.push([t.repUnused, String(c.unused_quantity)])
    rows.push([t.repFinalCost, c.total_display])
  }
  return rows
}

const EXPENSE_HEAD = [
  t.repCategory, t.repExpenseName, t.repVendor, t.repCalc,
  t.repTotal, t.repPaid, t.repRemaining,
]

function expenseRows(report: FinanceReport): string[][] {
  return report.expenses.map((e) => [
    e.category_label,
    e.label,
    e.vendor ?? '',
    describeCalc(e) || t.calcMethods.fixed,
    e.total_display,
    e.paid_display,
    e.remaining_display,
  ])
}

const PAYMENT_HEAD = [
  t.repPaymentDate, t.repPaymentFor, t.repPaymentTo,
  t.repPaymentKind, t.repPaymentAmount, t.noteLabel,
]

/** ח"ה — כל התשלומים, שטוחים מכל ההוצאות ולפי תאריך. */
function paymentRows(report: FinanceReport): string[][] {
  const rows: { date: string; cells: string[] }[] = []
  for (const e of report.expenses) {
    for (const p of e.payments) {
      rows.push({
        date: p.paid_on,
        cells: [
          p.paid_on_display,
          e.label,
          p.payee,
          p.kind === 'advance' ? t.paymentAdvance : t.paymentRegular,
          p.amount_display,
          p.note ?? '',
        ],
      })
    }
  }
  // תשלום בלי תאריך יורד לסוף — הוא לא "לפני הכול".
  rows.sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999'))
  return rows.map((r) => r.cells)
}

const GIFT_HEAD = [
  t.repGiftFrom, t.colPhone, t.colRsvp, t.repGiftKind,
  t.repGiftSource, t.colTotal, t.colNotes,
]

/**
 * ח"ו — כל המתנות: מוזמנים, נותנים חיצוניים, ומעטפות שטרם זוהו.
 *
 * **שלוש הקבוצות יחד**, אחרת סה״כ המתנות בסיכום גדול מסכום השורות
 * שמעליו — וזו בדיוק הצורה שבה דוח מאבד אמון.
 */
function giftRows(report: FinanceReport): string[][] {
  const rows = report.guests.map((g) => [
    g.full_name,
    g.phone,
    t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status,
    t.repGiftGuest,
    [g.credit_agorot ? t.sourceCredit : '', g.envelope_agorot ? t.sourceEnvelope : '']
      .filter(Boolean)
      .join(' + '),
    // "טרם נספרה" ולא "0 ₪": אפס הוא טענה שאין לה כיסוי כשלא נספר כלום.
    g.status === 'not_counted' ? t.cellNotCounted : g.total_display,
    g.note,
  ])

  for (const e of report.external) {
    rows.push([
      e.guest_name, e.external_phone, '', t.repGiftExternal,
      t.sourceEnvelope, e.amount_display, e.note ?? '',
    ])
  }
  for (const e of report.unidentified) {
    rows.push([
      t.repGiftUnknown, '', '', t.repGiftUnknown,
      `${t.sourceEnvelope} #${e.envelope_number}`, e.amount_display, e.note ?? '',
    ])
  }
  return rows
}

/** ח"ז — הסיכום. §20: התוצאה במילים פשוטות. */
function summaryFacts(report: FinanceReport): string[][] {
  const { cost, income, bottom_line_agorot } = report
  const rows = [
    [t.summaryCostLabel(report.event_type_label), cost.total_display],
    [t.summaryPaidLabel, cost.paid_display],
    [t.summaryUnpaidLabel, cost.unpaid_display],
    ['', ''],
    [t.repGiftsEnvelopes, income.envelopes_display],
  ]
  // שורת האשראי מופיעה רק כשיש מתנות אשראי. "0 ₪" או משפט הנעילה
  // באירוע שלא השתמש בשירות הם תשובה לשאלה שלא נשאלה.
  if (income.credit_count) {
    rows.push([t.repGiftsCredit, income.credit_display || t.creditLockedNote])
  }
  if (income.external_count) rows.push([t.repGiftsExternal, income.external_display])
  rows.push([t.repGiftsTotal, income.total_display || '—'], ['', ''])

  if (bottom_line_agorot !== null) {
    const label =
      bottom_line_agorot > 0
        ? t.repResultSurplus
        : bottom_line_agorot < 0
          ? t.repResultDeficit
          : t.repResultEven
    // הנוסחה נאמרת **בתוך** התווית ולא כשורה משלה — שורה עם תווית ובלי
    // ערך נראית כמו נתון שלא נטען.
    rows.push([`${label} (${t.repResultFormula})`, stripSign(report.bottom_line_display)])
  } else {
    rows.push([t.bottomLineLabel, t.bottomLineLocked])
  }
  return rows
}

/** ``2026-09-05`` → "5 בספטמבר 2026". ריק נשאר ריק. */
function formatEventDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('he-IL', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** אגורות → "12,000 ₪". לתצוגה בדוח בלבד — לא חישוב. */
function formatAgorot(agorot: number): string {
  return `${Math.trunc(agorot / 100).toLocaleString('he-IL')} ₪`
}

// ── Excel (§22) ──────────────────────────────────────────────────────

/**
 * חמישה גיליונות: סיכום · מוזמנים · הוצאות · תשלומים · מתנות.
 *
 * לא dump: לכל גיליון כותרות מודגשות שקופאות בראש, רוחב עמודות, ויישור
 * RTL. הסכומים בגיליון הסיכום יושבים למעלה, כדי שמי שפותח את הקובץ
 * יראה את התמונה לפני הפירוט.
 *
 * הכותב הוא שלנו (``lib/xlsx``) — ראו שם למה ולא ספרייה.
 */
function downloadReport(report: FinanceReport, eventNoun: string): void {
  const facts = (rows: string[][]) => rows.map(([k, v]) => [k, v] as Cell[])

  downloadWorkbook(t.excelFileName(report.event_title || eventNoun), [
    {
      name: t.sheetSummary,
      head: [t.repSummaryTitle, ''],
      rows: [
        ...facts(summaryFacts(report)),
        ['', ''],
        [t.repEventTitle, ''],
        ...facts(eventFacts(report)),
        ['', ''],
        [t.repGuestsTitle, ''],
        ...facts(guestFacts(report)),
        ...(report.cost.commitments.length
          ? [['', ''], [t.repCommitmentTitle, ''], ...facts(commitmentFacts(report))]
          : []),
        ['', ''],
        [t.noFeeNote, ''],
      ],
      widths: [32, 22],
    },
    {
      name: t.sheetGuests,
      head: [t.colGuest, t.colPhone, t.colRsvp, t.colInvited, t.colAttended,
             t.colCredit, t.colEnvelope, t.colTotal, t.colNotes],
      rows: report.guests.map((g) => [
        g.full_name, g.phone, t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status,
        g.party_size, g.attended_count,
        g.credit_display || '', g.envelope_display || '',
        g.status === 'not_counted' ? t.cellNotCounted : g.total_display,
        g.note,
      ]),
      widths: [22, 14, 14, 12, 12, 14, 14, 14, 26],
    },
    {
      name: t.sheetExpenses,
      head: EXPENSE_HEAD,
      rows: expenseRows(report),
      widths: [18, 22, 18, 22, 14, 14, 14],
    },
    {
      name: t.sheetPayments,
      head: PAYMENT_HEAD,
      rows: paymentRows(report),
      widths: [14, 22, 20, 10, 14, 26],
    },
    {
      name: t.sheetGifts,
      head: GIFT_HEAD,
      rows: giftRows(report),
      widths: [22, 14, 14, 14, 16, 14, 26],
    },
  ])
}

// ── PDF / הדפסה (§19 + §21) ──────────────────────────────────────────

/**
 * מונוגרם VEYA הרשמי (``logo_nobg.png`` — הטבעת + היהלום + ה-V, זהב על
 * שקוף) מוטבע כ-base64, לצד שם המותג בטיפוגרפיה. לא לוקאפ אופקי מלא:
 * ב-``veya_horizontal.png``/``logo.svg``/``logo.png`` מילת "VEYA" צבועה
 * שנהב-קרם — מיועדת לרקע כהה, ונעלמת על הדף הלבן של הדוח (בדיוק כמו
 * בכל מסך במוצר שמציג את הלוגו המלא: הוא תמיד יושב על כרטיס/רקע כהה).
 * אין ב-VEYA שום גרסה רשמית לרקע בהיר. הפתרון: המונוגרם הרשמי (תקין
 * לגמרי על לבן — כולו זהב) + "VEYA" כטקסט ב-``--font-brand``
 * (Cormorant Garamond) — הפונט ש-``design-system.md`` מייחד *בדיוק*
 * ללוגוטייפ הזה, לא המצאת עיצוב. ראו ``printReport``.
 */
const LOGO_MONOGRAM_IMG = `<img src="${veyaMonogram}" alt="" />`

/**
 * גרסת הדפסה — ומכאן גם PDF, דרך "שמירה כ-PDF" של הדפדפן.
 *
 * ## בלי ספריית PDF
 *
 * ספריית PDF בדפדפן שוקלת מאות קילובייטים, ורובן שוברות עברית ו-RTL
 * בדיוק במסמך שכולו עברית. חלון הדפסה עם ``dir="rtl"`` נותן פלט נכון
 * בכל דפדפן, במשקל אפס, והמשתמש בוחר מדפסת או PDF באותו דיאלוג.
 *
 * ## הלוגו מוטבע כ-base64, לא מקושר
 *
 * חלון ההדפסה נפתח כ-``about:blank``, וכתובת יחסית ל-``/logo_nobg.png``
 * לא בהכרח נפתרת שם. תמונה שלא נטענה בזמן היא דוח בלי מיתוג — ולכן
 * ``veyaMonogramBase64.ts`` מייצא data URI מוכן-מראש (base64 של קובץ
 * ה-PNG הרשמי, בלי לגעת בפיקסל אחד בו). ``position: fixed`` גורם
 * לכותרת לחזור בכל עמוד ב-Chrome וב-Safari; מספרי עמודים מגיעים
 * מהגדרות ההדפסה של הדפדפן עצמו.
 */
function printReport(report: FinanceReport): void {
  const esc = (v: string) =>
    (v ?? '').replace(/[&<>"]/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string,
    )

  const factTable = (rows: string[][]) =>
    `<table class="facts"><tbody>${rows
      .map(
        ([k, v]) =>
          `<tr class="${v ? '' : 'sub'}"><td>${esc(k)}</td><td class="num">${esc(v)}</td></tr>`,
      )
      .join('')}</tbody></table>`

  const dataTable = (head: string[], rows: string[][], numFrom = 3) =>
    rows.length
      ? `<table class="grid"><thead><tr>${head
          .map((h) => `<th>${esc(h)}</th>`)
          .join('')}</tr></thead><tbody>${rows
          .map(
            (r) =>
              `<tr>${r
                .map(
                  (c, i) =>
                    `<td class="${i >= numFrom ? 'num' : ''}${
                      c === t.cellNotCounted ? ' muted' : ''
                    }">${esc(c)}</td>`,
                )
                .join('')}</tr>`,
          )
          .join('')}</tbody></table>`
      : `<p class="muted">${esc(t.repEmptyPayments)}</p>`

  // cls='long' לסקשנים עם טבלת-נתונים באורך משתנה (יכולה להיות ארוכה):
  // break-inside: auto מרשה לה להישבר בין עמודים בלי לגרור שורות שכבר
  // הודפסו לעמוד הבא כדי "לא לשבור" את break-inside: avoid של הסקשן —
  // בלעדיו Chrome עלול לדלג על שורות שלמות בשבירת עמוד (ראו בדיקות ה-PDF).
  const section = (title: string, body: string, cls = '') =>
    `<section${cls ? ` class="${cls}"` : ''}><h2>${esc(title)}</h2>${body}</section>`

  // תאריך בניסוח שקוראים ולא ב-ISO. "2026-09-05" בכותרת של דוח פרימיום
  // הוא פליטה טכנית, לא תאריך.
  const eventDate = formatEventDate(report.event_date)
  const meta = [report.event_type_label, report.venue_name, eventDate]
    .filter(Boolean)
    .join(' · ')

  const html = `<!doctype html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>${esc(t.navTitle)} — ${esc(report.event_title)}</title>
<style>
  /* מרווח עליון של 22mm משאיר שטח בטוח לכותרת הרצה (~12mm) בלי להתקרב
     לשוליים הלא-מודפסים של מדפסות ביתיות. */
  @page { size: A4; margin: 22mm 12mm 14mm; }
  body { font-family: 'Heebo', Arial, sans-serif; color: #2b2620; font-size: 11px; margin: 0; }

  /* כותרת רצה — חוזרת בכל עמוד ב-Chrome וב-Safari, אבל position: fixed
     בהדפסה ממוקם יחסית לאזור התוכן של *כל עמוד* (אחרי שולי @page), לא
     לפינת הנייר — כלומר היא "יושבת" מעל תחילת התוכן בכל עמוד ומכסה
     אותו, לא רק בעמוד הראשון. פתרון: page-spacer (למטה) שומר בפועל שורה
     ריקה בגובה הכותרת בתחילת כל עמוד, בעזרת thead שחוזר על עצמו — כך
     שהתוכן האמיתי מתחיל תמיד מתחת לכותרת הקבועה, בכל עמוד. */
  .runner {
    position: fixed; top: 0; inset-inline: 0;
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px;
    padding-bottom: 10px; border-bottom: 1px solid #e5dec9;
    background: #fff;
  }
  /* טבלה "שקופה" שכל תפקידה לשמור מקום — ה-thead שלה חוזר בתחילת כל
     עמוד (בדיוק כמו .grid thead למטה), ובכך "דוחף" את שאר הדוח מתחת
     לכותרת הקבועה גם בעמוד 2, 3 וכו', לא רק בעמוד הראשון. */
  .page-spacer { width: 100%; border-collapse: collapse; }
  .page-spacer > thead > tr > td { height: 74px; padding: 0; border: 0; }
  .page-spacer > tbody > tr > td { padding: 0; }
  /* המונוגרם הרשמי (זהב, שקוף) יושב ישירות על דף הדוח — בלי תיבת רקע.
     קווי הטבעת דקים מטבע עיצובם (עדינות מכוונת, לא באג) — קטן מ-48px
     בערך הם "נמחקים" בהדפסה בפועל, לכן 52px ולא 32px. לצידו "VEYA"
     כטקסט ב-Cormorant Garamond, הפונט שה-design system מייחד ללוגוטייפ
     הזה בדיוק, בגוון --gold-deep (הגוון היחיד שכוייל לניגודיות טקסט
     תקינה על רקע בהיר — --gold הרגיל הוא צבע מסגרת/משטח, לא טקסט). */
  .brand-mark { display: flex; align-items: center; gap: 12px; flex: none; }
  .brand-mark img { display: block; height: 52px; width: 52px; }
  .brand-mark .brand-word {
    font-family: 'Cormorant Garamond', Georgia, 'Times New Roman', serif;
    font-size: 24px; font-weight: 600; letter-spacing: 5px; color: #896e29;
  }
  .runner .who { font-size: 10px; color: #787064; text-align: start; }
  .runner .who b { display: block; font-size: 12px; color: #2b2620; }

  h1 { font-size: 20px; margin: 0 0 2px; }
  .lede { color: #787064; font-size: 11px; margin: 0 0 16px; }
  h2 {
    font-size: 13px; margin: 0 0 6px; padding-bottom: 4px;
    border-bottom: 1px solid #e5dec9; color: #896e29;
  }
  section { margin-bottom: 16px; break-inside: avoid; }
  /* טבלה ארוכה כן נשברת — אחרת "כל המוזמנים" היה נדחף לעמוד חדש שלם. */
  section.long { break-inside: auto; }

  table { width: 100%; border-collapse: collapse; }
  .facts { width: auto; min-width: 58%; }
  .facts td { padding: 3px 6px; border-bottom: 1px solid #f2ede1; }
  .facts td:last-child { font-weight: 600; }
  .facts tr.sub td { font-weight: 700; color: #2b2620; padding-top: 8px; border-bottom: 0; }

  .grid th, .grid td { border-bottom: 1px solid #e5dec9; padding: 4px 6px; text-align: right; }
  .grid th { background: #fbf6ee; font-weight: 600; font-size: 10px; }
  /* השורות לא נשברות באמצע, והכותרת חוזרת בכל עמוד. */
  .grid tr { break-inside: avoid; }
  .grid thead { display: table-header-group; }

  .num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .muted { color: #787064; }
  .note { color: #787064; font-size: 10px; margin-top: 10px; }
  .result { font-size: 15px; font-weight: 700; }
</style></head><body>

<div class="runner">
  <div class="brand-mark">${LOGO_MONOGRAM_IMG}<span class="brand-word">VEYA</span></div>
  <div class="who"><b>${esc(report.event_title)}</b>${esc(meta)}</div>
</div>

<table class="page-spacer"><thead><tr><td></td></tr></thead><tbody><tr><td>

<h1>${esc(t.navTitle)}</h1>
<p class="lede">${esc(t.repGeneratedAt)} ${esc(
    new Date(report.generated_at).toLocaleDateString('he-IL'),
  )}</p>

${section(t.repSummaryTitle, factTable(summaryFacts(report)))}
${section(t.repEventTitle, factTable(eventFacts(report)))}
${section(t.repGuestsTitle, factTable(guestFacts(report)))}
${
  report.cost.commitments.length
    ? section(t.repCommitmentTitle, factTable(commitmentFacts(report)))
    : ''
}
${section(t.repExpensesTitle, dataTable(EXPENSE_HEAD, expenseRows(report), 4), 'long')}
${section(t.repPaymentsTitle, dataTable(PAYMENT_HEAD, paymentRows(report), 4), 'long')}
<section class="long"><h2>${esc(t.repGiftsTitle)}</h2>${dataTable(
    GIFT_HEAD,
    giftRows(report),
    5,
  )}</section>

<p class="note">${esc(t.noFeeNote)}</p>

</td></tr></tbody></table>
</body></html>`

  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(html)
  win.document.close()
  // ההמתנה נותנת לדפדפן לפרוס את הטבלאות לפני שדיאלוג ההדפסה נפתח;
  // בלעדיה דפדפנים מסוימים מדפיסים עמוד ריק.
  win.onload = () => win.print()
  setTimeout(() => win.print(), 400)
}