import { useEffect, useState } from 'react'
import { getConfirm, mediaUrl, submitConfirm } from '../api'
import type { ConfirmGuestPublic } from '../types'

type Choice = 'confirmed' | 'declined' | 'maybe'

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

/** כפתורי ניווט לאולם (Waze + Google Maps) — מוצגים רק כשיש כתובת. */
function NavButtons({ mapsLink, wazeLink }: { mapsLink: string; wazeLink: string }) {
  if (!mapsLink && !wazeLink) return null
  return (
    <div className="confirm-nav">
      {wazeLink && (
        <a className="confirm-nav-btn waze" href={wazeLink} target="_blank" rel="noopener noreferrer">
          ניווט ב-Waze
        </a>
      )}
      {mapsLink && (
        <a className="confirm-nav-btn maps" href={mapsLink} target="_blank" rel="noopener noreferrer">
          ניווט ב-Google Maps
        </a>
      )}
    </div>
  )
}

/** דף אישור הגעה ציבורי — נפתח דרך הקישור האישי /confirm/{token}, ללא התחברות. */
export function ConfirmPage({ token }: { token: string }) {
  const [data, setData] = useState<ConfirmGuestPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [choice, setChoice] = useState<Choice | null>(null)
  const [count, setCount] = useState(1)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<ConfirmGuestPublic | null>(null)

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
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'לא הצלחנו לטעון את ההזמנה. נסו לרענן את הדף.'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [token])

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
      setDone(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'לא הצלחנו לשלוח את התשובה. נסו שוב.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="confirm-wrap" dir="rtl">
        <div className="confirm-card confirm-center">טוען…</div>
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

  const ev = data!.event
  const couple = [ev.groom_name, ev.bride_name].filter(Boolean).join(' ו')

  // מסך תודה אחרי שליחה
  if (done) {
    const guests =
      done.confirmed_count === 1 ? 'אורח אחד' : `${done.confirmed_count} אורחים`
    const msg =
      done.rsvp_status === 'confirmed'
        ? `נהדר! נתראה באירוע 🎉 (${guests})`
        : done.rsvp_status === 'maybe'
          ? 'תודה! סימנו "אולי" — נשמח לעדכון סופי בהמשך.'
          : 'תודה שעדכנתם. חבל שלא תגיעו — נחגוג לחיים!'
    return (
      <div className="confirm-wrap" dir="rtl">
        <div className="confirm-card confirm-center">
          <Monogram />
          <h1 className="confirm-title">{couple}</h1>
          <p className="confirm-thankyou">{msg}</p>
          <button className="confirm-change" onClick={() => setDone(null)}>
            שינוי התשובה
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="confirm-wrap" dir="rtl">
      <div className={`confirm-card ${ev.invite_image ? 'has-invite' : ''}`}>
        <div className="confirm-brand">
          <Monogram />
          <div className="confirm-brand-name">VEYA</div>
        </div>

        <p className="confirm-hello">היי {data!.full_name}, שמחים שהגעתם 💛</p>

        {ev.invite_image ? (
          <>
            {/* תמונת ההזמנה היא הכוכבת — היא מכילה את שמות בני הזוג והפרטים */}
            <img
              className="confirm-invite-img"
              src={mediaUrl(ev.invite_image)}
              alt={`הזמנה לחתונה של ${couple}`}
            />
            <div className="confirm-caption">
              {ev.venue_name && (
                <span className="confirm-venue">{ev.venue_name}</span>
              )}
              {whenText(ev.event_date, ev.event_time) && (
                <span className="confirm-when">
                  {whenText(ev.event_date, ev.event_time)}
                </span>
              )}
              {ev.venue_address && (
                <span className="confirm-address">{ev.venue_address}</span>
              )}
            </div>
            <NavButtons mapsLink={ev.maps_link} wazeLink={ev.waze_link} />
          </>
        ) : (
          <>
            <h1 className="confirm-title">בשמחה רבה מזמינים אתכם לחגוג איתנו</h1>
            <div className="confirm-couple">{couple}</div>
            {ev.venue_name && <div className="confirm-venue">{ev.venue_name}</div>}
            {whenText(ev.event_date, ev.event_time) && (
              <div className="confirm-when">
                {whenText(ev.event_date, ev.event_time)}
              </div>
            )}
            {ev.venue_address && (
              <div className="confirm-address">{ev.venue_address}</div>
            )}
            <NavButtons mapsLink={ev.maps_link} wazeLink={ev.waze_link} />
          </>
        )}

        <div className="confirm-question">נשמח לדעת — תגיעו לחגוג איתנו?</div>

        <div className="confirm-choices">
          <button
            type="button"
            className={`confirm-choice yes ${choice === 'confirmed' ? 'active' : ''}`}
            onClick={() => setChoice('confirmed')}
          >
            ✓ מגיעים
          </button>
          <button
            type="button"
            className={`confirm-choice maybe ${choice === 'maybe' ? 'active' : ''}`}
            onClick={() => setChoice('maybe')}
          >
            ? אולי
          </button>
          <button
            type="button"
            className={`confirm-choice no ${choice === 'declined' ? 'active' : ''}`}
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
                aria-label="הפחתת אורח"
                disabled={count <= 1}
                onClick={() => setCount((c) => Math.max(1, c - 1))}
              >
                −
              </button>
              <span className="confirm-step-num">{count}</span>
              <button
                type="button"
                className="confirm-step"
                aria-label="הוספת אורח"
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

        {error && <div className="confirm-error">{error}</div>}

        <button
          type="button"
          className="confirm-submit"
          disabled={!choice || busy}
          onClick={send}
        >
          {busy ? 'שולח…' : 'שליחת אישור'}
        </button>
      </div>
    </div>
  )
}
