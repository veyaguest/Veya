import { useEffect, useState } from 'react'
import {
  getCommunicationSequence,
  getEvent,
  getMessageOptions,
  mediaUrl,
  previewCommunicationMessage,
  testSendCommunicationMessage,
  updateCommunicationMessage,
} from '../api'
import type { EventDetails, EventMessage, MessageDefaultOption, MessageType } from '../types'
import { COMMUNICATION_VARIABLES } from '../types'

const STEP_ICON: Record<MessageType, string> = {
  invitation: '💌',
  reminder_1: '👋',
  reminder_2: '🔔',
  final_reminder: '⏰',
  event_day: '🎉',
  thank_you: '❤️',
}

/**
 * המרה דו-כיוונית בין תחביר המשתנים הטכני ({{guest_name}}) לתווית עברית
 * ידידותית בעורך ([שם האורח]) — כדי שהזוג לא יראה syntax. מה שנשמר בפועל
 * דרך ה-API הוא תמיד ה-{{...}} המקורי; ההמרה קיימת רק בתצוגת העורך.
 */
function toDisplay(content: string): string {
  let out = content
  for (const v of COMMUNICATION_VARIABLES) {
    out = out.split(`{{${v.key}}}`).join(`[${v.label}]`)
  }
  return out
}
function toRaw(display: string): string {
  let out = display
  for (const v of COMMUNICATION_VARIABLES) {
    out = out.split(`[${v.label}]`).join(`{{${v.key}}}`)
  }
  return out
}

