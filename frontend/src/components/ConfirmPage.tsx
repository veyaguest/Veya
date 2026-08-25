import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  confirmIcsUrl,
  fetchGiftQuote,
  getConfirm,
  mediaUrl,
  submitConfirm,
  submitGiftCheckout,
} from '../api'
import type { ConfirmGuestPublic, GiftCheckoutResult, GiftQuote } from '../types'
import { getEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

type Choice = 'confirmed' | 'declined' | 'maybe'

/**
 * Guest Hub — העמוד היחיד של המוזמן, בקישור אישי אחד וקבוע (/confirm/{token}).
 *
 * הקישור הזה נשלח פעם אחת ולא מתחלף לעולם: אותה כתובת משרתת את ההזמנה
 * הראשונה, את תזכורת אישור ההגעה, ובעתיד גם את המתנה. מה שמשתנה לאורך
 * הדרך הוא **אילו פעולות פתוחות** — וזה מגיע מהשרת (``data.actions``), לא
 * מכאן. כך פעולה חדשה נדלקת במקום אחד בלבד.
 *
 * ההיררכיה נבנתה למי שפותח את זה בטלפון תוך כדי משהו אחר:
 *   מי מזמין → מתי ואיפה → מה אפשר לעשות → ואז אישור ההגעה.
 */

/** לוגו VEYA הרשמי (מונוגרמה עם יהלום + טבעת כפולה) — זהה למערכת. */
function Monogram() {
  return (
    <span className="auth-monogram">
      <span className="auth-monogram-diamond" />
      <span className="auth-monogram-v">V</span>
    </span>
  )
}

/** מרכיב מחרוזת תאריך+שעה קריאה בעברית להצגה למוזמן. */
function whenText(date: string, time: string): string {
  const parts: string[] = []
  if (date) {
    const d = new Date(date)
    parts.push(
      isNaN(d.getTime())
        ? date
        : d.toLocaleDateString('he-IL', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          }),
    )
  }
  if (time) parts.push(`בשעה ${time}`)
  return parts.join(' · ')
}

/** אילו פעולות אפשר לפתוח ישירות מקישור (``?action=``). */
type HubAction = 'invitation' | 'calendar' | 'navigation' | 'gift'

const ROUTABLE_ACTIONS: HubAction[] = ['invitation', 'calendar', 'navigation', 'gift']

/**
 * פעולה שהמוזמן ביקש לפתוח דרך הקישור.
 *
 * למה זה קיים: הודעת יום-האירוע תוביל **ישר** למתנה, בלי שהמוזמן יחפש
 * אותה בעמוד.
 *
 * **הפרמטר הזה הוא ניתוב בלבד — לא הרשאה.** הוא רק אומר "מה לפתוח",
 * ותמיד נבדק מול ``actions`` שהשרת החזיר. מוזמן שיקליד ``?action=gift``
 * שבוע לפני האירוע לא יקבל כלום, כי השרת מחזיר ``gift: false``. אין כאן
 * שום חישוב תאריכים בצד לקוח — שעון המכשיר אינו מקור אמת.
 */
function readActionParam(): HubAction | null {
  const raw = new URLSearchParams(window.location.search).get('action')
  return ROUTABLE_ACTIONS.includes(raw as HubAction) ? (raw as HubAction) : null
}

