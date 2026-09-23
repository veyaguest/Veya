import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  getAutomationDashboard,
  getCommunicationSequence,
  getMessageStatus,
  getMessageStatusByType,
  getRsvpTimeline,
  getRsvpTrack,
  getStats,
  listGuests,
} from '../api'
import type {
  AutomationDashboard,
  DashboardStats,
  Guest,
  MessageStatusSummary,
  RsvpStatus,
  RsvpTrackStatus,
} from '../types'
import { RSVP_LABELS } from '../types'
import { DeliveryIcon } from './DeliveryIcon'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { GuestTimelineModal } from './GuestTimelineModal'
import { PhaseCard, RsvpTimeline } from './RsvpTimeline'
import type { GuestFilter } from '../api'
import type { RsvpTimelineView } from '../types'

type RsvpNavigate = (
  page: 'guests' | 'messages' | 'hall',
  options?: { guestFilter?: GuestFilter },
) => void

/**
 * מסך אישורי ההגעה: "מה מצב המוזמנים שלי?" — מי אישר, מי לא ענה, מעקב
 * WhatsApp ולוח הזמנים עד מועד סגירת הרשימה. עריכה/בחירה/שליחה של הודעות
 * נמצאות במסך נפרד ("ניהול הודעות"). הזוג רואה חוויה פשוטה, ואילו אדמין
 * רואה גם לשונית טכנית מלאה (סטטיסטיקות RSVP + רשימת מוזמנים).
 */
