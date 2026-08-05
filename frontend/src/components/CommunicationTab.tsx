import { useEffect, useState } from 'react'
import {
  getCommunicationSequence,
  previewCommunicationMessage,
  testSendCommunicationMessage,
  updateCommunicationMessage,
} from '../api'
import type { EventMessage } from '../types'
import { COMMUNICATION_VARIABLES } from '../types'

/**
 * "תקשורת עם אורחים" — רצף ההודעות הקבוע של האירוע, במקום אחד. מחליף את
 * ספריית ההודעות/הלשוניות הישנות (אוטומציות/תבניות/תור/ידני): 6 כרטיסים
 * קבועים לפי סוג האירוע, שכל אחד מהם עורכים/מפעילים/כבים/בודקים בנפרד.
 *
 * שלב 1 (תשתית בלבד): התוכן עצמו עדיין ריק — הבעלים יזין את הטקסטים
 * הסופיים בהמשך. הכרטיס מציג placeholder ברור כל עוד אין תוכן, אבל כל
 * שאר התשתית (עריכה/הפעלה/תצוגה מקדימה/שליחת בדיקה) כבר עובדת.
 */
export function CommunicationTab() {
  const [messages, setMessages] = useState<EventMessage[] | null>(null)
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      const seq = await getCommunicationSequence()
      setMessages(seq)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת רצף ההודעות נכשלה')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <div className="mb-wrap">
      <div className="mb-head">
        <h2 className="mb-title">תקשורת עם אורחים</h2>
        <p className="mb-sub">
          כל רצף ההודעות של האירוע — מהזמנה ועד תודה — במקום אחד. הרצף נוצר
          אוטומטית לפי סוג האירוע; אפשר לערוך, לכבות ולבדוק כל הודעה בנפרד.
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}
      {messages === null && !error && <p className="mb-empty">טוענים…</p>}

      {messages && (
        <div className="comm-list">
          {messages.map((m) => (
            <MessageCard key={m.message_type} message={m} onSaved={refresh} />
          ))}
        </div>
      )}
    </div>
  )
}

function MessageCard({
  message,
  onSaved,
}: {
  message: EventMessage
  onSaved: () => void
}) {
  const [content, setContent] = useState(message.content)
  const [active, setActive] = useState(message.is_active)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [testSending, setTestSending] = useState(false)

  const dirty = content !== message.content || active !== message.is_active

  async function save() {
    setSaving(true)
    setNote('')
    try {
      await updateCommunicationMessage(message.message_type, { content, is_active: active })
      setNote('נשמר')
      setPreview(null)
      onSaved()
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'השמירה נכשלה')
    } finally {
      setSaving(false)
    }
  }

  async function showPreview() {
    setPreviewLoading(true)
    try {
      const text = await previewCommunicationMessage(message.message_type)
      setPreview(text)
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'התצוגה המקדימה נכשלה')
    } finally {
      setPreviewLoading(false)
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

  function insertVariable(key: string) {
    setContent((c) => `${c}{{${key}}}`)
  }

  return (
    <div className={`mb-card comm-card ${active ? '' : 'comm-card-off'}`}>
      <div className="mb-card-head">
        <h3 className="mb-card-title">{message.title}</h3>
        <label className="comm-active-toggle">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          פעיל
        </label>
      </div>

      {!message.content && (
        <p className="mb-card-hint">עדיין לא הוזן תוכן להודעה הזו.</p>
      )}

      <textarea
        className="mb-textarea"
        rows={5}
        value={content}
        placeholder="כתבו כאן את נוסח ההודעה…"
        onChange={(e) => setContent(e.target.value)}
      />

      <div className="comm-var-row">
        {COMMUNICATION_VARIABLES.map((v) => (
          <button
            key={v.key}
            type="button"
            className="comm-var-btn"
            onClick={() => insertVariable(v.key)}
            title={`{{${v.key}}}`}
          >
            + {v.label}
          </button>
        ))}
      </div>

      <div className="mb-actions">
        <button className="btn-primary" disabled={!dirty || saving} onClick={save}>
          {saving ? 'שומר…' : 'שמירה'}
        </button>
        <button className="btn-ghost" disabled={previewLoading} onClick={showPreview}>
          {previewLoading ? 'טוען…' : 'תצוגה מקדימה'}
        </button>
        <button className="btn-text" disabled={testSending} onClick={testSend}>
          {testSending ? 'שולח…' : 'שליחה לבדיקה'}
        </button>
        {dirty && <span className="mb-dirty">יש שינויים שלא נשמרו</span>}
        {note && <span className="mb-dirty">{note}</span>}
      </div>

      {preview !== null && (
        <div className="mb-card-preview">
          <span className="mb-preview-label">תצוגה מקדימה</span>
          <div className="wa-screen">
            <div className="wa-bubble">
              {preview ? (
                <span className="wa-text">{preview}</span>
              ) : (
                <span className="wa-text wa-empty">אין עדיין תוכן להצגה</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
