import { useEffect, useMemo, useState } from 'react'
import { getEvent, getMessageLibrary } from '../api'
import type { EventType, MessageDefault } from '../types'
import { EVENT_TYPE_OPTIONS } from '../strings/eventTypes'

/**
 * ספריית הודעות מוכנות — תצוגה בלבד (לא עריכה) של כל ברירות המחדל, לפי סוג
 * אירוע. זה בדיוק הנוסח שנכנס אוטומטית לכל אירוע חדש מאותו סוג
 * (``provision_event_messages``). לעריכת ההודעות של האירוע שלכם — "תקשורת
 * עם אורחים".
 */
export function MessageLibrary() {
  const [rows, setRows] = useState<MessageDefault[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<EventType>('wedding')
  const [openType, setOpenType] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getMessageLibrary(), getEvent().catch(() => null)])
      .then(([lib, event]) => {
        setRows(lib)
        if (event) setSelected(event.event_type)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת הספרייה נכשלה'))
  }, [])

  const forType = useMemo(
    () => (rows ?? []).filter((r) => r.event_type === selected),
    [rows, selected],
  )

  return (
    <div className="mb-wrap">
      <div className="mb-head">
        <h2 className="mb-title">ספריית הודעות מוכנות</h2>
        <p className="mb-sub">
          כל נוסחי ההודעות המוכנים, לפי סוג אירוע — לצפייה בלבד. הנוסח של
          סוג האירוע שלכם הוא בדיוק מה שכבר נכנס אוטומטית ל"תקשורת עם
          אורחים" שלכם.
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}
      {rows === null && !error && <p className="mb-empty">טוענים…</p>}

      {rows && (
        <>
          <div className="lib2-chips">
            {EVENT_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.type}
                type="button"
                className={`lib2-chip ${selected === opt.type ? 'active' : ''}`}
                onClick={() => setSelected(opt.type)}
              >
                <span aria-hidden="true">{opt.icon}</span> {opt.label}
              </button>
            ))}
          </div>

          <div className="comm-list">
            {forType.map((row) => (
              <LibraryCard
                key={row.message_type}
                row={row}
                open={openType === row.message_type}
                onToggle={() =>
                  setOpenType((cur) => (cur === row.message_type ? null : row.message_type))
                }
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function LibraryCard({
  row,
  open,
  onToggle,
}: {
  row: MessageDefault
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className={`mb-card comm-card ${row.is_active ? '' : 'comm-card-off'}`}>
      <button type="button" className="lib2-card-head" onClick={onToggle}>
        <h3 className="mb-card-title">{row.title}</h3>
        <span className="lib2-card-arrow" aria-hidden="true">{open ? '︿' : '﹀'}</span>
      </button>

      {!row.content && (
        <p className="mb-card-hint">
          עוד לא הוזן נוסח סופי להודעה הזו — הוא יופיע כאן ברגע שיוזן.
        </p>
      )}

      {open && row.content && (
        <div className="wa-screen">
          <div className="wa-bubble">
            <span className="wa-text">{row.content}</span>
          </div>
        </div>
      )}
    </div>
  )
}
