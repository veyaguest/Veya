import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  advanceRsvpTrack,
  getAutomationDashboard,
  getCommunicationSequence,
  getMessageStatusByType,
  getRsvpTrack,
  listGuests,
} from '../api'
import type {
  AutomationDashboard,
  EventMessage,
  Guest,
  MessageType,
  MessageTypeStatus,
  RsvpTrackStatus,
} from '../types'
import { MESSAGE_TYPE_ICONS, RSVP_LABELS } from '../types'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { GuestTimelineModal } from './GuestTimelineModal'
import { RsvpTimeline } from './RsvpTimeline'

/**
 * מסך אישורי ההגעה: "מה מצב המוזמנים שלי?" — מי אישר, מי לא ענה, מעקב
 * WhatsApp ולוח הזמנים עד יום ההתחייבות לאולם. עריכה/בחירה/שליחה של הודעות
 * נמצאות במסך נפרד ("ניהול הודעות"). הזוג רואה חוויה פשוטה, ואילו אדמין
 * רואה גם לשונית טכנית מלאה (סטטיסטיקות RSVP + רשימת מוזמנים).
 */
export function RsvpPage({
  isAdmin,
  onNavigate,
}: {
  isAdmin: boolean
  onNavigate?: (page: 'guests' | 'messages') => void
}) {
  if (!isAdmin) return <CoupleRsvpView onNavigate={onNavigate} />
  return <AdminRsvpShell onNavigate={onNavigate} />
}

/**
 * מעטפת לאדמין: כברירת מחדל מציגה את חוויית הזוג (מעקב אישורי ההגעה), כי
 * זה הלב של המוצר. מתג קטן מאפשר לעבור לפאנל הניהול הטכני בעת הצורך.
 * זוג רגיל לא רואה את המתג הזה כלל.
 */
function AdminRsvpShell({
  onNavigate,
}: {
  onNavigate?: (page: 'guests' | 'messages') => void
}) {
  const [view, setView] = useState<'couple' | 'admin'>('couple')
  return (
    <>
      <div className="rsvp-view-toggle" role="tablist">
        <button
          role="tab"
          className={`rsvp-view-btn ${view === 'couple' ? 'active' : ''}`}
          onClick={() => setView('couple')}
        >
          תצוגת הזוג
        </button>
        <button
          role="tab"
          className={`rsvp-view-btn ${view === 'admin' ? 'active' : ''}`}
          onClick={() => setView('admin')}
        >
          ניהול טכני
        </button>
      </div>
      {view === 'couple' ? (
        <CoupleRsvpView onNavigate={onNavigate} />
      ) : (
        <AdminRsvpView onGoToMessages={() => onNavigate?.('messages')} />
      )}
    </>
  )
}

function AdminRsvpView({ onGoToMessages }: { onGoToMessages?: () => void }) {
  const [timelineGuest, setTimelineGuest] = useState<number | null>(null)

  return (
    <div className="rsvp-page">
      <DashboardTab onOpenTimeline={setTimelineGuest} onGoToMessages={onGoToMessages} />

      {timelineGuest != null && (
        <GuestTimelineModal
          guestId={timelineGuest}
          onClose={() => setTimelineGuest(null)}
        />
      )}
    </div>
  )
}

// ============ מסך הזוג — מעקב אישורי הגעה ============

