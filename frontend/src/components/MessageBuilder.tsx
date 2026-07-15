import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getAutomationPlaceholders,
  getEvent,
  listAutomationTemplates,
  listGuests,
  updateAutomationTemplate,
} from '../api'
import type {
  AutomationTemplate,
  EventDetails,
  TemplatePlaceholder,
} from '../types'

// סדר תצוגה ידידותי של סוגי ההודעות במסלול (kind של MessageTemplate).
const KIND_ORDER: Record<string, number> = {
  invitation: 0,
  reminder: 1,
  thank_you: 2,
  pre_event: 3,
  custom: 9,
}

const KIND_LABEL: Record<string, string> = {
  invitation: 'הזמנה',
  reminder: 'תזכורת',
  thank_you: 'תודה על האישור',
  pre_event: 'לפני האירוע',
  custom: 'הודעה נוספת',
}

/**
 * עורך הודעות ידידותי לזוג — בוחרים הודעה מהמסלול, עורכים בטקסט פשוט עם
 * כפתורי "כינויים" ([שם אורח] וכו'), ורואים תצוגה מקדימה בסגנון WhatsApp
 * עם נתוני האירוע האמיתיים. אין קוד טכני ({{...}}) מול הזוג.
 */
export function MessageBuilder() {
  const [templates, setTemplates] = useState<AutomationTemplate[]>([])
  const [placeholders, setPlaceholders] = useState<TemplatePlaceholder[]>([])
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [sampleGuest, setSampleGuest] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  const load = useCallback(async () => {
    try {
      const [tpls, phs, ev, g] = await Promise.all([
        listAutomationTemplates(),
        getAutomationPlaceholders(),
        getEvent(),
        listGuests('', 1, 0),
      ])
      const sorted = [...tpls].sort(
        (a, b) => (KIND_ORDER[a.kind] ?? 5) - (KIND_ORDER[b.kind] ?? 5),
      )
      setTemplates(sorted)
      setPlaceholders(phs)
      setEvent(ev)
      setSampleGuest(g.items[0]?.full_name || 'דנה כהן')
      setSelectedId((cur) => cur ?? sorted[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את ההודעות, ננסה שוב')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // כשמחליפים תבנית נבחרת — טוענים את הגוף שלה לעריכה.
  useEffect(() => {
    const t = templates.find((x) => x.id === selectedId)
    setBody(t ? t.body : '')
    setNote('')
  }, [selectedId, templates])

  // ערכי דוגמה לכל משתנה — להצגת תצוגה מקדימה אמיתית.
  const sampleByKey = useMemo<Record<string, string>>(() => {
    const couple =
      event && (event.groom_name || event.bride_name)
        ? `${event.groom_name} ו${event.bride_name}`
        : 'בני הזוג'
    return {
      '{{guest_name}}': sampleGuest || 'דנה כהן',
      '{{couple_names}}': couple,
      '{{event_date}}': event?.event_date || 'תאריך האירוע',
      '{{event_time}}': event?.event_time || 'שעה',
      '{{venue_name}}': event?.venue_name || 'שם האולם',
      '{{venue_address}}': event?.venue_address || 'כתובת האולם',
      '{{maps_link}}': 'ניווט באמצעות Waze / Google Maps',
      '{{rsvp_link}}': 'קישור אישי לאישור הגעה',
    }
  }, [event, sampleGuest])

  // המרה של הגוף (עם כינויים ידידותיים או {{...}}) לטקסט תצוגה מקדימה.
  const previewText = useMemo(() => {
    let text = body
    for (const p of placeholders) {
      const val = sampleByKey[p.key] ?? ''
      if (p.token) text = text.split(p.token).join(val)
      text = text.split(p.key).join(val)
    }
    return text
  }, [body, placeholders, sampleByKey])

  function insertToken(token: string) {
    const ta = taRef.current
    if (!ta) {
      setBody((b) => b + token)
      return
    }
    const start = ta.selectionStart
    const end = ta.selectionEnd
    setBody((b) => b.slice(0, start) + token + b.slice(end))
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + token.length
    }, 0)
  }

  async function onSave() {
    if (selectedId == null) return
    setSaving(true)
    setError('')
    setNote('')
    try {
      const updated = await updateAutomationTemplate(selectedId, { body })
      setTemplates((list) =>
        list.map((t) => (t.id === updated.id ? updated : t)),
      )
      setNote('שמרנו את ההודעה ✓')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור, נסו שוב')
    } finally {
      setSaving(false)
    }
  }

  const selected = templates.find((t) => t.id === selectedId) || null

  return (
    <div className="mb-wrap">
      <div className="mb-head">
        <h3 className="clar-title">עריכת ההודעות שלכם</h3>
        <span className="clar-sub">
          בחרו הודעה, ערכו את הנוסח, והוסיפו פרטים אישיים בלחיצה. כך זה ייראה
          למוזמנים ב-WhatsApp.
        </span>
      </div>

      {error && <p className="form-error">{error}</p>}

      {templates.length === 0 ? (
        <p className="mb-empty">
          ההודעות ייווצרו אוטומטית ברגע שתפעילו את מסלול אישורי ההגעה.
        </p>
      ) : (
        <div className="mb-layout">
          {/* ספריית ההודעות במסלול */}
          <aside className="mb-list">
            {templates.map((t) => (
              <button
                key={t.id}
                className={`mb-list-item ${t.id === selectedId ? 'active' : ''}`}
                onClick={() => setSelectedId(t.id)}
              >
                <span className="mb-list-kind">
                  {KIND_LABEL[t.kind] ?? 'הודעה'}
                </span>
                <span className="mb-list-name">{t.name}</span>
              </button>
            ))}
          </aside>

          {/* עורך + תצוגה מקדימה */}
          <div className="mb-editor">
            <div className="mb-tokens">
              {placeholders
                .filter((p) => p.token)
                .map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    className="mb-token-chip"
                    title={p.desc}
                    onClick={() => insertToken(p.token)}
                  >
                    + {p.token}
                  </button>
                ))}
            </div>

            <textarea
              ref={taRef}
              className="mb-textarea"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              dir="rtl"
              placeholder="כתבו כאן את ההודעה למוזמנים…"
            />

            <div className="mb-actions">
              <button
                className="btn-primary"
                onClick={onSave}
                disabled={saving || selectedId == null}
              >
                {saving ? 'שומר…' : 'שמירת ההודעה'}
              </button>
              {note && <span className="tpl-saved">{note}</span>}
            </div>

            {/* תצוגת WhatsApp */}
            <div className="mb-preview">
              <span className="mb-preview-label">כך זה ייראה למוזמן</span>
              <div className="wa-screen" dir="rtl">
                <div className="wa-bubble">
                  {event?.invite_image && (
                    <img
                      className="wa-image"
                      src={event.invite_image}
                      alt="הזמנה"
                    />
                  )}
                  <div className="wa-text">
                    {previewText.trim() ? (
                      previewText.split('\n').map((line, i) => (
                        <div key={i} className="wa-line">
                          {line || ' '}
                        </div>
                      ))
                    ) : (
                      <span className="wa-empty">אין עדיין נוסח להודעה</span>
                    )}
                  </div>
                  <span className="wa-meta">
                    {selected ? KIND_LABEL[selected.kind] ?? '' : ''} · עכשיו
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