/** אייקון פעולה — קבוע ולא תלוי אימוג'י של מערכת ההפעלה. */
function ActionIcon({ name }: { name: HubAction }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  if (name === 'invitation') {
    return (
      <svg {...common}>
        <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2 2 0 0 1 2 2 2 2 0 0 1 2-2h4.5A1.5 1.5 0 0 1 20 5.5v12a1.5 1.5 0 0 1-1.5 1.5H14a2 2 0 0 0-2 2 2 2 0 0 0-2-2H5.5A1.5 1.5 0 0 1 4 17.5z" />
        <path d="M12 6v14" />
      </svg>
    )
  }
  if (name === 'calendar') {
    return (
      <svg {...common}>
        <rect x="3.5" y="5" width="17" height="15" rx="2" />
        <path d="M3.5 9.5h17M8 3.5V6M16 3.5V6" />
        <path d="m9 14 2 2 4-4" />
      </svg>
    )
  }
  if (name === 'gift') {
    return (
      <svg {...common}>
        <rect x="3.5" y="9" width="17" height="4" rx="1" />
        <path d="M5 13v6.5a1.5 1.5 0 0 0 1.5 1.5h11a1.5 1.5 0 0 0 1.5-1.5V13" />
        <path d="M12 9v12" />
        <path d="M12 9S10.5 3.5 8 3.5a2.5 2.5 0 0 0 0 5M12 9s1.5-5.5 4-5.5a2.5 2.5 0 0 1 0 5" />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.6" />
    </svg>
  )
}

/**
 * שורת פעולה בהאב — אייקון, תווית ואזור מגע מלא.
 *
 * בכוונה בלי תת-שורה: התאריך ושם המקום כבר מופיעים בגוף הכרטיס, ושכפול
 * שלהם בתוך הכפתור רק מוסיף רעש למסך שכל כולו אמור להיקרא בשלוש שניות.
 */
function ActionRow({
  icon,
  label,
  onClick,
}: {
  icon: HubAction
  label: string
  onClick: () => void
}) {
  return (
    <button type="button" className="hub-action" onClick={onClick}>
      <span className="hub-action-icon">
        <ActionIcon name={icon} />
      </span>
      <span className="hub-action-text">
        <span className="hub-action-label">{label}</span>
      </span>
      <svg
        className="hub-action-chevron"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="m15 6-6 6 6 6" />
      </svg>
    </button>
  )
}

/**
 * מגירה תחתונה לבחירת יעד (יומן / ניווט).
 *
 * למה בורר ולא כפתור לכל אפשרות: שלושה כפתורי יומן ושלושה כפתורי ניווט על
 * מסך אחד הופכים את העמוד לרשימת קישורים. המוזמן מבין "הוספה ליומן",
 * ורק אחר כך צריך להחליט לאיזה.
 */
function ChoiceSheet({
  title,
  options,
  onClose,
}: {
  title: string
  options: { label: string; href: string; className?: string; download?: boolean }[]
  onClose: () => void
}) {
  const sheetRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // ממקדים את המגירה עצמה ולא את האפשרות הראשונה: קורא מסך מכריז על
    // הדיאלוג ועל שמו, ובמגע רגיל לא מודגשת אפשרות אחת כאילו כבר נבחרה.
    sheetRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="hub-sheet-backdrop" onClick={onClose}>
      <div
        className="hub-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={sheetRef}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="hub-sheet-grip" aria-hidden="true" />
        <div className="hub-sheet-title">{title}</div>
        {options.map((opt) => (
          <a
            key={opt.label}
            className={`hub-sheet-option ${opt.className || ''}`}
            href={opt.href}
            // ICS נפתח באותה לשונית בכוונה: זה מה שגורם ל-iOS להציג את מסך
            // "הוספה ליומן" במקום לפתוח חלון ריק.
            target={opt.download ? undefined : '_blank'}
            rel="noopener noreferrer"
            onClick={onClose}
          >
            {opt.label}
          </a>
        ))}
        <button type="button" className="hub-sheet-close" onClick={onClose}>
          {strings.guestHub.closeSheet}
        </button>
      </div>
    </div>
  )
}

/**
 * המרת קלט שקלים חופשי לאגורות — **בלי float בשום שלב**.
 *
 * "500" → 50000 · "500.5" → 50050 · "500.50" → 50050
 *
 * זו לא "חישוב כסף" אלא תרגום של מה שהמשתמש הקליד ליחידה שהשרת מצפה לה.
 * העמלה והסכום הכולל מחושבים אך ורק בשרת. הפירוק נעשה על המחרוזת ולא
 * דרך ``parseFloat`` בדיוק כדי שלא תיכנס שגיאת ייצוג בינארית.
 */
function shekelsToAgorot(text: string): number | null {
  const clean = text.trim().replace(/[,\s₪]/g, '')
  if (!clean || !/^\d+(\.\d{0,2})?$/.test(clean)) return null
  const [whole, fraction = ''] = clean.split('.')
  const agorot = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  return Number.isSafeInteger(agorot) && agorot > 0 ? agorot : null
}

/** הצגה בלבד: 52000 → "₪520" · 10450 → "₪104.50". */
function formatAgorot(agorot: number): string {
  const whole = Math.trunc(agorot / 100)
  const rest = agorot % 100
  const shown = whole.toLocaleString('he-IL')
  return rest ? `₪${shown}.${String(rest).padStart(2, '0')}` : `₪${shown}`
}

