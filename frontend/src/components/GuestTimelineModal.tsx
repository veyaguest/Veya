import { useEffect, useState } from 'react'
import { getGuestTimeline } from '../api'
import type { GuestTimeline, TimelineEvent } from '../types'
import { RSVP_LABELS } from '../types'

const KIND_LABEL: Record<string, string> = {
  invitation: 'הזמנה נשלחה',
  reminder: 'תזכורת נשלחה',
  pre_event: 'הודעה לפני האירוע',
  thank_you: 'הודעת תודה',
  reply: 'תשובת המוזמן',
  custom: 'הודעה נשלחה',
}

function fmt(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('he-IL', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function lineFor(e: TimelineEvent): string {
  if (e.direction === 'inbound') return 'המוזמן הגיב'
  return KIND_LABEL[e.kind] ?? 'הודעה נשלחה'
}

/** חלון ציר-זמן של מוזמן — כל ההודעות היוצאות והנכנסות לפי סדר. */
export function GuestTimelineModal({
  guestId,
  onClose,
}: {
  guestId: number
  onClose: () => void
}) {
  const [data, setData] = useState<GuestTimeline | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getGuestTimeline(guestId)
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת ציר הזמן'),
      )
  }, [guestId])

  return (
    <div className="auto-modal-backdrop" onClick={onClose}>
      <div className="auto-modal" onClick={(e) => e.stopPropagation()}>
        <div className="auto-modal-head">
          <h3 className="clar-title">
            ציר זמן — {data?.guest_name ?? '…'}
          </h3>
          <button className="btn-text" onClick={onClose}>
            סגירה ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}

        {data && (
          <>
            <div className="auto-modal-status">
              סטטוס נוכחי:{' '}
              <span className={`rsvp-badge ${data.rsvp_status}`}>
                {RSVP_LABELS[data.rsvp_status]}
              </span>
            </div>

            {data.events.length === 0 ? (
              <p className="auto-empty">עדיין לא נשלחו הודעות למוזמן הזה.</p>
            ) : (
              <ul className="auto-timeline">
                {data.events.map((e, i) => (
                  <li key={i} className={`auto-timeline-row ${e.direction}`}>
                    <span className="auto-timeline-dot" />
                    <div className="auto-timeline-body">
                      <div className="auto-timeline-top">
                        <span className="auto-timeline-kind">{lineFor(e)}</span>
                        <span className="auto-timeline-date">{fmt(e.created_at)}</span>
                      </div>
                      {e.text && (
                        <div className="auto-timeline-text">
                          {e.text.split('\n')[0]}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  )
}