function CoupleRsvpView({
  onNavigate,
}: {
  onNavigate?: (page: 'guests' | 'messages') => void
}) {
  const [track, setTrack] = useState<RsvpTrackStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  // בטעינה: טוענים סטטוס, ואם המסלול פעיל — מקדמים אותו אוטומטית (idempotent;
  // אותה קריאה שגם מסך "ניהול הודעות" מבצע, כך התזכורות ממשיכות לצאת גם
  // כשמבקרים רק בעמוד אחד מהשניים).
  const load = useCallback(async () => {
    setError('')
    try {
      const status = await getRsvpTrack()
      if (status.active) {
        const advanced = await advanceRsvpTrack()
        setTrack(advanced)
        const moved = advanced.sent + advanced.phoned
        if (moved > 0) {
          setNote(
            `המסלול התקדם: ${advanced.sent} הודעות חדשות נשלחו` +
              (advanced.phoned
                ? ` · ${advanced.phoned} נוספו לרשימת המעקב הטלפוני`
                : ''),
          )
        }
      } else {
        setTrack(status)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.loadGenericRetry)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="rsvp-page couple-rsvp">
        <p className="mb-empty">רגע, מכינים לכם את אישורי ההגעה…</p>
      </div>
    )
  }

  const active = track?.active

  return (
    <div className="rsvp-page couple-rsvp">
      {error && <p className="form-error">{error}</p>}
      {note && <p className="rsvp-note">{note}</p>}

      {!active ? (
        <RsvpEmptyState
          onGoToMessages={onNavigate ? () => onNavigate('messages') : undefined}
        />
      ) : (
        <>
          {/* יומן המשימות היומי — לוח הזמנים שנבנה לאחור מיום ההתחייבות לאולם. */}
          <RsvpTimeline />
          {track && (
            <TrackStatusCard
              track={track}
              onResend={onNavigate ? () => onNavigate('messages') : undefined}
            />
          )}
        </>
      )}

      <RsvpFaq />
    </div>
  )
}

/** מצב לפני שליחת הזמנה ראשונה — אישורי ההגעה עוד לא התחילו לרוץ. */
function RsvpEmptyState({ onGoToMessages }: { onGoToMessages?: () => void }) {
  return (
    <div className="tl-empty">
      <span className="tl-empty-icon" aria-hidden>
        🗓️
      </span>
      <h3 className="tl-empty-title">אישורי ההגעה יתחילו לרוץ ברגע שתשלחו הזמנה</h3>
      <p className="tl-empty-sub">
        כאן תראו בכל רגע מי אישר, מי עדיין לא ענה ומי לא מגיע — וגם את לוח
        הזמנים שבנינו לכם עד יום ההתחייבות לאולם.
      </p>
      {onGoToMessages && (
        <button className="btn-primary tl-empty-cta" onClick={onGoToMessages}>
          לניהול הודעות ושליחת הזמנות
        </button>
      )}
    </div>
  )
}

/** שאלות נפוצות על אישורי הגעה — עברית פשוטה, בלי מונחים טכניים. */
const RSVP_FAQ: { q: string; a: string }[] = [
  {
    q: 'איך אישורי ההגעה עובדים?',
    a: 'אחרי ששולחים הזמנה, כל מוזמן מקבל קישור אישי לאישור הגעה בוואטסאפ. משם יוצא רצף תזכורות אוטומטי למי שעדיין לא ענה, ובעמוד הזה רואים בכל רגע מי אישר, מי לא ומי עדיין לא החליט.',
  },
  {
    q: 'מתי האורחים מקבלים בקשה לאישור?',
    a: 'קצת אחרי ההזמנה, ולפי לוח הזמנים שבנינו לכם עד יום ההתחייבות לאולם. מי שלא עונה מקבל תזכורת נוספת, וככל שמתקרבים ליום ההתחייבות התזכורות מתקצרות כדי לתפוס עוד תשובות בזמן.',
  },
  {
    q: 'מה קורה אם אורח עדיין לא ענה?',
    a: 'הוא ממשיך לקבל תזכורות אוטומטיות לפי לוח הזמנים. מי שלא עונה אחרי כל התזכורות עובר לרשימת מעקב טלפוני, כדי שתוכלו להתקשר אישית לפני שסוגרים מספר סופי.',
  },
  {
    q: 'האם אורח שכבר אישר יכול לשנות תשובה?',
    a: 'כן. הקישור האישי שלו נשאר פתוח לאורך כל הדרך, ואפשר לחזור אליו ולעדכן תשובה בכל שלב — עד יום ההתחייבות.',
  },
  {
    q: 'איך אני יודע מי עדיין לא אישר?',
    a: 'בכרטיס אישורי ההגעה רואים תמיד כמה אישרו, כמה עדיין לא ענו וכמה לא מגיעים, ובמסך המוזמנים אפשר לראות את הסטטוס של כל אחד ואחת בנפרד.',
  },
  {
    q: 'מה המשמעות של סטטוסי וואטסאפ?',
    a: '✓ אחד — ההודעה נשלחה. ✓✓ אפורים — היא הגיעה למכשיר. ✓✓ כחולים — המוזמן פתח וקרא אותה. אם השליחה נכשלה או שהמספר לא תקין, זה יסומן בבירור כדי שתוכלו לתקן.',
  },
  {
    q: 'מה קורה אם מספר של אורח לא זמין?',
    a: 'אם המספר חסר או בפורמט לא תקין, ההודעה לא נשלחת אליו וזה מסומן ברשימה. אפשר לתקן את המספר במסך המוזמנים ולשלוח את ההזמנה שוב, רק אליו.',
  },
  {
    q: 'איך VEYA עוזרת לי להגיע למספר מוזמנים מדויק לקראת האירוע?',
    a: 'בנינו לכם לוח זמנים שמסתיים ביום ההתחייבות לאולם, עם תזכורות אוטומטיות ורשימת מעקב טלפוני למי שלא ענה — כדי שתגיעו לאותו יום עם מספר סופי וברור, בלי לרדוף אחרי אף אחד בעצמכם.',
  },
]

function RsvpFaq() {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <section className="rsvp-faq">
      <h2 className="rsvp-faq-title">שאלות נפוצות על אישורי הגעה</h2>
      <div className="rsvp-faq-list">
        {RSVP_FAQ.map((item, i) => (
          <div key={i} className="rsvp-faq-item mb-card">
            <button
              type="button"
              className="lib2-card-head"
              onClick={() => setOpen((cur) => (cur === i ? null : i))}
            >
              <span className="rsvp-faq-q-text">{item.q}</span>
              <span className="lib2-card-arrow" aria-hidden="true">
                {open === i ? '︿' : '﹀'}
              </span>
            </button>
            {open === i && <p className="rsvp-faq-a">{item.a}</p>}
          </div>
        ))}
      </div>
    </section>
  )
}