export function CommunicationTab() {
  const [messages, setMessages] = useState<EventMessage[] | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      const [seq, ev] = await Promise.all([getCommunicationSequence(), getEvent().catch(() => null)])
      setMessages(seq)
      if (ev) setEvent(ev)
      const entries = await Promise.all(
        seq.map(async (m) => {
          try {
            return [m.message_type, await previewCommunicationMessage(m.message_type)] as const
          } catch {
            return [m.message_type, ''] as const
          }
        }),
      )
      setPreviews(Object.fromEntries(entries))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת ההודעות נכשלה')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <div className="mb-wrap">
      <div className="mb-head">
        <h2 className="mb-title">💬 הודעות לאורחים</h2>
        <p className="mb-sub">כאן תוכלו לבחור ולערוך את ההודעות שהאורחים יקבלו לאורך הדרך.</p>
      </div>

      {error && <p className="form-error">{error}</p>}
      {messages === null && !error && <p className="mb-empty">טוענים…</p>}

      {messages && (
        <div className="gm-grid">
          {messages.map((m) => (
            <MessageCard
              key={m.message_type}
              message={m}
              event={event}
              previewText={previews[m.message_type] ?? ''}
              onSaved={refresh}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function MessageCard({
  message,
  event,
  previewText,
  onSaved,
}: {
  message: EventMessage
  event: EventDetails | null
  previewText: string
  onSaved: () => void
}) {
  const [showPicker, setShowPicker] = useState(false)
  const [options, setOptions] = useState<MessageDefaultOption[] | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [note, setNote] = useState('')
  const [togglingActive, setTogglingActive] = useState(false)

  async function toggleActive() {
    setTogglingActive(true)
    try {
      await updateCommunicationMessage(message.message_type, { is_active: !message.is_active })
      onSaved()
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'העדכון נכשל')
    } finally {
      setTogglingActive(false)
    }
  }

  async function openPicker() {
    const next = !showPicker
    setShowPicker(next)
    if (next && options === null) {
      setOptionsLoading(true)
      try {
        setOptions(await getMessageOptions(message.message_type))
      } catch (err) {
        setNote(err instanceof Error ? err.message : 'טעינת ההודעות המוכנות נכשלה')
      } finally {
        setOptionsLoading(false)
      }
    }
  }

  async function chooseOption(opt: MessageDefaultOption) {
    if (opt.content === message.content) {
      setShowPicker(false)
      return
    }
    try {
      await updateCommunicationMessage(message.message_type, { content: opt.content })
      setShowPicker(false)
      onSaved()
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'הבחירה נכשלה')
    }
  }

  const shortPreview = previewText.replace(/\n+/g, ' ').trim()

  return (
    <div className={`gm-card ${message.is_active ? '' : 'gm-card-off'}`}>
      <div className="gm-card-top">
        <div className="gm-card-heading">
          <span className="gm-icon" aria-hidden="true">{STEP_ICON[message.message_type]}</span>
          <h3 className="gm-card-title">{message.title}</h3>
        </div>
        <label className="gm-toggle" title="פעיל">
          <input
            type="checkbox"
            checked={message.is_active}
            disabled={togglingActive}
            onChange={toggleActive}
          />
          <span>פעיל</span>
        </label>
      </div>

      {shortPreview ? (
        <p className="gm-preview-text">{shortPreview}</p>
      ) : (
        <p className="gm-preview-text gm-preview-empty">עדיין לא נבחרה הודעה לשלב הזה.</p>
      )}

      <button type="button" className="gm-preview-link" onClick={() => setShowPreview(true)}>
        👀 תצוגה מקדימה
      </button>

      <div className="gm-actions">
        <button type="button" className="btn-ghost" onClick={openPicker}>
          {showPicker ? 'סגירה' : 'בחירת הודעה'}
        </button>
        <button type="button" className="btn-ghost" onClick={() => setShowEdit(true)}>
          עריכת הודעה
        </button>
      </div>

      {note && <span className="mb-dirty">{note}</span>}

      {showPicker && (
        <div className="comm-picker">
          {optionsLoading && <p className="mb-empty">טוענים…</p>}
          {!optionsLoading && options !== null && options.length === 0 && (
            <p className="mb-card-hint">עדיין אין הודעות מוכנות לשלב הזה.</p>
          )}
          {!optionsLoading && options && options.length > 0 && (
            <div className="comm-picker-list">
              {options.map((opt) => {
                const selected = opt.content === message.content
                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`comm-picker-option gm-picker-option ${selected ? 'gm-picker-selected' : ''}`}
                    onClick={() => chooseOption(opt)}
                  >
                    {selected && <span className="gm-picker-check" aria-hidden="true">✓</span>}
                    <p className="comm-picker-text">{opt.content}</p>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {showEdit && (
        <EditModal message={message} onClose={() => setShowEdit(false)} onSaved={onSaved} />
      )}

      {showPreview && (
        <PreviewModal
          message={message}
          event={event}
          onClose={() => setShowPreview(false)}
        />
      )}
    </div>
  )
}

function EditModal({
  message,
  onClose,
  onSaved,
}: {
  message: EventMessage
  onClose: () => void
  onSaved: () => void
}) {
  const [draft, setDraft] = useState(toDisplay(message.content))
  const [saving, setSaving] = useState(false)
  const [testSending, setTestSending] = useState(false)
  const [note, setNote] = useState('')

  const dirty = draft !== toDisplay(message.content)

  function insertPlaceholder(label: string) {
    setDraft((d) => `${d}[${label}]`)
  }

  async function save() {
    setSaving(true)
    setNote('')
    try {
      await updateCommunicationMessage(message.message_type, { content: toRaw(draft) })
      setNote('נשמר')
      onSaved()
      onClose()
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'השמירה נכשלה')
    } finally {
      setSaving(false)
    }
  }

  async function testSend() {
    setTestSending(true)
    setNote('')
    try {
      const res = await testSendCommunicationMessage(message.message_type)
      setNote(res.sent ? 'נשלחה הודעת בדיקה לטלפון שלכם' : (res.detail || 'השליחה נכשלה'))
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'השליחה נכשלה')
    } finally {
      setTestSending(false)
    }
  }

  return (
    <div className="auto-modal-backdrop" onClick={onClose}>
      <div className="auto-modal" onClick={(e) => e.stopPropagation()}>
        <div className="auto-modal-head">
          <h3 className="clar-title">{message.title}</h3>
          <button className="btn-text" onClick={onClose}>סגירה ✕</button>
        </div>

        <textarea
          className="mb-textarea"
          rows={7}
          value={draft}
          placeholder="כתבו כאן את ההודעה…"
          onChange={(e) => setDraft(e.target.value)}
        />

        <div className="comm-var-row">
          {COMMUNICATION_VARIABLES.map((v) => (
            <button
              key={v.key}
              type="button"
              className="comm-var-btn"
              onClick={() => insertPlaceholder(v.label)}
            >
              + {v.label}
            </button>
          ))}
        </div>

        <div className="mb-actions">
          <button className="btn-primary" disabled={!dirty || saving} onClick={save}>
            {saving ? 'שומר…' : 'שמירת שינויים'}
          </button>
          <button className="btn-text" disabled={testSending} onClick={testSend}>
            {testSending ? 'שולח…' : 'שליחת הודעת בדיקה אליי'}
          </button>
          {note && <span className="mb-dirty">{note}</span>}
        </div>
      </div>
    </div>
  )
}

function PreviewModal({
  message,
  event,
  onClose,
}: {
  message: EventMessage
  event: EventDetails | null
  onClose: () => void
}) {
  const [text, setText] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [note, setNote] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    previewCommunicationMessage(message.message_type)
      .then((t) => alive && setText(t))
      .catch((err) => alive && setNote(err instanceof Error ? err.message : 'התצוגה המקדימה נכשלה'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [message.message_type])

  const showImage = message.message_type === 'invitation' && !!event?.invite_image
  const showRsvp = message.content.includes('{{rsvp_link}}')
  const showNav = message.content.includes('{{navigation_link}}')
  const showGift = message.content.includes('{{gift_link}}')

  return (
    <div className="auto-modal-backdrop" onClick={onClose}>
      <div className="auto-modal" onClick={(e) => e.stopPropagation()}>
        <div className="auto-modal-head">
          <h3 className="clar-title">{message.title} — תצוגה מקדימה</h3>
          <button className="btn-text" onClick={onClose}>סגירה ✕</button>
        </div>

        {note && <p className="form-error">{note}</p>}
        {loading && <p className="mb-empty">טוענים…</p>}

        {!loading && (
          <div className="wa-screen" dir="rtl">
            <div className="wa-bubble">
              {showImage && (
                <img className="wa-image" src={mediaUrl(event!.invite_image)} alt="" />
              )}
              <div className="wa-text">
                {text && text.trim() ? (
                  text.split('\n').map((line, i) => (
                    <div key={i} className="wa-line">{line || ' '}</div>
                  ))
                ) : (
                  <span className="wa-empty">אין עדיין הודעה להצגה</span>
                )}
              </div>
              {(showRsvp || showNav || showGift) && (
                <div className="wa-actions">
                  {showRsvp && <span className="wa-action-btn">✅ אישור הגעה</span>}
                  {showNav && <span className="wa-action-btn">🧭 ניווט</span>}
                  {showGift && <span className="wa-action-btn">🎁 מתנה באשראי</span>}
                </div>
              )}
              <span className="wa-meta">12:30 ✓✓</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