/** שורה בפירוט התשלום. ``strong`` שמורה לשורת הסה"כ. */
function GiftRow({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`hub-gift-row ${strong ? 'total' : ''}`}>
      <span className="hub-gift-row-label">{label}</span>
      <span className="hub-gift-row-value">{value}</span>
    </div>
  )
}

/**
 * אזור המתנה — הזנת סכום, שקיפות עמלה, ותשלום **מדומה**.
 *
 * שלוש החלטות שמעצבות את המסך הזה:
 *
 * 1. **אין סכומים מוכנים.** האורח מקליד כמה שהוא רוצה שהם יקבלו. סכומי
 *    מתנה בישראל אישיים מדי מכדי להציע "בחר 200/500/1000".
 * 2. **מה שמוקלד הוא מה שהם מקבלים.** העמלה מתווספת *מעל* ומוצגת
 *    במפורש באותו מסך — לא בשלב תשלום מאוחר. אורח שמגלה תוספת רק בסוף
 *    מרגיש שהוליכו אותו שולל, וזה בדיוק ההפך ממה ש-VEYA מוכרת.
 * 3. **השרת מחשב.** כל שינוי סכום שולח בקשת תמחור (מושהית ב-300ms),
 *    והמספרים המוצגים תמיד מגיעים משם.
 */
