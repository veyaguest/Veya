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
import { buildSampleTokens, renderMessagePreview } from '../lib/messagePreview'
import { strings } from '../strings/he'

const t = strings.messages

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

// מיפוי סוג ההודעה במסלול → קטגוריה בספריית ההודעות. כך כשעורכים את
// ההזמנה, בורר הספרייה נפתח ישר על ההזמנות בלבד ("ספרייה יעודית להזמנות").
const KIND_TO_CATEGORY: Record<string, string> = {
  invitation: 'invitation',
  reminder: 'reminder',
  thank_you: 'thank_you',
  pre_event: 'event_day',
}

// סדר הקבוצות בבורר הפרטים האישיים. חייב להתאים למפתחות ש-messaging.py
// שולח בשדה ``cat``; קבוצה שלא מוכרת נופלת לסוף תחת "תוספות".
const TOKEN_CAT_ORDER = ['guest', 'event', 'when_where', 'links', 'extra']

/**
 * עורך הודעות ידידותי לזוג — בוחרים הודעה מהמסלול, עורכים בטקסט פשוט עם
 * כפתורי "פרטים אישיים" ([שם פרטי] וכו'), ורואים תצוגה מקדימה בסגנון WhatsApp
 * עם נתוני האירוע האמיתיים. אין קוד טכני ({{...}}) מול הזוג.
 *
 * ``invitationOnly`` — מצב "הזמנה ראשונית בלבד": לפני שליחת ההזמנה הראשונה
 * מציגים רק את עריכת ההזמנה (בלי תזכורות/תודות), עם ספרייה יעודית להזמנות.
 * אחרי השליחה נפתח העורך המלא עם כל סוגי ההודעות.
 */
