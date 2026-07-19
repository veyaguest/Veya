import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getAutomationPlaceholders,
  getEvent,
  getMessageLibrary,
  listAutomationTemplates,
  mediaUrl,
  listGuests,
  updateAutomationTemplate,
} from '../api'
import type {
  AutomationTemplate,
  EventDetails,
  LibraryMessage,
  MessageLibrary,
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

  // ספריית ההודעות (נטענת בעצלתיים בפתיחת החלון).
  const [library, setLibrary] = useState<MessageLibrary | null>(null)
  const [libOpen, setLibOpen] = useState(false)
  const [libLoading, setLibLoading] = useState(false)
  const [libCat, setLibCat] = useState<string>('')   // '' = הכול
  const [libStyle, setLibStyle] = useState<string>('') // '' = הכול
  const [libSearch, setLibSearch] = useState('')
  const [libPreviewId, setLibPreviewId] = useState<number | null>(null)

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

  // ערכי דוגמה לכל טוקן — כולל הכינויים החדשים והישנים — כדי שהתצוגה המקדימה
  // תיראה נכון גם להודעות מהספרייה וגם לתבניות ותיקות. מפה שטוחה: טוקן → ערך.
  const sampleByToken = useMemo<Record<string, string>>(() => {
    const couple =
      event && (event.groom_name || event.bride_name)
        ? `${event.groom_name} ו${event.bride_name}`
        : 'בני הזוג'
    const first = (sampleGuest || 'דנה כהן').split(/\s+/)[0]
    const date = event?.event_date || 'תאריך האירוע'
    const time = event?.event_time || 'שעה'
    const venue = event?.venue_name || 'שם האולם'
    const addr = event?.venue_address || 'כתובת האולם'
    const nav = 'קישור ניווט'
    const rsvp = 'קישור אישי לאישור הגעה'
    return {
      // שם פרטי (חדש + ישן)
      '{{first_name}}': first, '{{guest_name}}': first,
      '[שם פרטי]': first, '[שם אורח]': first,
      // כלה/חתן
      '{{bride_name}}': event?.bride_name || 'הכלה', '[שם הכלה]': event?.bride_name || 'הכלה',
      '{{groom_name}}': event?.groom_name || 'החתן', '[שם החתן]': event?.groom_name || 'החתן',
      // שמות בני הזוג
      '{{event_name}}': couple, '{{couple_names}}': couple, '[שמות בני הזוג]': couple,
      // תאריך / שעה
      '{{event_date}}': date, '[תאריך]': date, '[תאריך האירוע]': date,
      '{{event_time}}': time, '[שעה]': time,
      // אולם / כתובת
      '{{venue_name}}': venue, '[שם האולם]': venue,
      '{{venue_address}}': addr, '[כתובת]': addr,
      // קישורים
      '{{confirmation_link}}': rsvp, '{{rsvp_link}}': rsvp, '[קישור אישור]': rsvp,
      '{{navigation_link}}': nav, '{{maps_link}}': nav, '[קישור ניווט]': nav,
      '{{waze_link}}': nav, '[קישור וייז]': nav,
      // שולחן / כמות
      '{{table_number}}': '12', '[מספר שולחן]': '12',
      '{{guest_count}}': '2', '[כמות מקומות]': '2',
      // מתנה / גלריות
      '{{gift_link}}': 'קישור למתנה', '[קישור מתנה]': 'קישור למתנה',
      '{{photo_gallery}}': 'גלריית תמונות', '[גלריית תמונות]': 'גלריית תמונות',
      '{{video_gallery}}': 'גלריית וידאו', '[גלריית וידאו]': 'גלריית וידאו',
    }
  }, [event, sampleGuest])

  // ממיר גוף כלשהו לתצוגה מקדימה. מחליף טוקנים ארוכים לפני קצרים כדי ש-
  // "[תאריך האירוע]" לא ייחתך ל-"[תאריך]".
  const renderPreview = useCallback(
    (text: string): string => {
      const tokens = Object.keys(sampleByToken).sort((a, b) => b.length - a.length)
      let out = text
      for (const tok of tokens) {
        if (out.includes(tok)) out = out.split(tok).join(sampleByToken[tok])
      }
      return out
    },
    [sampleByToken],
  )

  const previewText = useMemo(() => renderPreview(body), [renderPreview, body])

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

  // פתיחת ספריית ההודעות — טוענים בעצלתיים בפעם הראשונה.
  async function openLibrary() {
    setLibOpen(true)
    if (library || libLoading) return
    setLibLoading(true)
    try {
      const lib = await getMessageLibrary()
      setLibrary(lib)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את ספריית ההודעות')
      setLibOpen(false)
    } finally {
      setLibLoading(false)
    }
  }

  // ההודעות שתואמות לסינון הנוכחי (קטגוריה + סגנון + חיפוש חופשי).
  const libFiltered = useMemo<LibraryMessage[]>(() => {
    if (!library) return []
    const q = libSearch.trim()
    return library.messages.filter((m) => {
      if (libCat && m.category !== libCat) return false
      if (libStyle && m.style !== libStyle) return false
      if (q && !(m.name.includes(q) || m.body.includes(q))) return false
      return true
    })
  }, [library, libCat, libStyle, libSearch])

  const catLabel = (key: string) =>
    library?.categories.find((c) => c.key === key)?.label ?? key
  const styleLabel = (key: string) =>
    library?.styles.find((s) => s.key === key)?.label ?? key

  const libPreviewMsg = libFiltered.find((m) => m.id === libPreviewId) || null

  // בחירת הודעה מהספרייה — טוענים אותה לעורך (לא שומרים עדיין, הזוג יכול לערוך).
  function applyLibraryMessage(m: LibraryMessage) {
    setBody(m.body)
    setLibOpen(false)
    setLibPreviewId(null)
    setNote('הודעה נטענה מהספרייה — אפשר לערוך ואז לשמור')
    setTimeout(() => taRef.current?.focus(), 0)
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
            <div className="mb-editor-bar">
              <button type="button" className="mb-lib-btn" onClick={openLibrary}>
                📚 בחירה מספריית ההודעות
              </button>
              <span className="mb-editor-hint">
                בחרו נוסח מוכן ומעוצב, או כתבו בעצמכם למטה
              </span>
            </div>

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
                      src={mediaUrl(event.invite_image)}
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

      {libOpen && (
        <div className="lib-overlay" onClick={() => setLibOpen(false)}>
          <div
            className="lib-modal"
            dir="rtl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="lib-head">
              <h3 className="clar-title">ספריית ההודעות</h3>
              <button
                type="button"
                className="lib-close"
                onClick={() => setLibOpen(false)}
                aria-label="סגירה"
              >
                ✕
              </button>
            </div>

            {libLoading ? (
              <p className="mb-empty">טוען הודעות…</p>
            ) : (
              <>
                <div className="lib-filters">
                  <input
                    className="lib-search"
                    value={libSearch}
                    onChange={(e) => setLibSearch(e.target.value)}
                    placeholder="חיפוש חופשי בהודעות…"
                    dir="rtl"
                  />
                  <div className="lib-chips">
                    <span className="lib-chips-label">קטגוריה:</span>
                    <button
                      className={`lib-chip ${libCat === '' ? 'active' : ''}`}
                      onClick={() => setLibCat('')}
                    >
                      הכול
                    </button>
                    {library?.categories.map((c) => (
                      <button
                        key={c.key}
                        className={`lib-chip ${libCat === c.key ? 'active' : ''}`}
                        onClick={() => setLibCat(c.key)}
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                  <div className="lib-chips">
                    <span className="lib-chips-label">סגנון:</span>
                    <button
                      className={`lib-chip ${libStyle === '' ? 'active' : ''}`}
                      onClick={() => setLibStyle('')}
                    >
                      הכול
                    </button>
                    {library?.styles.map((s) => (
                      <button
                        key={s.key}
                        className={`lib-chip ${libStyle === s.key ? 'active' : ''}`}
                        onClick={() => setLibStyle(s.key)}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="lib-body">
                  <div className="lib-list">
                    {libFiltered.length === 0 ? (
                      <p className="mb-empty">לא נמצאו הודעות מתאימות לסינון</p>
                    ) : (
                      libFiltered.map((m) => (
                        <button
                          key={m.id}
                          className={`lib-item ${m.id === libPreviewId ? 'active' : ''}`}
                          onClick={() => setLibPreviewId(m.id)}
                        >
                          <span className="lib-item-name">{m.name}</span>
                          <span className="lib-item-tags">
                            <span className="lib-tag">{catLabel(m.category)}</span>
                            <span className="lib-tag alt">{styleLabel(m.style)}</span>
                          </span>
                          <span className="lib-item-snippet">
                            {m.body.replace(/\n+/g, ' · ').slice(0, 70)}…
                          </span>
                        </button>
                      ))
                    )}
                  </div>

                  <div className="lib-preview">
                    {libPreviewMsg ? (
                      <>
                        <span className="mb-preview-label">
                          תצוגה מקדימה — {libPreviewMsg.name}
                        </span>
                        <div className="wa-screen" dir="rtl">
                          <div className="wa-bubble">
                            <div className="wa-text">
                              {renderPreview(libPreviewMsg.body)
                                .split('\n')
                                .map((line, i) => (
                                  <div key={i} className="wa-line">
                                    {line || ' '}
                                  </div>
                                ))}
                            </div>
                            <span className="wa-meta">כך זה ייראה למוזמן · עכשיו</span>
                          </div>
                        </div>
                        <button
                          className="btn-primary lib-use"
                          onClick={() => applyLibraryMessage(libPreviewMsg)}
                        >
                          השתמשו בהודעה זו
                        </button>
                      </>
                    ) : (
                      <p className="mb-empty">בחרו הודעה מהרשימה כדי לראות תצוגה מקדימה</p>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
