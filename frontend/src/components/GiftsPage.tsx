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
 *   1. **סה״כ שהתקבל** — עובדה אחת גדולה, **בלי כרטיס**: המספר יושב
 *      ישירות על רקע העמוד. כך הוא נקרא כמותג ולא כשדה בטופס, והמסך
 *      מקבל נשימה לפני הכרטיס שמתחתיו. מתחתיו שורה אחת שמפרטת את
 *      המצבים, כדי שההפרש בין הסכום לבין אורך הרשימה לא יישאר חידה.
 *   2. **פרטי קבלת מתנות** — המצב ולאן הכסף יגיע. כרטיס אחד
 *      (``PayoutDetails``) שמחזיק גם את הסטטוס וגם את הפרטים, עם פעולה
 *      ראשית אחת.
 *   3. **המתנות שהתקבלו** — מי בירך, כמה ומה כתב.
 *
 * **למה הסכום ראשון ולא כרטיס הפרטים.** במסך כספי המספר הוא הדבר הראשון
 * שהעין צריכה להבין. כרטיס הפרטים גבוה, וברוב חייו של האירוע הוא כבר
 * מאושר ולא דורש דבר — כלומר בטלפון הוא דחף את המספר החשוב ביותר במסך
 * אל מתחת לקיפול. באירוע שעוד לא קיבל מתנות אזור הסכום אינו מרונדר
 * כלל, ולכן במצב שבו *כן* צריך לפעול הכרטיס חוזר להיות ראשון מאליו.
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

/** ₪1 = 100 אגורות. הצגה בלבד — כל חשבון הכסף כבר בוצע בשרת.
 *
 *  סדר הכתיבה: **המספר ואז הסימן, עם רווח** — "3,900 ₪". זה הכתיב
 *  הישראלי (``hebrew-writing-rules.md``); "₪3,900" הוא סדר אנגלי
 *  שנראה כמו תרגום. הרווח הוא רווח דק שאינו נשבר (U+202F), כדי
 *  שהסימן לעולם לא ייפול לשורה נפרדת מהמספר. */
function formatAgorot(agorot: number): string {
  const whole = Math.trunc(agorot / 100)
  const rest = agorot % 100
  const shown = whole.toLocaleString('he-IL')
  const value = rest ? `${shown}.${String(rest).padStart(2, '0')}` : shown
  return `${value}\u202f₪`
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
  // שנה מלאה, כמו בכל שאר המערכת ("18.11.2026"). שנתיים ספרות חסכו
  // מעט מקום אבל יצרו פורמט תאריך שני במוצר שיש בו כבר אחד.
  return `${dd}.${mm}.${d.getFullYear()}`
}

/**
 * "9 מתנות התקבלו · 2 ממתינות · אחת נכשלה" — שורה אחת מתחת לסכום.
 *
 * הסיבה שהיא קיימת: הסכום הגדול נספר בשרת **מ-``paid`` בלבד**, ומתחתיו
 * מופיעה רשימה שכוללת גם עסקאות שנכשלו, בוטלו, הוחזרו או עדיין ממתינות.
 * בלי השורה הזו הזוג רואה שלוש-עשרה שורות מעל סכום שמייצג תשע מהן, ואין
 * לו שום דרך לדעת למה — וזו בדיוק השאלה שאסור להשאיר פתוחה במסך כספי.
 *
 * **זו ספירה, לא חישוב.** אלה בדיוק אותן שורות שמוצגות מיד מתחת, נספרות
 * לפי השדה ``status`` שהשרת החזיר. סכומים לפי מצב **אינם** מחושבים כאן:
 * את הכסף סופר השרת, ומקור אמת כספי שני באותו מסך הוא בדיוק מה שגורם
 * לשני מספרים לסטות זה מזה.
 */
const STATUS_ORDER = ['pending', 'failed', 'cancelled', 'refunded'] as const

