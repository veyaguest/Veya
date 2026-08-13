import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { EventMessage, MessageType, MessageTypeStatus, RsvpTrackStatus } from '../types'
import { MESSAGE_TYPE_ICONS } from '../types'
import { strings } from '../strings/he'

/**
 * מעקב אחרי המוזמנים — מצב ההודעות שנשלחו (נמסרו/נקראו/נכשלו/...), לא
 * אישורי הגעה. אישורי ההגעה (RSVP) נשארים במסך "תמונת מצב" של הדשבורד —
 * הטאב הזה עונה רק על "מה קרה להודעה שנשלחה למוזמן?".
 *
 * הועבר כמעט ללא שינוי מ-TrackStatusCard הישן (RsvpPage.tsx) אל תוך מסך
 * ניהול ההודעות — כדי שלא יעמוד עוד כגוש נפרד וגדול מעל הלוח. הנתונים
 * (sequence + סטטוס לפי סוג) מגיעים כ-props מה-shell המשותף, כדי שלא
 * יהיו קריאות רשת כפולות מול הלוח.
 */
export function MessageTracking({
  sequence,
  statusByType,
  fetchStatus,
  initialType,
  track,
  onResend,
}: {
  sequence: EventMessage[]
  statusByType: Partial<Record<MessageType, MessageTypeStatus>>
  fetchStatus: (type: MessageType) => Promise<MessageTypeStatus>
  initialType?: MessageType
  track?: RsvpTrackStatus
  onResend?: () => void
}) {
  const [activeType, setActiveType] = useState<MessageType>(initialType ?? 'invitation')
  const [typeStatusError, setTypeStatusError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const t = strings.messages.statusCard

  // "צפייה במעקב" מהלוח — קופץ ישר לסוג הרלוונטי.
  useEffect(() => {
    if (initialType) setActiveType(initialType)
  }, [initialType])

  useEffect(() => {
    let cancelled = false
    setTypeStatusError('')
    setSearch('')
    setFilter('all')
    fetchStatus(activeType).catch(() => {
      if (!cancelled) setTypeStatusError(t.loadError)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeType])

  const typeStatus = statusByType[activeType] ?? null

  const filteredGuests = useMemo(() => {
    if (!typeStatus) return []
    const q = search.trim()
    return typeStatus.guests.filter((g) => {
      if (filter !== 'all' && g.status !== filter) return false
      if (!q) return true
      return g.guest_name.includes(q) || (g.phone || '').includes(q)
    })
  }, [typeStatus, search, filter])

  const reached = typeStatus ? typeStatus.sent + typeStatus.delivered + typeStatus.read : 0
  const problems = typeStatus
    ? typeStatus.failed + typeStatus.no_valid_number + typeStatus.blocked
    : 0

  return (
    <div className="track-status">
      <p className="track-status-sub">{t.subtitle}</p>
      {track?.mode === 'mock' && (
        <span className="mode-badge mock">עדיין לא נשלחות הודעות אמיתיות</span>
      )}

      {sequence.length > 0 && (
        <div className="msg-type-select-wrap">
          <label className="msg-type-select-label" htmlFor="msg-type-select">
            {t.selectorLabel}
          </label>
          <select
            id="msg-type-select"
            className="msg-type-select"
            value={activeType}
            onChange={(e) => setActiveType(e.target.value as MessageType)}
          >
            {sequence.map((m) => (
              <option key={m.message_type} value={m.message_type}>
                {MESSAGE_TYPE_ICONS[m.message_type]} {m.title}
              </option>
            ))}
          </select>
        </div>
      )}

      {typeStatusError && <p className="form-error">{typeStatusError}</p>}

      {typeStatus?.not_sent_yet && (
        <div className="msg-empty-state">
          <p>{t.notSentYet[activeType] ?? t.notSentYet.invitation}</p>
          <p>{t.notSentYetNote}</p>
        </div>
      )}

      {typeStatus && !typeStatus.not_sent_yet && (
        <>
          <p className="msg-summary-line">
            <bdi>{typeStatus.total}</bdi> {t.guestsWord} · <bdi>{reached}</bdi>{' '}
            {t.reachedWord}
            {problems > 0 && (
              <>
                {' '}
                · <bdi>{problems}</bdi> {t.needsAttentionWord}
              </>
            )}
          </p>

          {/* לא חייבים להציג מדד שהוא 0 — הדגש נשאר על מה שדורש תשומת לב. */}
          <div className="msg-status-grid">
            {typeStatus.sent > 0 && (
              <MessageStatusTile
                icon={<WhatsAppCheck />}
                num={typeStatus.sent}
                label={t.sent}
                hint={t.sentHint}
              />
            )}
            {typeStatus.delivered > 0 && (
              <MessageStatusTile
                icon={<WhatsAppCheck double />}
                num={typeStatus.delivered}
                label={t.delivered}
                hint={t.deliveredHint}
                tone="ok"
              />
            )}
            {typeStatus.read > 0 && (
              <MessageStatusTile
                icon={<WhatsAppCheck double blue />}
                num={typeStatus.read}
                label={t.read}
                hint={t.readHint}
                tone="ok"
              />
            )}
            {typeStatus.failed > 0 && (
              <MessageStatusTile
                icon="⚠️"
                num={typeStatus.failed}
                label={t.failed}
                hint={t.failedHint}
                tone="err"
              />
            )}
            {typeStatus.no_valid_number > 0 && (
              <MessageStatusTile
                icon="📵"
                num={typeStatus.no_valid_number}
                label={t.noValidNumber}
                hint={t.noValidNumberHint}
                tone="err"
              />
            )}
            {typeStatus.blocked > 0 && (
              <MessageStatusTile
                icon="🚫"
                num={typeStatus.blocked}
                label={t.blocked}
                hint={t.blockedHint}
                tone="err"
              />
            )}
            {typeStatus.queued > 0 && (
              <MessageStatusTile
                icon="⏳"
                num={typeStatus.queued}
                label={t.queued}
                hint={t.queuedHint}
                tone="wait"
              />
            )}
          </div>
          {typeStatus.read > 0 && <p className="track-status-note">{t.readNote}</p>}
        </>
      )}

      {onResend && (
        <div className="track-resend">
          <button className="btn-ghost" onClick={onResend}>
            שליחת הזמנות
          </button>
          <span className="clar-sub">
            הוספתם מוזמנים חדשים? אפשר לשלוח להם הזמנה בלי לשלוח שוב למי שכבר קיבל.
          </span>
        </div>
      )}

      {/* פירוט מעקב לפי מוזמן — מקופל כברירת מחדל (כמו ה-FAQ בדף הנחיתה).
          האריחים למעלה כבר נותנים את התמונה הכללית; הרשימה המלאה היא
          progressive disclosure, לא משהו שצריך לתפוס מקום תמיד. */}
      {((typeStatus && !typeStatus.not_sent_yet) || (track && track.phone_list.length > 0)) && (
        <details className="track-detail">
          <summary className="track-detail-summary">פירוט מעקב לפי מוזמן</summary>

          {typeStatus && !typeStatus.not_sent_yet && (
            <div className="msg-guest-section">
              <h3 className="clar-title">{t.guestListTitle}</h3>
              <div className="msg-guest-controls">
                <input
                  className="send-recipients-search"
                  type="search"
                  dir="rtl"
                  placeholder={t.searchPlaceholder}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <select
                  className="msg-guest-filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">{t.filterAll}</option>
                  <option value="sent">✓ {t.sent}</option>
                  <option value="delivered">✓✓ {t.delivered}</option>
                  <option value="read">✓✓ {t.read}</option>
                  <option value="failed">⚠️ {t.failed}</option>
                  <option value="no_valid_number">📵 {t.noValidNumber}</option>
                  <option value="blocked">🚫 {t.blocked}</option>
                  <option value="queued">⏳ {t.queued}</option>
                </select>
              </div>

              <ul className="msg-guest-list">
                {filteredGuests.map((g) => (
                  <li key={g.guest_id} className="msg-guest-row">
                    <span className="msg-guest-who">
                      <span className="rsvp-name">{g.guest_name}</span>
                      <span className="msg-guest-phone">{g.phone || '—'}</span>
                    </span>
                    <GuestStatusBadge status={g.status} t={t} />
                  </li>
                ))}
                {filteredGuests.length === 0 && (
                  <li className="msg-guest-empty">{t.guestListEmpty}</li>
                )}
              </ul>
            </div>
          )}

          {track && track.phone_list.length > 0 && (
            <div className="track-phone">
              <h3 className="clar-title">רשימת מעקב טלפוני</h3>
              <span className="clar-sub">
                מוזמנים שעדיין לא ענו אחרי כל התזכורות — כדאי טלפון אישי.
              </span>
              <ul className="track-phone-list">
                {track.phone_list.map((row) => (
                  <li key={row.guest_id} className="track-phone-row">
                    <span className="rsvp-name">{row.guest_name}</span>
                    <a className="track-phone-num" href={`tel:${row.phone}`}>
                      {row.phone || '—'}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </details>
      )}
    </div>
  )
}

/**
 * הוי-ים של WhatsApp — צוירים כ-SVG (לא תווי ✓ טקסטואליים, שנראים שונה
 * בכל גופן/מערכת הפעלה) כדי שיזוהו מיד כ"שפת WhatsApp": קו אחד = נשלח,
 * שני קווים אפורים = נמסר, שני קווים כחולים = נקרא. הצבעים קבועים בכוונה
 * (לא טוקן עיצוב של VEYA) — כמו .wa-bubble/.ph-screen הקיימים במסך הזה,
 * זה ייצוג מדויק של ממשק חיצוני, לא צבע מותג.
 */
function WhatsAppCheck({ double, blue }: { double?: boolean; blue?: boolean }) {
  return (
    <svg
      className={`wa-check-icon ${blue ? 'wa-check-icon-read' : ''}`}
      viewBox="0 0 20 12"
      width="20"
      height="12"
      aria-hidden="true"
      focusable="false"
    >
      {double && (
        <path
          d="M1 6.6L4.4 10L11 3"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
      <path
        d="M5 6.6L8.4 10L19 1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** תג הסטטוס של מוזמן בודד ברשימת "מי קיבל את ההודעה" — אותה שפת אייקונים
 * בדיוק כמו כרטיסי הסיכום למעלה (WhatsAppCheck לשלושת סטטוסי המסירה, אמוג'י
 * לשאר), רק בשורה אחת קטנה עם התווית לצידה. */
function GuestStatusBadge({
  status,
  t,
}: {
  status: string
  t: typeof strings.messages.statusCard
}) {
  const content = (() => {
    switch (status) {
      case 'sent':
        return { icon: <WhatsAppCheck />, label: t.sent }
      case 'delivered':
        return { icon: <WhatsAppCheck double />, label: t.delivered }
      case 'read':
        return { icon: <WhatsAppCheck double blue />, label: t.read }
      case 'failed':
        return { icon: '⚠️', label: t.failed }
      case 'no_valid_number':
        return { icon: '📵', label: t.noValidNumber }
      case 'blocked':
        return { icon: '🚫', label: t.blocked }
      default:
        return { icon: '⏳', label: t.queued }
    }
  })()
  return (
    <span className="msg-guest-status">
      <span className="msg-status-icon" aria-hidden="true">
        {content.icon}
      </span>
      {content.label}
    </span>
  )
}

/** כמו StatCard, אבל עם סמל בתחילת התווית — אייקון WhatsApp אמיתי (✓/✓✓
 * אפור/✓✓ כחול) לשלושת סטטוסי המסירה, ואמוג'י לשאר (⚠️/📵/🚫/⏳, שאינם
 * חלק משפת העיצוב של WhatsApp אלא תוצרים פנימיים של VEYA). ``hint`` הוא
 * הסבר בשפה פשוטה שמופיע כ-tooltip במעבר עכבר/החזקה במובייל. */
function MessageStatusTile({
  icon,
  num,
  label,
  hint,
  tone,
}: {
  icon: ReactNode
  num: number | undefined | null
  label: string
  hint: string
  tone?: 'ok' | 'err' | 'wait'
}) {
  return (
    <div className={`stat-card msg-status-tile ${tone ?? ''}`} title={hint}>
      <span className="stat-num">{num ?? '—'}</span>
      <span className="stat-label">
        <span className="msg-status-icon" aria-hidden="true">
          {icon}
        </span>{' '}
        {label}
      </span>
    </div>
  )
}