export function RsvpPage({
  isAdmin,
  onNavigate,
}: {
  isAdmin: boolean
  onNavigate?: RsvpNavigate
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
  onNavigate?: RsvpNavigate
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

/**
 * סיכום אישורי הגעה — שורה אחת בראש המסך.
 *
 * המסך ששמו "אישורי הגעה" לא ענה על השאלה "כמה אישרו": הנתון חי רק
 * בתמונת מצב, והזוג נאלץ לעבור מסך כדי לדעת. זו **תצוגה בלבד** של
 * ``GET /stats`` — אותו מקור שהדשבורד קורא, בלי חישוב חדש ובלי API חדש.
 *
 * במכוון לא לוח בקרה שני: אין כאן מד, אין גרף ואין פירוק לפי צד או
 * קבוצה. ארבעה מספרים בשורה, ומי שרוצה יותר ממשיך לתמונת מצב.
 *
 * הספירה היא **אנשים** ולא רשומות מוזמן (``*_people``) — אותה יחידה
 * בדיוק כמו במד בתמונת מצב, כדי שלא ייווצרו שני מספרים סותרים למי
 * שעובר בין המסכים.
 */
function RsvpSummaryStrip({
  stats,
  onOpen,
}: {
  stats: DashboardStats | null
  onOpen?: (filter: GuestFilter) => void
}) {
  if (!stats || stats.total_guests === 0) return null

  // אותן תוויות בדיוק כמו במד בתמונת מצב — לא ניסוח מקביל. כל מספר מוביל
  // לרשימת המוזמנים שמאחוריו.
  const d = strings.dashboard
  const items: { key: GuestFilter; value: number; label: string }[] = [
    { key: 'confirmed', value: stats.confirmed_people, label: d.kpiConfirmed },
    { key: 'pending', value: stats.pending_people, label: d.kpiPending },
    { key: 'maybe', value: stats.maybe_people, label: d.gaugeStatusMaybe },
    { key: 'declined', value: stats.declined_people, label: d.gaugeStatusDeclined },
  ]

  return (
    <section className="rsvp-summary" aria-label={strings.messages.summaryLabel}>
      <ul className="rsvp-summary-list">
        {items.map((item) => (
          <li key={item.key} className={`rsvp-summary-item is-${item.key}`}>
            <button
              type="button"
              className="rsvp-summary-btn"
              onClick={() => onOpen?.(item.key)}
              aria-label={d.gaugeCardAria(item.value, item.label)}
            >
              <span className="rsvp-summary-num">{item.value}</span>
              <span className="rsvp-summary-label">{item.label}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="rsvp-summary-foot">
        {strings.messages.summaryFoot(stats.total_people)}
      </p>
    </section>
  )
}

/** "צריכים אתכם" במסך אישורי ההגעה: VEYA מטפלת בעצמה ברוב המוזמנים —
 *  כאן מופיעים רק מי שתלויים בבעל האירוע, כל קבוצה עם הדרך לרשימה שלה. */
function RsvpNeedsYou({
  stats,
  view,
  onOpen,
}: {
  stats: DashboardStats | null
  view: RsvpTimelineView | null
  onOpen?: (filter: GuestFilter) => void
}) {
  if (!stats) return null
  const n = strings.messages.needsYou
  const ended = view?.track_phase === 'ended'
  const items: { key: GuestFilter; title: string; desc: string }[] = []
  const bad = stats.bad_phone_guests ?? 0
  if (bad > 0) items.push({ key: 'bad_phone', title: n.badPhones(bad), desc: n.badPhonesDesc })
  if (ended && stats.pending > 0) {
    items.push({ key: 'pending', title: n.noAnswer(stats.pending), desc: n.noAnswerDesc })
  }
  if (ended && stats.maybe > 0) {
    items.push({ key: 'maybe', title: n.undecided(stats.maybe), desc: n.undecidedDesc })
  }
  if (items.length === 0) return null
  return (
    <section className="dash-stack dash-actions rsvp-needs" aria-label={n.label}>
      <h2 className="rsvp-needs-title">{n.label}</h2>
      {items.map((it) => (
        <div key={it.key} className="invite-banner">
          <div className="invite-banner-text">
            <p className="invite-banner-title">{it.title}</p>
            <p className="invite-banner-desc">{it.desc}</p>
          </div>
          <button type="button" className="invite-banner-btn" onClick={() => onOpen?.(it.key)}>
            {n.cta}
          </button>
        </div>
      ))}
    </section>
  )
}

// ============ מסך הזוג — מעקב אישורי הגעה ============

function CoupleRsvpView({
  onNavigate,
}: {
  onNavigate?: RsvpNavigate
}) {
  const [track, setTrack] = useState<RsvpTrackStatus | null>(null)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [view, setView] = useState<RsvpTimelineView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // קריאה בלבד. **כניסה למסך לא שולחת כלום** — סבבי המסלול יוצאים מהמשימה
  // המתוזמנת בשרת (``rsvp_scheduler``), גם אם אף אחד לא נכנס (2026-09-23).
  const load = useCallback(async () => {
    setError('')
    try {
      const [tr, st, vw] = await Promise.all([
        getRsvpTrack(),
        getStats().catch(() => null),
        getRsvpTimeline().catch(() => null),
      ])
      setTrack(tr)
      setStats(st)
      setView(vw)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.loadGenericRetry)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openGuests = (filter: GuestFilter) => onNavigate?.('guests', { guestFilter: filter })

  if (loading) {
    return (
      <div className="rsvp-page couple-rsvp">
        <p className="mb-empty">רגע, מכינים לכם את אישורי ההגעה…</p>
      </div>
    )
  }

  // המסך זמין גם לפני שליחת הזמנה: לוח הזמנים נגזר ממועד סגירת הרשימה בלבד,
  // ומצב ההודעות מוצג ברגע שיצאה הודעה כלשהי.
  return (
    <div className="rsvp-page couple-rsvp">
      {error && <p className="form-error" role="alert">{error}</p>}

      {/* התשובה לשאלה ששם המסך מבטיח — ראשונה, לפני הפירוט. */}
      <RsvpSummaryStrip stats={stats} onOpen={openGuests} />

      {/* קודם: איפה המסלול עכשיו (לפני / בדרך / הסתיים) ומה הצעד הבא. */}
      {view && (
        <PhaseCard
          view={view}
          onGoToSeating={onNavigate ? () => onNavigate('hall') : undefined}
        />
      )}

      {/* אחר כך: מי באמת צריך אתכם — בשאר המוזמנים VEYA מטפלת בעצמה. */}
      <RsvpNeedsYou stats={stats} view={view} onOpen={openGuests} />

      {/* ולבסוף הלוח עצמו, יום אחרי יום. */}
      <RsvpTimeline view={view ?? undefined} hidePhase={!!view} />

      {track && (
        <TrackStatusCard
          track={track}
          onResend={onNavigate ? () => onNavigate('messages') : undefined}
          onOpenGuests={openGuests}
        />
      )}

      <RsvpFaq />
    </div>
  )
}


const RSVP_FAQ: { q: string; a: string[] }[] = [
  {
    q: 'איך עובדים אישורי ההגעה ב-VEYA?',
    a: [
      'VEYA בונה את מסלול אישורי ההגעה לאחור ממועד סגירת הרשימה, ומנהלת אותו לבד. אין צורך להפעיל שום סבב.',
      '14 ימים לפני מועד סגירת הרשימה המסלול מתחיל, ובמהלכו:',
      '💬 בקשת אישור הגעה ראשונה ועוד 3 סבבי WhatsApp',
      '📞 3 סבבי שיחות',
      'כשנשארים פחות מ-14 ימים, המסלול מתקצר לפחות סבבים, ולא נעשה צפוף יותר.',
      'ההזמנה עצמה נפרדת: היא יוצאת מיד כשאתם שולחים אותה, והיא לא משנה את לוח הזמנים.',
    ],
  },
  {
    q: 'מתי אני יודע את המספר הסופי של המגיעים?',
    a: [
      'במועד סגירת הרשימה שהוגדר לאירוע.',
      'VEYA מנהלת את תהליך אישורי ההגעה ב-14 הימים שלפני המועד הזה, עם סבבי WhatsApp וטלפון, כדי שבסיום יהיה לכם מספר סופי של המוזמנים שמגיעים.',
    ],
  },
  {
    q: 'האם יש גם תזכורות טלפוניות אנושיות?',
    a: [
      'כן.',
      'בנוסף לסבבי ה-WhatsApp, יש 3 סבבי שיחות במהלך 14 ימי אישורי ההגעה.',
      'כלומר, VEYA לא מסתמכת רק על הודעות — המוזמנים שלא השלימו את האישור מקבלים גם טיפול טלפוני כחלק מהתהליך.',
    ],
  },
  {
    q: 'מה קורה ביום האירוע?',
    a: [
      'ביום האירוע המוזמן מקבל הודעת תזכורת אחרונה, שכוללת את הפרטים החשובים להגעה:',
      '🪑 מספר השולחן',
      '📍 ניווט לאירוע',
      '🔔 תזכורת לאירוע',
      'כך המוזמן לא צריך לחפש את פרטי האירוע ברגע האחרון.',
    ],
  },
]

// שורה שמתחילה באימוג'י — מוצגת קומפקטית יותר (פריט ברשימה, לא פסקה מלאה).
const EMOJI_LINE = /^\p{Extended_Pictographic}/u

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
            {open === i && (
              <div className="rsvp-faq-a">
                {item.a.map((para, j) => (
                  <p key={j} className={EMOJI_LINE.test(para) ? 'is-item' : undefined}>
                    {para}
                  </p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

// סטטוסי הודעה שמשמעותם "ההודעה יצאה" (ולכן המוזמן מופיע ברשימה). ``queued``
// (יש מספר תקין אבל טרם נשלח) לא נחשב — עדיין אין מה להראות עליו.
const SENT_STATUSES = new Set(['sent', 'delivered', 'read', 'failed', 'no_valid_number', 'blocked'])

// אותם מונחים בדיוק כמו בכל המערכת (``RSVP_LABELS``) — סטטוס אחד, שם אחד.
const RSVP_ROW_LABEL: Record<RsvpStatus, string> = RSVP_LABELS

interface MessageRow {
  guestId: number
  name: string
  messageLabel: string
  messageStatus: string
  rsvp: RsvpStatus
}

/**
 * "סטטוס הודעות" — תמונת מצב פשוטה של ההודעות שיצאו למוזמנים ושל התגובה
 * שלהם. שני דברים נפרדים, ומוצגים ככאלה: **סטטוס ההודעה** (נשלחה/נמסרה/
 * נקראה/לא נמסרה) ו**סטטוס אישור ההגעה** (ממתין/אישר/לא מגיע).
 *
 * הכול נבנה מנתונים קיימים: הסיכום מ-``getMessageStatus``, ורשימת המוזמנים
 * מ-``getMessageStatusByType`` לכל שלב ברצף + ``listGuests`` (לסטטוס ה-RSVP).
 * בלי API חדש ובלי לגעת בלוגיקת השליחה.
 */
function TrackStatusCard({
  track,
  onResend,
  onOpenGuests,
}: {
  track: RsvpTrackStatus
  onResend?: () => void
  onOpenGuests?: (filter: GuestFilter) => void
}) {
  const [summary, setSummary] = useState<MessageStatusSummary | null>(null)
  const [rows, setRows] = useState<MessageRow[] | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [detailGuest, setDetailGuest] = useState<number | null>(null)
  const t = strings.messages.statusCard

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [seq, guestsRes, sum] = await Promise.all([
          getCommunicationSequence(),
          listGuests('', 1000, 0),
          getMessageStatus(),
        ])
        if (cancelled) return
        setSummary(sum)

        const rsvpByGuest = new Map(guestsRes.items.map((g) => [g.id, g.rsvp_status]))
        const nameByGuest = new Map(guestsRes.items.map((g) => [g.id, g.full_name]))
        const labelByType = new Map<string, string>(seq.map((m) => [m.message_type, m.title]))
        const orderByType = new Map<string, number>(seq.map((m, i) => [m.message_type, i]))

        // ההודעה האחרונה שכל מוזמן קיבל, על פני כל שלבי הרצף.
        const perType = await Promise.all(
          seq.map((m) => getMessageStatusByType(m.message_type).catch(() => null)),
        )
        if (cancelled) return

        const latest = new Map<number, { type: string; status: string; at: number }>()
        for (const ts of perType) {
          if (!ts || ts.not_sent_yet) continue
          for (const gr of ts.guests) {
            if (!SENT_STATUSES.has(gr.status)) continue
            const at = gr.updated_at ? Date.parse(gr.updated_at) : 0
            const cur = latest.get(gr.guest_id)
            const newer =
              !cur ||
              at > cur.at ||
              (at === cur.at &&
                (orderByType.get(ts.message_type) ?? 0) > (orderByType.get(cur.type) ?? 0))
            if (newer) latest.set(gr.guest_id, { type: ts.message_type, status: gr.status, at })
          }
        }

        const merged: MessageRow[] = [...latest.entries()]
          .map(([guestId, v]) => ({
            guestId,
            name: nameByGuest.get(guestId) ?? '—',
            messageLabel: labelByType.get(v.type) ?? '',
            messageStatus: v.status,
            rsvp: (rsvpByGuest.get(guestId) ?? 'pending') as RsvpStatus,
          }))
          .sort((a, b) => a.name.localeCompare(b.name, 'he'))
        setRows(merged)
      } catch {
        if (!cancelled) setError(t.loadError)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [track.invited, t.loadError])

  const shownRows = useMemo(() => {
    if (!rows) return []
    const q = search.trim()
    if (!q) return rows
    return rows.filter((r) => r.name.includes(q))
  }, [rows, search])

  // ארבעה מדדים מצטברים — מספר/פונל, לא סטטוסים בלעדיים.
  const sentTotal = summary
    ? summary.sent + summary.delivered + summary.read
    : 0
  const deliveredTotal = summary ? summary.delivered + summary.read : 0
  const readTotal = summary ? summary.read : 0
  const failedTotal = summary ? summary.failed + summary.blocked : 0
  // מספר לא תקין — סטטוס עצמאי, לא חלק מ"לא נמסרו": מוזמן כזה לא מקבל
  // WhatsApp בכלל, והוא נספר כאן גם אם דילגנו עליו בשליחה (השרת גוזר אותו
  // מתקינות המספר, לא מהודעה שנשלחה).
  const invalidTotal = summary ? summary.no_valid_number : 0

  return (
    <div className="track-status">
      <div className="track-status-head">
        <div>
          <h2 className="track-hero-title">{t.title}</h2>
        </div>
        {track.mode === 'mock' && (
          <span className="mode-badge mock">עדיין לא נשלחות הודעות אמיתיות</span>
        )}
      </div>

      <p className="track-status-sub">{t.subtitle}</p>

      {error && <p className="form-error" role="alert">{error}</p>}

      {/* סיכום פונל: כמה יצאו, נמסרו, נקראו, ולא נמסרו. */}
      <div className="msg-status-grid">
        <MessageStatusTile
          icon={<WhatsAppCheck />}
          num={sentTotal}
          label={t.sent}
          hint={t.sentHint}
        />
        <MessageStatusTile
          icon={<WhatsAppCheck double />}
          num={deliveredTotal}
          label={t.delivered}
          hint={t.deliveredHint}
          tone="ok"
        />
        <MessageStatusTile
          icon={<WhatsAppCheck double blue />}
          num={readTotal}
          label={t.read}
          hint={t.readHint}
          tone="ok"
        />
        <MessageStatusTile
          icon={<DeliveryIcon name="failed" />}
          num={failedTotal}
          label={t.failed}
          hint={t.failedHint}
          tone={failedTotal > 0 ? 'err' : undefined}
        />
        <MessageStatusTile
          icon={<DeliveryIcon name="no_number" />}
          num={invalidTotal}
          label={t.invalidPhone}
          hint={t.invalidPhoneHint}
          tone={invalidTotal > 0 ? 'err' : undefined}
          onClick={invalidTotal > 0 && onOpenGuests ? () => onOpenGuests('bad_phone') : undefined}
        />
      </div>

      <div className="msg-guest-section">
        <h3 className="clar-title">{t.guestListTitle}</h3>

        {rows !== null && rows.length > 0 && (
          <input
            className="send-recipients-search"
            type="search"
            dir="rtl"
            placeholder={t.searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        )}

        <ul className="msg-guest-list">
          {rows === null && !error && (
            <li className="msg-guest-empty">{t.listLoading}</li>
          )}
          {rows !== null && rows.length === 0 && (
            <li className="msg-guest-empty">{t.listEmpty}</li>
          )}
          {shownRows.map((r) => (
            <li key={r.guestId}>
              <button
                type="button"
                className="msg-guest-row msg-guest-row-btn"
                onClick={() => setDetailGuest(r.guestId)}
              >
                <span className="msg-guest-who">
                  <span className="rsvp-name">{r.name}</span>
                  <span className="msg-guest-kind">{r.messageLabel}</span>
                </span>
                <span className="msg-guest-badges">
                  <GuestStatusBadge status={r.messageStatus} />
                  <span className={`msg-guest-rsvp is-${r.rsvp}`}>
                    {RSVP_ROW_LABEL[r.rsvp]}
                  </span>
                </span>
              </button>
            </li>
          ))}
          {rows !== null && rows.length > 0 && shownRows.length === 0 && (
            <li className="msg-guest-empty">{t.guestListEmpty}</li>
          )}
        </ul>
      </div>

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

      {detailGuest != null && (
        <GuestTimelineModal guestId={detailGuest} onClose={() => setDetailGuest(null)} />
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
      {error && <p className="form-error" role="alert">{error}</p>}

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

// תווית סטטוס ההודעה למוזמן בודד — לשון יחיד ("נמסרה", לא "נמסרו").
const MSG_STATUS_ONE: Record<string, string> = {
  sent: 'נשלחה',
  delivered: 'נמסרה',
  read: 'נקראה',
  failed: 'לא נמסרה',
  no_valid_number: 'מספר לא תקין',
  blocked: 'חסום',
  queued: 'ממתין לשליחה',
}

/** תג סטטוס ההודעה של מוזמן בודד — אותה שפת אייקונים כמו כרטיסי הסיכום
 * למעלה (WhatsAppCheck לשלושת סטטוסי המסירה, אייקון קווי לשאר). */
function GuestStatusBadge({ status }: { status: string }) {
  const icon = (() => {
    switch (status) {
      case 'sent':
        return <WhatsAppCheck />
      case 'delivered':
        return <WhatsAppCheck double />
      case 'read':
        return <WhatsAppCheck double blue />
      case 'failed':
        return <DeliveryIcon name="failed" />
      case 'no_valid_number':
        return <DeliveryIcon name="no_number" />
      case 'blocked':
        return <DeliveryIcon name="blocked" />
      default:
        return <DeliveryIcon name="queued" />
    }
  })()
  return (
    <span className={`msg-guest-status is-${status}`}>
      <span className="msg-status-icon" aria-hidden="true">
        {icon}
      </span>
      {MSG_STATUS_ONE[status] ?? status}
    </span>
  )
}

/** כמו StatCard, אבל עם סמל בתחילת התווית — אייקון WhatsApp אמיתי (✓/✓✓
 * אפור/✓✓ כחול) לשלושת סטטוסי המסירה, ואייקון קווי משלנו (DeliveryIcon)
 * לארבעת המצבים שהם תוצר פנימי של VEYA. ``hint`` הוא
 * הסבר בשפה פשוטה שמופיע כ-tooltip במעבר עכבר/החזקה במובייל. */
function MessageStatusTile({
  icon,
  num,
  label,
  hint,
  tone,
  onClick,
}: {
  icon: ReactNode
  num: number | undefined | null
  label: string
  hint: string
  tone?: 'ok' | 'err' | 'wait'
  /** כשיש מה לטפל בו — המדד מוביל לרשימת המוזמנים שמאחוריו. */
  onClick?: () => void
}) {
  const body = (
    <>
      <span className="stat-num">{num ?? '—'}</span>
      <span className="stat-label">
        <span className="msg-status-icon" aria-hidden="true">
          {icon}
        </span>{' '}
        {label}
      </span>
    </>
  )
  if (onClick) {
    return (
      <button
        type="button"
        className={`stat-card msg-status-tile is-link ${tone ?? ''}`}
        title={hint}
        onClick={onClick}
      >
        {body}
      </button>
    )
  }
  return (
    <div className={`stat-card msg-status-tile ${tone ?? ''}`} title={hint}>
      {body}
    </div>
  )
}
