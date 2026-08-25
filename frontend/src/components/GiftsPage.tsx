import { useCallback, useEffect, useState } from 'react'
import { getGifts, getPayoutAccount } from '../api'
import type { GiftRow, GiftsSummary, PayoutAccount } from '../types'
import { strings } from '../strings/he'
import { PayoutDetails } from './PayoutDetails'
import './GiftsPage.css'

const t = strings.gifts

/**
 * מסך "מתנות באשראי" לבעלי האירוע — קריאה בלבד.
 *
 * שלושה אזורים, בסדר הזה — וזה גם סדר החשיבות:
 *
 *   1. **פרטי קבלת מתנות** — המצב ולאן הכסף יגיע. כרטיס אחד
 *      (``PayoutDetails``) שמחזיק גם את הסטטוס וגם את הפרטים, עם פעולה
 *      ראשית אחת. ראשון, כי הוא היחיד שעשוי לדרוש משהו מהזוג.
 *   2. **סה״כ שהתקבל** — עובדה אחת גדולה, **בלי כרטיס**: המספר יושב
 *      ישירות על רקע העמוד. כך הוא נקרא כמותג ולא כשדה בטופס, והמסך
 *      מקבל נשימה בין שני הכרטיסים.
 *   3. **המתנות שהתקבלו** — מי בירך, כמה ומה כתב.
 *
 * באופיו הוא קרוב ל"יומן פעילות" ולא ללוח בקרה: שורות מופרדות בקו שיער,
 * טיפוגרפיה רגועה. הזוג בא לכאן לראות מי בירך ובכמה, לא לנתח נתונים.
 *
 * **מה שבמפורש לא מוצג כאן: עמלת השירות.** היא עניין שבין VEYA לנותן
 * המתנה — הוא משלם אותה ורואה אותה במלואה במסך שלו לפני התשלום. לבעלי
 * האירוע מוצג רק מה שהם מקבלים.
 *
 * **והסכומים אינם החלטה של המסך הזה.** כל עוד חשבון קבלת המתנות לא עבר
 * את שתי הבדיקות, השרת לא מחזיר אותם בכלל (``amounts_visible``). המסך רק
 * מציג את מה שקיבל, ומסביר בבאנר למה חסר.
 */

/** ₪1 = 100 אגורות. הצגה בלבד — כל חשבון הכסף כבר בוצע בשרת. */
function formatAgorot(agorot: number): string {
  const whole = Math.trunc(agorot / 100)
  const rest = agorot % 100
  const shown = whole.toLocaleString('he-IL')
  return rest ? `₪${shown}.${String(rest).padStart(2, '0')}` : `₪${shown}`
}

/** "24.08.26" — קצר ועדין, לא משפט שלם.
 *
 * ה-Backend מחזיר UTC נאיבי (בלי Z), ולכן מסמנים זאת במפורש — אחרת
 * הדפדפן קורא את המחרוזת כזמן מקומי והתאריך יכול לקפוץ ביום שלם.
 * אותו טיפול בדיוק כמו ב-ActivityLog.
 */
function formatDate(iso: string): string {
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (isNaN(d.getTime())) return ''
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const yy = String(d.getFullYear()).slice(-2)
  return `${dd}.${mm}.${yy}`
}

/** תג סטטוס — ברור אך לא צעקני. */
function StatusBadge({ status }: { status: GiftRow['status'] }) {
  return (
    <span className={`gift-status gift-status-${status}`}>
      {t.statusLabels[status] ?? status}
    </span>
  )
}

function GiftListRow({ gift }: { gift: GiftRow }) {
  return (
    <li className="gift-row">
      <span className="gift-cell-name">{gift.sender_name || t.anonymousGiver}</span>
      <span className="gift-cell-amount">
        {gift.gift_amount_agorot === null ? (
          // הסכום לא הגיע מהשרת. שלוש נקודות ולא "0" או שדה ריק: הכסף
          // קיים, הוא פשוט עוד לא מוצג — והמשפט המלא נמצא בבאנר למעלה.
          <span
            className="gift-amount-hidden"
            title={t.amountHiddenLabel}
            aria-label={t.amountHiddenLabel}
          >
            •••
          </span>
        ) : (
          formatAgorot(gift.gift_amount_agorot)
        )}
      </span>
      <span className="gift-cell-blessing">
        {gift.message ? <q>{gift.message}</q> : <span aria-hidden="true">—</span>}
      </span>
      <span className="gift-cell-date">{formatDate(gift.created_at)}</span>
      <span className="gift-cell-status">
        <StatusBadge status={gift.status} />
      </span>
    </li>
  )
}

/**
 * הסכום שהתקבל — **אזור ולא כרטיס.**
 *
 * זו העובדה היחידה במסך שראויה לגודל, ולכן היא מקבלת אותו בלי מסגרת,
 * בלי רקע ובלי צל: טיפוגרפיה על רקע העמוד. מסגרת סביב מספר בודד רק
 * הייתה מקטינה אותו ומוסיפה עוד כרטיס למסך שכבר יש בו שניים.
 *
 * כשהסכומים סגורים — **הספירה הופכת לגיבור** במקום מקום ריק או "₪0"
 * מטעה, ומתחתיה משפט אחד שמסביר בעדינות מה חסר. אותה היררכיה בדיוק,
 * רק עם נתון אחר במרכז.
 */