function StatusCounts({ data, includePaid = true }: { data: GiftsSummary; includePaid?: boolean }) {
  const parts: string[] = []
  // "התקבלו" מגיע מ-``paid_count`` של השרת ולא מספירה מקומית — אותו מקור
  // בדיוק שממנו חושב הסכום שמעליו, כדי ששני המספרים לא יוכלו לסטות.
  // כשהסכומים נעולים, **הגיבור עצמו הוא המניין הזה** ולכן הוא יורד מכאן:
  // אחרת אותו מספר היה מופיע פעמיים, אחד מתחת לשני.
  if (includePaid && data.paid_count > 0) parts.push(t.statusCounts.paid(data.paid_count))
  for (const status of STATUS_ORDER) {
    const n = data.gifts.filter((g) => g.status === status).length
    if (n > 0) parts.push(t.statusCounts[status](n))
  }
  if (!parts.length) return null
  return <p className="gifts-total-sub">{parts.join(' · ')}</p>
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
          // ``role="img"`` ולא span עירום: ל-``span`` יש role גנרי, שאינו
          // תומך במתן שם — ולכן ``aria-label`` עליו עלול פשוט להיעלם, וקורא
          // מסך היה מקריא שלוש נקודות בלי שום הסבר. עם role שתומך בשם,
          // התא נקרא "הסכום יוצג אחרי אישור פרטי קבלת המתנות".
          <span
            className="gift-amount-hidden"
            role="img"
            title={t.amountHiddenLabel}
            aria-label={t.amountHiddenLabel}
          >
            •••
          </span>
        ) : (
          formatAgorot(gift.gift_amount_agorot)
        )}
      </span>
      {/* אין ברכה — התא נשאר ריק. המקף שהיה כאן קודם היה טקסט דקורטיבי
          ב-``--faint`` (3.24:1), כלומר סימן שנראה חלש יותר מהברכות שלצידו
          ומוסיף רעש לעמודה שרובה ממילא ריקה. במובייל הוא כבר הוסתר. */}
      <span className="gift-cell-blessing">
        {gift.message ? <q>{gift.message}</q> : null}
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
          {/* מעוצב כאן ולא נלקח מ-``total_received_display`` של השרת:
              השרת מחזיר "₪1,240" (סדר אנגלי), ואילו שורות המתנות עוברות
              דרך ``formatAgorot`` המקומי. שתי נוסחאות באותו מסך פירושן
              שהסכום הגדול והסכומים שמתחתיו כתובים אחרת. הסכום עצמו מגיע
              מהשרת — רק העיצוב שלו מקומי. */}
          <span className="gifts-total-figure">
            {formatAgorot(data.total_received_agorot ?? 0)}
          </span>
        </p>
        <StatusCounts data={data} />
      </section>
    )
  }
  // התווית משתנה יחד עם הערך: מתחת ל"סה״כ שהתקבל" חייב לעמוד סכום כסף,
  // ולא מספר מתנות — אחרת המסך נראה כאילו טעה.
  return (
    <section className="gifts-total" aria-label={t.countOnlyLabel}>
      <p className="gifts-total-label">{t.countOnlyLabel}</p>
      <p className="gifts-total-value gifts-total-value-count">{data.paid_count}</p>
      <StatusCounts data={data} includePaid={false} />
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

  // מונה ניסיונות — כפתור "ניסיון חוזר" מגדיל אותו, וה-effect רץ מחדש.
  // עדיף על חילוץ הטעינה לפונקציה: כך יש **מסלול טעינה אחד בלבד**, עם
  // אותו ניקוי (``alive``) שמונע כתיבה אחרי שהרכיב ירד.
  const [attempt, setAttempt] = useState(0)

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
  }, [attempt])

  /**
   * חשבון עודכן (נשמר או הוגש) — ולכן ייתכן שגם השער נפתח או נסגר.
   * טוענים מחדש את המתנות כדי שהסכומים במסך יתאימו למצב האמיתי בשרת,
   * ולא רק לחשבון החדש.
   */
  const handleAccountChange = useCallback((next: PayoutAccount) => {
    setAccount(next)
    getGifts().then(setData).catch(() => undefined)
  }, [])

  // אותם דפוסים כמו בשאר המערכת (.load-text / .form-error) ולא מחלקות
  // ייעודיות למסך אחד: מצב טעינה ומצב שגיאה צריכים להיראות זהה בכל מקום.
  if (loading) return <p className="load-text">{strings.common.loading}</p>
  // הודעת השגיאה **תמיד עוברת דרך ``api.ts``**, שכבר ממיר 5xx להודעה
  // ידידותית ולעולם לא מעביר גוף תשובה גולמי — ולכן אין כאן טקסט טכני.
  // מה שכן היה חסר: מוצא. "ננסה שוב" בלי כפתור משאיר את הזוג עם רענון
  // הדף כאפשרות היחידה.
  if (error) {
    return (
      <div className="gifts-page">
        <p className="form-error" role="alert">{error}</p>
        <div className="empty-actions">
          <button type="button" className="btn-ghost" onClick={() => setAttempt((n) => n + 1)}>
            {strings.common.retry}
          </button>
        </div>
      </div>
    )
  }
  if (!data) return null

  return (
    <div className="gifts-page">
      {/* 1. כמה התקבל — ללא כרטיס, ישירות על רקע העמוד.
             **ראשון במסך.** במסך כספי הסכום הוא הדבר הראשון שהעין צריכה
             להבין; קודם הוא ישב מתחת לכרטיס פרטי החשבון, ובטלפון זה אומר
             שהמספר החשוב ביותר במסך היה מתחת לקיפול, אחרי כרטיס עיון שברוב
             הזמן לא דורש כלום.

             באירוע שעוד לא קיבל אף מתנה האזור הזה **לא מוצג בכלל** — ולכן
             במצב "עוד לא התחלנו" הכרטיס שמתחתיו חוזר להיות הדבר הראשון,
             עם הפעולה שבו. "₪0" מעל מצב-ריק שאומר "עדיין לא התקבלו מתנות"
             הוא אותה בשורה פעמיים, ואף אחת מהן לא מוסיפה. */}
      {data.total_count > 0 && <TotalReceived data={data} />}

      {/* 2. פרטי קבלת מתנות — מצב + פרטים + פעולה אחת, בכרטיס אחד.
             כשהסכומים נעולים, המשפט שמעליו ("הסכומים יופיעו כאן ברגע
             שפרטי קבלת המתנות יאושרו") מצביע ישירות על הכרטיס הזה —
             כלומר ההסבר בא לפני הפעולה, ולא אחריה. */}
      {payoutVisible && (
        <PayoutDetails account={account} onChange={handleAccountChange} />
      )}

      {/* 3. מי בירך ובכמה. */}
      <section className="gifts-log" aria-labelledby="gifts-log-title">
        <h2 className="gifts-log-title" id="gifts-log-title">{t.logTitle}</h2>

        {data.gifts.length === 0 ? (
          // ``.empty`` ולא מחלקה ייעודית למסך אחד: זה דפוס המצב-הריק של
          // המערכת (כותרת + הסבר), ו-``.gifts-empty`` היה שכפול שלו עם
          // ערכים אחרים. מצב ריק צריך להיראות זהה בכל מסך.
          // המצב הריק יושב על **אותו משטח** שעליו תשב הרשימה. בלי הכרטיס
          // האזור מתמוטט לטקסט מרחף מתחת לכותרת, והמסך "קופץ" ברגע שמגיעה
          // המתנה הראשונה.
          <div className="gifts-card gifts-card-empty">
            <div className="empty">
              <p className="empty-title">{t.emptyTitle}</p>
              {/* לפני שהחשבון מאומת השירות פשוט **סגור למוזמנים**
                  (``gift_eligibility.is_active``), ולכן "עוד לא שלחו" אינו
                  הסבר נכון — אי אפשר היה לשלוח.

                  המקור הוא ``amounts_visible`` ולא ``account.fully_verified``:
                  זה בדיוק אותו תנאי שרת שפותח את השירות למוזמנים, והוא מגיע
                  גם למי שאינו רשאי לראות את חשבון הבנק (מפיק/אולם), שאצלו
                  ``account`` הוא ``null`` תמיד. */}
              <p className="empty-desc">
                {data.amounts_visible ? t.emptyBodyActive : t.emptyBodyPending}
              </p>
            </div>
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