function GiftPanel({
  token,
  title,
  guestName,
  onClose,
}: {
  token: string
  title: string
  guestName: string
  onClose: () => void
}) {
  const hub = strings.guestHub
  const panelRef = useRef<HTMLDivElement>(null)

  const [amountText, setAmountText] = useState('')
  const [quote, setQuote] = useState<GiftQuote | null>(null)
  const [quoting, setQuoting] = useState(false)
  const [giver, setGiver] = useState(guestName)
  const [blessing, setBlessing] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState<'form' | 'checkout'>('form')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<GiftCheckoutResult | null>(null)
  const [attempt, setAttempt] = useState(0)

  const agorot = shekelsToAgorot(amountText)

  /**
   * מפתח מניעת-כפילות לניסיון התשלום הנוכחי.
   *
   * קבוע כל עוד מדובר באותו ניסיון — כך שלחיצה כפולה, או שליחה חוזרת אחרי
   * שהרשת "נתקעה", לא ייצרו שני חיובים (השרת יזהה ויחזיר את אותה עסקה).
   * משתנה כשהסכום משתנה או אחרי כישלון, כי אלה **ניסיונות אחרים** —
   * ועסקה שנכשלה היא סופית ולא מוחייאת.
   */
  const idempotencyKey = useMemo(
    () => `${token}:${agorot ?? 0}:${attempt}`,
    [token, agorot, attempt],
  )

  useEffect(() => {
    panelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // תמחור מהשרת בכל שינוי סכום. ההשהיה מונעת בקשה לכל הקשה, ו-``alive``
  // מונע מתשובה איטית של סכום ישן לדרוס תמחור חדש יותר.
  useEffect(() => {
    if (agorot === null) {
      setQuote(null)
      return
    }
    let alive = true
    setQuoting(true)
    const timer = window.setTimeout(() => {
      fetchGiftQuote(token, agorot)
        .then((q) => alive && setQuote(q))
        .catch((e) => {
          if (!alive) return
          setQuote(null)
          setError(e instanceof Error ? e.message : strings.errors.loadGenericRetry)
        })
        .finally(() => alive && setQuoting(false))
    }, 300)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [token, agorot])

  async function pay(simulate: 'success' | 'failure') {
    if (agorot === null) return
    setBusy(true)
    setError(null)
    try {
      setResult(
        await submitGiftCheckout(token, {
          gift_amount_agorot: agorot,
          giver_name: giver.trim(),
          blessing: blessing.trim() || null,
          simulate,
          idempotency_key: idempotencyKey,
        }),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : strings.errors.loadGenericRetry)
    } finally {
      setBusy(false)
    }
  }

  // מציגים פירוט **רק** אם הוא של הסכום שכרגע בשדה. בזמן שהתמחור החדש
  // בדרך, הסכום הישן כבר לא נכון — ומסך כסף שמראה סה"כ שלא תואם למה
  // שכתוב בשדה הוא בדיוק סוג הבלבול שאסור שיקרה כאן.
  const freshQuote = quote && quote.gift_amount_agorot === agorot ? quote : null
  const canContinue = agorot !== null && freshQuote !== null && !quoting

  return (
    <div className="hub-sheet-backdrop" onClick={onClose}>
      <div
        className="hub-sheet hub-gift"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="hub-sheet-grip" aria-hidden="true" />

        {/* סימון ההדמיה מופיע בכל שלב, לא רק במסך התשלום. */}
        <p className="hub-gift-mock-badge">{hub.giftMockBadge}</p>

        {result ? (
          <div className="hub-gift-done">
            <div className="hub-gift-title">
              {result.status === 'success' ? hub.giftSuccessTitle : hub.giftFailTitle}
            </div>
            <p className="hub-gift-body">
              {result.status === 'success'
                ? hub.giftSuccessBody(
                    formatAgorot(result.quote.total_agorot),
                    formatAgorot(result.quote.gift_amount_agorot),
                  )
                : result.message}
            </p>
            <p className="hub-gift-reference">{hub.giftReference(result.reference)}</p>
            {result.status === 'failure' ? (
              <button
                type="button"
                className="confirm-submit"
                onClick={() => {
                  // ניסיון חדש = עסקה חדשה. עסקה שנכשלה היא סופית.
                  setAttempt((n) => n + 1)
                  setResult(null)
                  setStage('form')
                }}
              >
                {hub.giftTryAgain}
              </button>
            ) : null}
            <button type="button" className="hub-sheet-close" onClick={onClose}>
              {hub.closeSheet}
            </button>
          </div>
        ) : stage === 'form' ? (
          <>
            <div className="hub-gift-title">{title}</div>

            <label className="hub-gift-field" htmlFor="gift-amount">
              <span className="hub-gift-label">{hub.giftAmountLabel}</span>
              <div className="hub-gift-amount-wrap">
                <span className="hub-gift-currency" aria-hidden="true">₪</span>
                <input
                  id="gift-amount"
                  className="hub-gift-amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  dir="ltr"
                  value={amountText}
                  placeholder={hub.giftAmountPlaceholder}
                  onChange={(e) => setAmountText(e.target.value)}
                  aria-describedby="gift-amount-hint gift-fee-explainer"
                />
              </div>
              <span className="hub-gift-hint" id="gift-amount-hint">
                {hub.giftAmountHint}
              </span>
            </label>

            {/* פירוט התשלום — תמיד גלוי כשיש סכום, אף פעם לא מוסתר לשלב הבא.
                aria-live כדי שקורא מסך יכריז על השינוי בסכום. */}
            <div className="hub-gift-breakdown" aria-live="polite">
              {freshQuote ? (
                <>
                  <GiftRow
                    label={hub.giftRowAmount}
                    value={formatAgorot(freshQuote.gift_amount_agorot)}
                  />
                  <GiftRow
                    label={hub.giftRowFee(freshQuote.fee_percent)}
                    value={formatAgorot(freshQuote.fee_agorot)}
                  />
                  <GiftRow
                    label={hub.giftRowTotal}
                    value={formatAgorot(freshQuote.total_agorot)}
                    strong
                  />
                </>
              ) : (
                <p className="hub-gift-hint">
                  {agorot !== null ? hub.giftCalculating : hub.giftAmountHint}
                </p>
              )}
            </div>

            <p className="hub-gift-explainer" id="gift-fee-explainer">
              {hub.giftFeeExplainer(freshQuote?.fee_percent ?? 4)}
            </p>

            <label className="hub-gift-field" htmlFor="gift-giver">
              <span className="hub-gift-label">{hub.giftGiverLabel}</span>
              <input
                id="gift-giver"
                className="hub-gift-input"
                type="text"
                value={giver}
                placeholder={hub.giftGiverPlaceholder}
                onChange={(e) => setGiver(e.target.value)}
              />
            </label>

            <label className="hub-gift-field" htmlFor="gift-blessing">
              <span className="hub-gift-label">{hub.giftBlessingLabel}</span>
              <textarea
                id="gift-blessing"
                className="hub-gift-input"
                rows={2}
                value={blessing}
                placeholder={hub.giftBlessingPlaceholder}
                onChange={(e) => setBlessing(e.target.value)}
              />
            </label>

            {error && (
              <div className="confirm-error" role="alert">
                {error}
              </div>
            )}

            <button
              type="button"
              className="confirm-submit"
              disabled={!canContinue}
              onClick={() => setStage('checkout')}
            >
              {hub.giftSubmit}
            </button>
            <button type="button" className="hub-sheet-close" onClick={onClose}>
              {hub.closeSheet}
            </button>
          </>
        ) : (
          <div className="hub-gift-checkout">
            <div className="hub-gift-title">{hub.giftRowTotal}</div>
            <div className="hub-gift-total-big">
              {freshQuote ? formatAgorot(freshQuote.total_agorot) : ''}
            </div>
            <p className="hub-gift-body">{hub.giftMockNotice}</p>

            {error && (
              <div className="confirm-error" role="alert">
                {error}
              </div>
            )}

            <button
              type="button"
              className="confirm-submit"
              disabled={busy}
              onClick={() => pay('success')}
            >
              {busy ? strings.common.working : hub.giftPayNow}
            </button>
            <button
              type="button"
              className="hub-gift-fail-btn"
              disabled={busy}
              onClick={() => pay('failure')}
            >
              {hub.giftPayFail}
            </button>
            <button type="button" className="hub-sheet-close" onClick={() => setStage('form')}>
              {hub.giftBack}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/** תצוגת ההזמנה במסך מלא — התמונה היא העיקר, אז נותנים לה את כל המסך. */
function InviteViewer({
  src,
  alt,
  onClose,
}: {
  src: string
  alt: string
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="hub-viewer" role="dialog" aria-modal="true" aria-label={alt}>
      <button
        type="button"
        className="hub-viewer-close"
        onClick={onClose}
        aria-label={strings.guestHub.closeInvite}
      >
        ✕
      </button>
      <img className="hub-viewer-img" src={src} alt={alt} />
      <p className="hub-viewer-hint">{strings.guestHub.inviteZoomHint}</p>
    </div>
  )
}

/** דף המוזמן הציבורי — נפתח דרך הקישור האישי /confirm/{token}, ללא התחברות. */
export function ConfirmPage({ token }: { token: string }) {
  const [data, setData] = useState<ConfirmGuestPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [choice, setChoice] = useState<Choice | null>(null)
  const [count, setCount] = useState(1)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  const [sheet, setSheet] = useState<'calendar' | 'navigation' | null>(null)
  const [viewingInvite, setViewingInvite] = useState(false)
  const [giftOpen, setGiftOpen] = useState(false)

  const hub = strings.guestHub

  useEffect(() => {
    let alive = true
    getConfirm(token)
      .then((d) => {
        if (!alive) return
        setData(d)
        // מצב התחלתי לפי תשובה קודמת (אם ענה כבר)
        if (d.rsvp_status === 'confirmed' || d.rsvp_status === 'declined' || d.rsvp_status === 'maybe') {
          setChoice(d.rsvp_status)
        }
        setCount(d.confirmed_count && d.confirmed_count > 0 ? d.confirmed_count : d.party_size)
        setNote(d.guest_note || '')

        // קישור ישיר לפעולה (?action=…) — **רק** אם השרת אמר שהיא זמינה.
        // זו הנקודה שבה הניתוב נבדק מול הזמינות: ?action=gift לפני חלון
        // שלושת הימים פשוט לא עושה כלום, כי d.actions.gift הוא false.
        const wanted = readActionParam()
        if (wanted && d.actions[wanted]) {
          if (wanted === 'invitation') setViewingInvite(true)
          else if (wanted === 'calendar') setSheet('calendar')
          else if (wanted === 'navigation') setSheet('navigation')
          else if (wanted === 'gift') setGiftOpen(true)
        }
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : strings.errors.confirmLoadFailed))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [token])

  const closeSheet = useCallback(() => setSheet(null), [])

  // נעילת גלילה כשמשהו פתוח מעל העמוד. בלי זה, החלקה על המגירה או על
  // ההזמנה במסך מלא מגלגלת את העמוד שמאחור — תחושה שבורה במיוחד בטלפון,
  // שם הרפלקס הראשון הוא להחליק.
  const overlayOpen = sheet !== null || viewingInvite || giftOpen
  useEffect(() => {
    if (!overlayOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [overlayOpen])

  const calendarOptions = useMemo(() => {
    const cal = data?.event.calendar
    if (!cal) return []
    return [
      { label: hub.calendarApple, href: confirmIcsUrl(cal.ics), download: true },
      { label: hub.calendarGoogle, href: cal.google },
      { label: hub.calendarOutlook, href: cal.outlook },
    ].filter((o) => o.href)
  }, [data, hub])

  const navOptions = useMemo(() => {
    const ev = data?.event
    if (!ev) return []
    return [
      { label: hub.navWaze, href: ev.waze_link, className: 'waze' },
      { label: hub.navGoogleMaps, href: ev.maps_link },
      { label: hub.navAppleMaps, href: ev.apple_maps_link },
    ].filter((o) => o.href)
  }, [data, hub])

  async function send() {
    if (!choice) return
    setBusy(true)
    setError(null)
    try {
      const res = await submitConfirm(token, {
        coming: choice === 'confirmed',
        maybe: choice === 'maybe',
        count: choice === 'confirmed' ? count : null,
        note: note.trim() || null,
      })
      setData(res)
      setSent(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : strings.errors.confirmSubmitFailed)
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="confirm-wrap" dir="rtl">
        <div className="confirm-card confirm-center">{strings.common.loading}</div>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="confirm-wrap" dir="rtl">
        <div className="confirm-card confirm-center">
          <Monogram />
          <h1 className="confirm-title">הקישור אינו תקין</h1>
          <p className="confirm-sub">{error}</p>
        </div>
      </div>
    )
  }

  const guest = data!
  const ev = guest.event
  const acts = guest.actions
  const terms = getEventTerms(ev.event_type)
  const hosts = [ev.groom_name, ev.bride_name].filter(Boolean).join(' ו')
  const couple = hosts || terms.defaultTitle
  const firstName = guest.full_name.trim().split(/\s+/)[0] || ''
  const when = whenText(ev.event_date, ev.event_time)
  const inviteSrc = ev.invite_image ? mediaUrl(ev.invite_image) : ''
  const inviteAlt = `${terms.inviteLabel} של ${couple}`

  // מסך התודה אחרי שליחה — אותן פעולות בדיוק נשארות זמינות, כי מוזמן שאישר
  // הגעה הוא בדיוק מי שעכשיו רוצה להוסיף ליומן ולשמור ניווט.
  const answered =
    sent && (guest.rsvp_status === 'confirmed' || guest.rsvp_status === 'maybe' || guest.rsvp_status === 'declined')
  const thankYou = !answered
    ? ''
    : guest.rsvp_status === 'confirmed'
      ? `נתראה ב${terms.celebration}! שמרנו ${
          guest.confirmed_count === 1 ? 'מקום אחד' : `${guest.confirmed_count} מקומות`
        }.`
      : guest.rsvp_status === 'maybe'
        ? 'סימנו "עוד לא החלטנו". נשמח לעדכון כשתדעו.'
        : 'תודה שעדכנתם. נחגוג לחייכם!'

  return (
    <div className="confirm-wrap" dir="rtl">
      <div className={`confirm-card hub-card ${inviteSrc ? 'has-invite' : ''}`}>
        <div className="confirm-brand">
          <Monogram />
          <div className="confirm-brand-name">VEYA</div>
        </div>

        <header className="hub-header">
          <p className="hub-greeting">{hub.greeting(firstName)}</p>
          <p className="hub-tagline">{hub.tagline}</p>
        </header>

        {/* ---- מי, מתי, איפה ---- */}
        {inviteSrc ? (
          <button
            type="button"
            className="hub-invite-preview"
            onClick={() => setViewingInvite(true)}
            aria-label={hub.viewInvite}
          >
            {/* התמונה מכילה כבר את השמות והפרטים — היא הכותרת האמיתית */}
            <img className="confirm-invite-img" src={inviteSrc} alt={inviteAlt} />
          </button>
        ) : (
          <h1 className="hub-title">{ev.title || terms.celebrationOf(couple)}</h1>
        )}

        <div className="hub-details">
          {when && <span className="hub-when">{when}</span>}
          {ev.venue_name && <span className="hub-venue">{ev.venue_name}</span>}
          {ev.venue_address && <span className="hub-address">{ev.venue_address}</span>}
        </div>

        {/* ---- הפעולות ---- */}
        {(acts.invitation || acts.calendar || acts.navigation || acts.gift) && (
          <div className="hub-actions">
            {acts.invitation && inviteSrc && (
              <ActionRow
                icon="invitation"
                label={hub.viewInvite}
                onClick={() => setViewingInvite(true)}
              />
            )}
            {acts.calendar && calendarOptions.length > 0 && (
              <ActionRow
                icon="calendar"
                label={hub.addToCalendar}
                onClick={() => setSheet('calendar')}
              />
            )}
            {acts.navigation && navOptions.length > 0 && (
              <ActionRow
                icon="navigation"
                label={hub.navigate}
                onClick={() => setSheet('navigation')}
              />
            )}
            {/* נדלקת לבדה 3 ימים לפני האירוע — השרת מחליט, לא העמוד. */}
            {acts.gift && (
              <ActionRow
                icon="gift"
                label={terms.giftLabel}
                onClick={() => setGiftOpen(true)}
              />
            )}
          </div>
        )}

        {/* ---- אישור הגעה (המנגנון הקיים, בלי שינוי בלוגיקה) ---- */}
        {acts.rsvp && (
          <div className="hub-rsvp">
            {answered ? (
              <div className="hub-answered">
                <p className="confirm-thankyou">{thankYou}</p>
                <button className="confirm-change" onClick={() => setSent(false)}>
                  שינוי התשובה
                </button>
              </div>
            ) : (
              <>
                <div className="confirm-question">נשמח לדעת — תגיעו לחגוג איתנו?</div>

                <div className="confirm-choices">
                  <button
                    type="button"
                    className={`confirm-choice yes ${choice === 'confirmed' ? 'active' : ''}`}
                    aria-pressed={choice === 'confirmed'}
                    onClick={() => setChoice('confirmed')}
                  >
                    ✓ מגיעים
                  </button>
                  <button
                    type="button"
                    className={`confirm-choice maybe ${choice === 'maybe' ? 'active' : ''}`}
                    aria-pressed={choice === 'maybe'}
                    onClick={() => setChoice('maybe')}
                  >
                    ? אולי
                  </button>
                  <button
                    type="button"
                    className={`confirm-choice no ${choice === 'declined' ? 'active' : ''}`}
                    aria-pressed={choice === 'declined'}
                    onClick={() => setChoice('declined')}
                  >
                    ✕ לא נגיע
                  </button>
                </div>

                {choice === 'confirmed' && (
                  <div className="confirm-count">
                    <label>כמה מכם מגיעים?</label>
                    <div className="confirm-stepper">
                      <button
                        type="button"
                        className="confirm-step"
                        aria-label="הפחתת מוזמן"
                        disabled={count <= 1}
                        onClick={() => setCount((c) => Math.max(1, c - 1))}
                      >
                        −
                      </button>
                      <span className="confirm-step-num" aria-live="polite">
                        {count}
                      </span>
                      <button
                        type="button"
                        className="confirm-step"
                        aria-label="הוספת מוזמן"
                        disabled={count >= 30}
                        onClick={() => setCount((c) => Math.min(30, c + 1))}
                      >
                        +
                      </button>
                    </div>
                  </div>
                )}

                {choice && choice !== 'declined' && (
                  <div className="confirm-note">
                    <label htmlFor="confirm-note-field">הערה (לא חובה)</label>
                    <textarea
                      id="confirm-note-field"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="לדוגמה: צריך נגישות, יש לנו תינוק, אלרגיה…"
                      rows={2}
                    />
                  </div>
                )}

                {error && (
                  <div className="confirm-error" role="alert">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  className="confirm-submit"
                  disabled={!choice || busy}
                  onClick={send}
                >
                  {busy ? 'שולח…' : 'שליחת אישור'}
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {sheet === 'calendar' && (
        <ChoiceSheet title={hub.calendarPickTitle} options={calendarOptions} onClose={closeSheet} />
      )}
      {sheet === 'navigation' && (
        <ChoiceSheet title={hub.navPickTitle} options={navOptions} onClose={closeSheet} />
      )}
      {viewingInvite && inviteSrc && (
        <InviteViewer src={inviteSrc} alt={inviteAlt} onClose={() => setViewingInvite(false)} />
      )}
      {/* התנאי כולל שוב את acts.gift בכוונה: גם אם מצב הפתיחה נדלק איכשהו,
          בלי אישור מהשרת שום דבר לא מוצג. */}
      {giftOpen && acts.gift && (
        <GiftPanel
          token={token}
          title={terms.giftLabel}
          guestName={guest.full_name}
          onClose={() => setGiftOpen(false)}
        />
      )}
    </div>
  )
}