export function MessageBuilder({ invitationOnly = false }: { invitationOnly?: boolean } = {}) {
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

  // בורר הפרטים האישיים: חיפוש חופשי + סינון לפי קבוצה + קיפול קבוצות.
  const [tokenSearch, setTokenSearch] = useState('')
  const [tokenCat, setTokenCat] = useState('')
  // רק קבוצות שקופלו ידנית נשמרות כאן — ברירת המחדל היא פתוח, כדי שהמסך
  // ייראה מלא ושמיש בכניסה הראשונה ולא כרשימת כותרות סגורות.
  const [collapsedCats, setCollapsedCats] = useState<Set<string>>(new Set())

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
      // במצב "הזמנה בלבד" נבחרת אוטומטית תבנית ההזמנה (ולא הראשונה שבמיון).
      const firstInvite = sorted.find((t) => t.kind === 'invitation')
      setSelectedId(
        (cur) =>
          cur ?? (invitationOnly ? firstInvite?.id : undefined) ?? sorted[0]?.id ?? null,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.messagesLoadFailed)
    }
  }, [invitationOnly])

  useEffect(() => {
    load()
  }, [load])

  // כשספריית ההודעות פתוחה — נועלים גלילת רקע, כדי שבמובייל לא תיווצר
  // "גלילת גומיה" שמקפיצה את סרגל הדפדפן ומקשה על לחיצה על הכפתורים.
  useEffect(() => {
    if (!libOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [libOpen])

  // כשמחליפים תבנית נבחרת — טוענים את הגוף שלה לעריכה.
  useEffect(() => {
    const t = templates.find((x) => x.id === selectedId)
    setBody(t ? t.body : '')
    setNote('')
  }, [selectedId, templates])

  // ערכי דוגמה לכל טוקן שהמערכת מכירה — מקור משותף עם מסך שליחת ההזמנות,
  // כדי ששני המסכים יראו בדיוק את אותה הודעה.
  const sampleByToken = useMemo(
    () => buildSampleTokens(event, sampleGuest || 'דנה כהן'),
    [event, sampleGuest],
  )

  // תצוגה מקדימה נאמנה לשליחה בפועל (כולל מחיקת שורות ריקות ומפרידים תלויים).
  const renderPreview = useCallback(
    (text: string): string => renderMessagePreview(text, sampleByToken),
    [sampleByToken],
  )

  const previewText = useMemo(() => renderPreview(body), [renderPreview, body])

  const selected = templates.find((t) => t.id === selectedId) || null
  const isDirty = !!selected && selected.body !== body

  // הפרטים האישיים אחרי חיפוש + סינון קבוצה, מקובצים לתצוגה.
  const tokenGroups = useMemo(() => {
    const q = tokenSearch.trim()
    const usable = placeholders.filter((p) => {
      if (!p.token) return false
      if (tokenCat && (p.cat || 'extra') !== tokenCat) return false
      if (q && !(p.token.includes(q) || p.desc.includes(q))) return false
      return true
    })
    const byCat = new Map<string, TemplatePlaceholder[]>()
    for (const p of usable) {
      const key = p.cat || 'extra'
      if (!byCat.has(key)) byCat.set(key, [])
      byCat.get(key)!.push(p)
    }
    return [...byCat.entries()].sort(
      (a, b) =>
        (TOKEN_CAT_ORDER.indexOf(a[0]) + 1 || 99) - (TOKEN_CAT_ORDER.indexOf(b[0]) + 1 || 99),
    )
  }, [placeholders, tokenSearch, tokenCat])

  // הקבוצות הקיימות בפועל (לצ'יפים של הסינון), בסדר הקבוע.
  const availableCats = useMemo(() => {
    const present = new Set(placeholders.filter((p) => p.token).map((p) => p.cat || 'extra'))
    return TOKEN_CAT_ORDER.filter((c) => present.has(c))
  }, [placeholders])

  // בחיפוש פעיל כל הקבוצות נפתחות — אחרת תוצאה תואמת הייתה מסתתרת בקבוצה
  // מקופלת והמשתמש היה חושב שאין התאמה.
  const isGroupOpen = (cat: string) =>
    tokenSearch.trim() !== '' || !collapsedCats.has(cat)

  function toggleGroup(cat: string) {
    setCollapsedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

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
      setNote(strings.toasts.messageSaved)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.messageSaveFailed)
    } finally {
      setSaving(false)
    }
  }

  // פתיחת ספריית ההודעות — טוענים בעצלתיים בפעם הראשונה. מסננים אוטומטית
  // לקטגוריה שתואמת את סוג ההודעה שנערך כרגע (הזמנה → הזמנות בלבד), כדי
  // שהזוג יראה "ספרייה יעודית" לסוג ההודעה, לא ערבוב של כל הקטגוריות.
  async function openLibrary() {
    const cur = templates.find((t) => t.id === selectedId)
    setLibCat(KIND_TO_CATEGORY[cur?.kind ?? ''] ?? '')
    setLibStyle('')
    setLibSearch('')
    setLibPreviewId(null)
    setLibOpen(true)
    if (library || libLoading) return
    setLibLoading(true)
    try {
      const lib = await getMessageLibrary()
      setLibrary(lib)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.messagesLibraryLoadFailed)
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
    setNote(strings.toasts.messageLoaded)
    setTimeout(() => taRef.current?.focus(), 0)
  }

  // במצב "הזמנה בלבד" מציגים רק את תבנית ההזמנה, ומסתירים את בורר הסוגים
  // (העורך תופס את כל הרוחב) — חוויה יעודית ופשוטה לשליחה הראשונה.
  const visibleTemplates = invitationOnly
    ? templates.filter((t) => t.kind === 'invitation')
    : templates
  const showPicker = !invitationOnly

  const bubbleLines = previewText.split('\n')

  return (
    <div className="mb-wrap" dir="rtl">
      <header className="mb-head">
        <h2 className="mb-title">{invitationOnly ? t.titleInvitation : t.titleFull}</h2>
        <p className="mb-sub">
          {invitationOnly ? t.subtitleInvitation : t.subtitleFull}
        </p>
      </header>

      {error && <p className="form-error">{error}</p>}

      {templates.length === 0 ? (
        <p className="mb-empty">{t.emptyState}</p>
      ) : (
        <div className="mb-grid">
          {/* ---- כרטיס 1: איזו הודעה עורכים ---- */}
          {showPicker && (
            <section className="mb-card mb-card-picker">
              <h3 className="mb-card-title">{t.pickerTitle}</h3>
              <div className="mb-picker" role="tablist" aria-label={t.pickerTitle}>
                {visibleTemplates.map((tpl) => (
                  <button
                    key={tpl.id}
                    role="tab"
                    aria-selected={tpl.id === selectedId}
                    className={`mb-picker-item ${tpl.id === selectedId ? 'active' : ''}`}
                    onClick={() => setSelectedId(tpl.id)}
                  >
                    <span className="mb-picker-kind">
                      {KIND_LABEL[tpl.kind] ?? 'הודעה'}
                    </span>
                    <span className="mb-picker-name">{tpl.name}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* ---- כרטיס 2: עורך הנוסח ---- */}
          <section className="mb-card mb-card-editor">
            <div className="mb-card-head">
              <h3 className="mb-card-title">{t.editorTitle}</h3>
              <button type="button" className="mb-lib-btn" onClick={openLibrary}>
                📚{' '}
                {selected && KIND_TO_CATEGORY[selected.kind]
                  ? t.libraryButtonFor(KIND_LABEL[selected.kind] ?? 'הודעה')
                  : t.libraryButton}
              </button>
            </div>
            <p className="mb-card-hint">{t.editorHint}</p>

            <textarea
              ref={taRef}
              className="mb-textarea"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              dir="rtl"
              placeholder={t.editorPlaceholder}
            />

            <div className="mb-actions">
              <button
                className="btn-primary"
                onClick={onSave}
                disabled={saving || selectedId == null || !isDirty}
              >
                {saving ? t.saving : t.save}
              </button>
              {isDirty && !saving && <span className="mb-dirty">{t.unsaved}</span>}
              {note && !isDirty && <span className="tpl-saved">{note}</span>}
            </div>
          </section>

          {/* ---- כרטיס 3: תצוגה מקדימה ---- */}
          <section className="mb-card mb-card-preview">
            <h3 className="mb-card-title">{t.previewTitle}</h3>
            <div className="wa-screen">
              <div className="wa-bubble">
                {event?.invite_image && (
                  <img
                    className="wa-image"
                    src={mediaUrl(event.invite_image)}
                    alt=""
                  />
                )}
                <div className="wa-text">
                  {previewText.trim() ? (
                    bubbleLines.map((line, i) => (
                      <div key={i} className="wa-line">
                        {line || ' '}
                      </div>
                    ))
                  ) : (
                    <span className="wa-empty">{t.previewEmpty}</span>
                  )}
                </div>
                <span className="wa-meta">
                  {selected ? KIND_LABEL[selected.kind] ?? '' : ''} · {t.previewNow}
                </span>
              </div>
            </div>
            <p className="mb-preview-note">{t.previewNote}</p>
          </section>
          {/* ---- כרטיס 4: פרטים אישיים (טוקנים) ---- */}
          <section className="mb-card mb-card-tokens">
            <h3 className="mb-card-title">{t.tokensTitle}</h3>
            <p className="mb-card-hint">{t.tokensHint}</p>

            <input
              className="mb-token-search"
              value={tokenSearch}
              onChange={(e) => setTokenSearch(e.target.value)}
              placeholder={t.tokensSearch}
              dir="rtl"
              aria-label={t.tokensSearch}
            />

            <div className="mb-token-cats">
              <button
                className={`mb-cat-chip ${tokenCat === '' ? 'active' : ''}`}
                onClick={() => setTokenCat('')}
              >
                {t.tokensAll}
              </button>
              {availableCats.map((c) => (
                <button
                  key={c}
                  className={`mb-cat-chip ${tokenCat === c ? 'active' : ''}`}
                  onClick={() => setTokenCat(c)}
                >
                  {t.tokenCategories[c] ?? c}
                </button>
              ))}
            </div>

            {tokenGroups.length === 0 ? (
              <p className="mb-token-empty">{t.tokensNoResults}</p>
            ) : (
              <div className="mb-token-groups">
                {tokenGroups.map(([cat, items]) => {
                  const open = isGroupOpen(cat)
                  return (
                    <div key={cat} className={`mb-token-group ${open ? 'open' : ''}`}>
                      <button
                        type="button"
                        className="mb-token-group-toggle"
                        aria-expanded={open}
                        onClick={() => toggleGroup(cat)}
                      >
                        <h4 className="mb-token-group-title">
                          {t.tokenCategories[cat] ?? cat}
                        </h4>
                        <span className="mb-token-group-meta">
                          <span>{items.length}</span>
                          <span className="mb-token-caret" aria-hidden="true">
                            ▾
                          </span>
                        </span>
                      </button>
                      {open && (
                        <ul className="mb-token-list">
                          {items.map((p) => (
                            <li key={p.key}>
                              <button
                                type="button"
                                className="mb-token"
                                onClick={() => insertToken(p.token)}
                              >
                                <span className="mb-token-name">{p.token}</span>
                                <span className="mb-token-desc">{p.desc}</span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>

        </div>
      )}

      {libOpen && (
        <div className="lib-overlay" onClick={() => setLibOpen(false)}>
          <div
            className="lib-modal"
            dir="rtl"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="lib-head">
              <h3 className="mb-card-title">
                {libCat ? t.libraryTitleFor(catLabel(libCat)) : t.libraryTitle}
              </h3>
              <button
                type="button"
                className="lib-close"
                onClick={() => setLibOpen(false)}
                aria-label={t.close}
              >
                ✕
              </button>
            </div>

            {libLoading ? (
              <p className="mb-empty">{t.libraryLoading}</p>
            ) : (
              <>
                <div className="lib-filters">
                  <input
                    className="lib-search"
                    value={libSearch}
                    onChange={(e) => setLibSearch(e.target.value)}
                    placeholder={t.librarySearch}
                    dir="rtl"
                    aria-label={t.librarySearch}
                  />
                  <div className="lib-chips">
                    <span className="lib-chips-label">{t.libraryCategory}</span>
                    <button
                      className={`lib-chip ${libCat === '' ? 'active' : ''}`}
                      onClick={() => setLibCat('')}
                    >
                      {t.tokensAll}
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
                    <span className="lib-chips-label">{t.libraryStyle}</span>
                    <button
                      className={`lib-chip ${libStyle === '' ? 'active' : ''}`}
                      onClick={() => setLibStyle('')}
                    >
                      {t.tokensAll}
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
                      <p className="mb-empty">{t.libraryNoResults}</p>
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
                          {t.libraryPreviewOf(libPreviewMsg.name)}
                        </span>
                        <div className="wa-screen">
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
                            <span className="wa-meta">
                              {t.previewTitle} · {t.previewNow}
                            </span>
                          </div>
                        </div>
                      </>
                    ) : (
                      <p className="mb-empty">{t.libraryPickPrompt}</p>
                    )}
                  </div>
                </div>

                {/* פוטר פעולה קבוע — תמיד נגיש, גם במובייל (מעל סרגל הדפדפן). */}
                {libPreviewMsg && (
                  <div className="lib-foot">
                    <button
                      className="btn-primary lib-use"
                      onClick={() => applyLibraryMessage(libPreviewMsg)}
                    >
                      {t.libraryUse}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