/**
 * כרטיס "מעקב אחרי המוזמנים" — מצב ההודעות שנשלחו (נמסרו/נקראו/נכשלו/...),
 * לא אישורי הגעה. אישורי ההגעה (RSVP) נשארים במסך "תמונת מצב" של הדשבורד —
 * הכרטיס הזה עונה רק על "מה קרה להודעה שנשלחה למוזמן?".
 *
 * מציג הודעה אחת בכל פעם (בורר "מעקב אחר: X", בדיוק אותם שלבים וכינויים
 * שמנוהלים ב"ניהול הודעות" — ``getCommunicationSequence``, לא רשימה
 * מקבילה) — הסטטוס של ההזמנה של מוזמן לעולם לא מתערבב עם הסטטוס של
 * התזכורת שלו (ראו backend: message_status.summarize_by_type).
 */
function TrackStatusCard({
  track,
  onResend,
}: {
  track: RsvpTrackStatus
  onResend?: () => void
}) {
  const [sequence, setSequence] = useState<EventMessage[] | null>(null)
  const [activeType, setActiveType] = useState<MessageType>('invitation')
  const [typeStatus, setTypeStatus] = useState<MessageTypeStatus | null>(null)
  const [typeStatusError, setTypeStatusError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const t = strings.messages.statusCard

  // בורר "מעקב אחר" — אותן הודעות/כינויים בדיוק כמו לשונית "ניהול הודעות".
  useEffect(() => {
    let cancelled = false
    getCommunicationSequence()
      .then((seq) => {
        if (!cancelled) setSequence(seq)
      })
      .catch(() => {
        /* שקט — הבורר פשוט לא יוצג; שאר הכרטיס עדיין עובד */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // בכל החלפת הודעה נבחרת (או שינוי במספר המוזמנים שקיבלו הזמנה) — טוענים
  // מחדש וגם מאפסים חיפוש/סינון, כי הם שייכים להודעה הקודמת שנבחרה.
  useEffect(() => {
    let cancelled = false
    setTypeStatus(null)
    setTypeStatusError('')
    setSearch('')
    setFilter('all')
    getMessageStatusByType(activeType)
      .then((s) => {
        if (!cancelled) setTypeStatus(s)
      })
      .catch(() => {
        if (!cancelled) setTypeStatusError(t.loadError)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeType, track.invited])

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
      <div className="track-status-head">
        <div>
          <span className="track-hero-badge ok">פעיל</span>
          <h2 className="track-hero-title">{t.title}</h2>
        </div>
        {track.mode === 'mock' && (
          <span className="mode-badge mock">עדיין לא נשלחות הודעות אמיתיות</span>
        )}
      </div>

      <p className="track-status-sub">{t.subtitle}</p>

      {sequence && sequence.length > 0 && (
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

          {/* "מי קיבל את ההודעה" — נפרד לחלוטין מסטטוס ה-RSVP (מסך "תמונת מצב"). */}
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

      {track.phone_list.length > 0 && (
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
    </div>
  )
}

// ============ לשונית "מצב ומעקב" (אדמין) ============

function DashboardTab({
  onOpenTimeline,
  onGoToMessages,
}: {
  onOpenTimeline: (guestId: number) => void
  onGoToMessages?: () => void
}) {
  const [dash, setDash] = useState<AutomationDashboard | null>(null)
  const [guests, setGuests] = useState<Guest[]>([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [d, g] = await Promise.all([
        getAutomationDashboard(),
        listGuests('', 300, 0),
      ])
      setDash(d)
      setGuests(g.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.rsvpStateLoadFailed)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <div className="auto-dashboard">
      {error && <p className="form-error">{error}</p>}

      {/* כרטיסי מצב */}
      <div className="auto-stat-grid">
        <StatCard num={dash?.total_guests} label="סה״כ מוזמנים" />
        <StatCard num={dash?.invited} label="קיבלו הזמנה" />
        <StatCard num={dash?.confirmed} label="אישרו הגעה" tone="ok" />
        <StatCard num={dash?.pending} label="ממתינים לתשובה" tone="wait" />
        <StatCard num={dash?.declined} label="לא מגיעים" tone="err" />
        <StatCard num={dash?.in_reminder_process} label="בתהליך תזכורות" />
      </div>

      {/* שורת סיכום מהירה */}
      <div className="auto-summary-row">
        {dash?.days_to_event != null && (
          <span className="auto-chip">
            {dash.days_to_event >= 0
              ? `${dash.days_to_event} ימים לאירוע`
              : 'האירוע כבר עבר'}
          </span>
        )}
        <span className="auto-chip">{dash?.active_rules ?? 0} הודעות פעילות ברצף</span>
        <button
          className="auto-chip auto-chip-btn"
          onClick={() => onGoToMessages?.()}
          title="מעבר לניהול הודעות"
        >
          {dash?.due_now ?? 0} הודעות ממתינות בתור →
        </button>
      </div>

      {/* המלצות מעקב חכם */}
      {dash && dash.recommendations.length > 0 && (
        <div className="auto-recs">
          <h3 className="clar-title">מעקב חכם</h3>
          <ul className="auto-rec-list">
            {dash.recommendations.map((r, i) => (
              <li key={i} className={`auto-rec ${r.severity}`}>
                <span className="auto-rec-icon" aria-hidden>
                  {r.severity === 'warn' ? '⚠' : 'ℹ'}
                </span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* רשימת מוזמנים עם גישה לציר זמן */}
      <div className="rsvp-guests">
        <div className="rsvp-guests-head">
          <h3 className="clar-title">{activeEventTerms().guestsLabel}</h3>
          <span className="clar-sub">לחצו "ציר זמן" כדי לראות את היסטוריית ההודעות של מוזמן.</span>
        </div>
        <ul className="rsvp-list">
          {guests.map((g) => (
            <li key={g.id} className="rsvp-row">
              <span className="rsvp-name">{g.full_name}</span>
              <span className={`rsvp-badge ${g.rsvp_status}`}>
                {RSVP_LABELS[g.rsvp_status]}
              </span>
              <button
                className="btn-text auto-timeline-btn"
                onClick={() => onOpenTimeline(g.id)}
              >
                ציר זמן
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function StatCard({
  num,
  label,
  tone,
}: {
  num: number | undefined | null
  label: string
  tone?: 'ok' | 'err' | 'wait'
}) {
  return (
    <div className={`stat-card ${tone ?? ''}`}>
      <span className="stat-num">{num ?? '—'}</span>
      <span className="stat-label">{label}</span>
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