function TotalReceived({ data }: { data: GiftsSummary }) {
  if (data.amounts_visible) {
    return (
      <section className="gifts-total" aria-label={t.totalReceivedLabel}>
        <p className="gifts-total-label">{t.totalReceivedLabel}</p>
        <p className="gifts-total-value">
          {/* ה-LTR חל על **המספר בלבד**, לא על הפסקה. אחרת "₪2,180" היה
              נכון בסדר התווים אבל הפסקה כולה הייתה נצמדת לשמאל ויוצאת
              מיישור עם התווית שמעליה והשורה שמתחתיה. */}
          <span className="gifts-total-figure">{data.total_received_display}</span>
        </p>
        <p className="gifts-total-sub">{t.giftsCount(data.paid_count)}</p>
      </section>
    )
  }
  // התווית משתנה יחד עם הערך: מתחת ל"סה״כ שהתקבל" חייב לעמוד סכום כסף,
  // ולא מספר מתנות — אחרת המסך נראה כאילו טעה.
  return (
    <section className="gifts-total" aria-label={t.countOnlyLabel}>
      <p className="gifts-total-label">{t.countOnlyLabel}</p>
      <p className="gifts-total-value gifts-total-value-count">{data.paid_count}</p>
      <p className="gifts-total-sub gifts-total-locked">{t.amountsLockedNote}</p>
    </section>
  )
}

export function GiftsPage() {
  const [data, setData] = useState<GiftsSummary | null>(null)
  const [account, setAccount] = useState<PayoutAccount | null>(null)
  // האם למשתמש הזה יש בכלל גישה לפרטי קבלת המתנות. חבר-אירוע (מפיק/אולם)
  // עם הרשאת צפייה במתנות **אינו** רואה את חשבון הבנק של הזוג — הנתיב
  // סגור לבעלים בלבד — ולכן אצלו הבאנר וכרטיס הפרטים פשוט לא קיימים.
  const [payoutVisible, setPayoutVisible] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    // שתי הקריאות במקביל: טעינה טורית הייתה מכפילה את זמן ההמתנה בלי סיבה.
    //
    // כישלון של ``/payout`` **אינו** מפיל את המסך: הנתיב פתוח לבעלים בלבד,
    // ומפיק שרואה מתנות יקבל בו 403 באופן תקין לגמרי. במקרה כזה המסך מציג
    // את המתנות בלי אזור הפרטים — ולא הודעת שגיאה על משהו שלא היה אמור
    // להיות שלו מלכתחילה.
    Promise.all([getGifts(), getPayoutAccount().then((p) => p, () => null)])
      .then(([gifts, payout]) => {
        if (!alive) return
        setData(gifts)
        setAccount(payout)
        setPayoutVisible(payout !== null)
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : t.loadError))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  /**
   * חשבון עודכן (נשמר או הוגש) — ולכן ייתכן שגם השער נפתח או נסגר.
   * טוענים מחדש את המתנות כדי שהסכומים במסך יתאימו למצב האמיתי בשרת,
   * ולא רק לחשבון החדש.
   */
  const handleAccountChange = useCallback((next: PayoutAccount) => {
    setAccount(next)
    getGifts().then(setData).catch(() => undefined)
  }, [])

  if (loading) return <div className="gifts-state">{strings.common.loading}</div>
  if (error) return <div className="gifts-state gifts-state-error">{error}</div>
  if (!data) return null

  return (
    <div className="gifts-page">
      {/* 1. פרטי קבלת מתנות — מצב + פרטים + פעולה אחת, בכרטיס אחד.
             ראשון במסך כי הוא היחיד שעשוי לדרוש משהו מהזוג. */}
      {payoutVisible && (
        <PayoutDetails account={account} onChange={handleAccountChange} />
      )}

      {/* 2. כמה התקבל — ללא כרטיס, ישירות על רקע העמוד.
             באירוע שעוד לא קיבל אף מתנה האזור הזה **לא מוצג בכלל**: "₪0"
             או "0 מתנות" מעל מצב-ריק שאומר "עדיין לא התקבלו מתנות" הוא
             אותה בשורה שלוש פעמים, ואף אחת מהן לא מוסיפה. */}
      {data.total_count > 0 && <TotalReceived data={data} />}

      {/* 3. מי בירך ובכמה. */}
      <section className="gifts-log" aria-labelledby="gifts-log-title">
        <h2 className="gifts-log-title" id="gifts-log-title">{t.logTitle}</h2>

        {data.gifts.length === 0 ? (
          <div className="gifts-empty">
            <p className="gifts-empty-title">{t.emptyTitle}</p>
            <p className="gifts-empty-body">{t.emptyBody}</p>
          </div>
        ) : (
          <div className="gifts-card">
            {/* כותרות עמודות — בדסקטופ בלבד. במובייל כל מתנה היא כרטיס
                שקורא את עצמו, ולכן שורת כותרות רק הייתה מוסיפה רעש. */}
            <div className="gift-head" aria-hidden="true">
              <span>{t.colGuest}</span>
              <span>{t.colAmount}</span>
              <span>{t.colBlessing}</span>
              <span>{t.colDate}</span>
              <span>{t.colStatus}</span>
            </div>
            <ul className="gift-list">
              {data.gifts.map((g) => (
                <GiftListRow key={g.id} gift={g} />
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  )
}
