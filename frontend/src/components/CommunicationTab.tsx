import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  getCommunicationSequence,
  getEvent,
  getMessageOptions,
  mediaUrl,
  previewCommunicationMessage,
  updateCommunicationMessage,
} from '../api'
import type { EventDetails, EventMessage, MessageDefaultOption, MessageType } from '../types'
import { MESSAGE_TYPE_ICONS } from '../types'
import { EVENT_TERMS } from '../strings/eventTypes'

const STEP_ICON = MESSAGE_TYPE_ICONS

/**
 * באילו שלבים תמונת ההזמנה נלווית להודעה — מקור אמת יחיד לכלל הזה.
 *
 * ההזמנה וכל התזכורות נושאות את התמונה, כדי שהאורח יזהה את האירוע מיד גם
 * בהודעה השלישית ולא רק בראשונה. "תודה" נשלחת אחרי האירוע, ושם התמונה כבר
 * לא מוסיפה — לכן היא היחידה בלעדיה. זה קורה מאליו: אין כאן הגדרה שהזוג
 * צריך לסמן.
 */
const STEPS_WITH_INVITE_IMAGE: ReadonlySet<MessageType> = new Set<MessageType>([
  'invitation', 'reminder_1', 'reminder_2', 'final_reminder', 'event_day',
])

/** מילה טבעית לכל פרט משתנה — מוצגת כשעדיין אין ערך אמיתי לאירוע. */
const FIELD_WORD: Record<string, string> = {
  guest_name: 'שם האורח',
  guest_names: 'שם האורח',
  host_names: 'השמות שלכם',
  groom_name: 'שם החתן',
  bride_name: 'שם הכלה',
  event_type: 'סוג האירוע',
  event_date: 'תאריך',
  event_time: 'שעה',
  venue_name: 'שם המקום',
  address: 'כתובת',
  navigation_link: 'ניווט',
  rsvp_link: 'אישור הגעה',
  table_number: 'מספר שולחן',
  gift_link: 'מתנה',
}

const VAR_RE = /\{\{\s*(\w+)\s*\}\}/g

/**
 * הפרטים האמיתיים של האירוע, לפי שם הפרט בתוך ההודעה. ריק במקום שעדיין אין
 * בו נתון — ואז מוצגת המילה הטבעית מ-FIELD_WORD במקום.
 *
 * הקישורים (אישור הגעה/ניווט/מתנה) נשארים תמיד כמילה ולא ככתובת: הכתובת
 * שונה לכל אורח, ואין שום סיבה שהזוג יראה אותה בזמן הכתיבה.
 */
function eventFieldValues(event: EventDetails | null): Record<string, string> {
  if (!event) return {}
  const terms = EVENT_TERMS[event.event_type] ?? EVENT_TERMS.wedding
  const a = (event.groom_name || '').trim()
  const b = (event.bride_name || '').trim()
  const hosts = terms.hasTwoHosts ? [a, b].filter(Boolean).join(' ו') : a || b
  return {
    host_names: hosts,
    groom_name: a,
    bride_name: b,
    event_type: terms.celebration,
    event_date: event.event_date || '',
    event_time: event.event_time || '',
    venue_name: event.venue_name || '',
    address: event.venue_address || '',
  }
}

type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'field'; key: string; shown: string }

/** מפרק תוכן הודעה לקטעי טקסט חופשי ולפרטים שהמערכת ממלאת בעצמה. */
function splitToSegments(content: string, values: Record<string, string>): Segment[] {
  const out: Segment[] = []
  let last = 0
  for (const m of content.matchAll(VAR_RE)) {
    const at = m.index ?? 0
    if (at > last) out.push({ kind: 'text', text: content.slice(last, at) })
    const key = m[1]
    out.push({ kind: 'field', key, shown: values[key] || FIELD_WORD[key] || key })
    last = at + m[0].length
  }
  if (last < content.length) out.push({ kind: 'text', text: content.slice(last) })
  return out
}

/** ההודעה כטקסט קריא לתצוגה בכרטיס — בלי שום סימון טכני. */
function asReadableText(content: string, values: Record<string, string>): string {
  return splitToSegments(content, values)
    .map((s) => (s.kind === 'text' ? s.text : s.shown))
    .join('')
}

export function CommunicationTab() {
  const [messages, setMessages] = useState<EventMessage[] | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [activeType, setActiveType] = useState<MessageType>('invitation')
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      const [seq, ev] = await Promise.all([
        getCommunicationSequence(),
        getEvent().catch(() => null),
      ])
      setMessages(seq)
      if (ev) setEvent(ev)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת ההודעות נכשלה')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const active = messages?.find((m) => m.message_type === activeType) ?? null

  return (
    <div className="gm2-wrap">
      <div className="gm2-head">
        <h2 className="gm2-title">💬 הודעות לאורחים</h2>
      </div>

      {error && <p className="form-error">{error}</p>}
      {messages === null && !error && <p className="mb-empty">טוענים…</p>}

      {messages && (
        <>
          <nav className="gm2-steps" aria-label="שלבי ההודעות">
            {messages.map((m) => (
              <button
                key={m.message_type}
                type="button"
                className={`gm2-step ${m.message_type === activeType ? 'active' : ''}`}
                onClick={() => setActiveType(m.message_type)}
              >
                <span className="gm2-step-icon" aria-hidden="true">
                  {STEP_ICON[m.message_type]}
                </span>
                <span className="gm2-step-name">{m.title}</span>
              </button>
            ))}
          </nav>

          {active && (
            <MessagePanel
              key={active.message_type}
              message={active}
              event={event}
              onSaved={refresh}
            />
          )}
        </>
      )}
    </div>
  )
}

type Mode = 'view' | 'browse' | 'edit'

function MessagePanel({
  message,
  event,
  onSaved,
}: {
  message: EventMessage
  event: EventDetails | null
  onSaved: () => void
}) {
  const [mode, setMode] = useState<Mode>('view')
  const [options, setOptions] = useState<MessageDefaultOption[] | null>(null)
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [index, setIndex] = useState(0)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  // דרך מילוט נוספת מהתצוגה המקדימה, מעבר לרקע ולכפתור הסגירה.
  useEffect(() => {
    if (!showPreview) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowPreview(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showPreview])

  const wide = useWideScreen()

  const values = useMemo(() => eventFieldValues(event), [event])
  const readable = asReadableText(message.content, values)

  async function startBrowsing() {
    setMode('browse')
    setNote('')
    if (options === null) {
      setLoadingOptions(true)
      try {
        const rows = await getMessageOptions(message.message_type)
        setOptions(rows)
        const at = rows.findIndex((o) => o.content === message.content)
        setIndex(at >= 0 ? at : 0)
      } catch (err) {
        setNote(err instanceof Error ? err.message : 'טעינת ההודעות נכשלה')
      } finally {
        setLoadingOptions(false)
      }
    } else {
      const at = options.findIndex((o) => o.content === message.content)
      setIndex(at >= 0 ? at : 0)
    }
  }

  async function save(content: string) {
    setBusy(true)
    setNote('')
    try {
      await updateCommunicationMessage(message.message_type, { content })
      setMode('view')
      onSaved()
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'השמירה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  const current = options && options.length > 0 ? options[index] : null
  const isCurrentChosen = !!current && current.content === message.content

  return (
    <div className="gm2-stage">
      <section className="gm2-card">
        <header className="gm2-card-head">
          <span className="gm2-card-icon" aria-hidden="true">
            {STEP_ICON[message.message_type]}
          </span>
          <h3 className="gm2-card-title">{message.title}</h3>
        </header>

        {mode === 'view' && (
          <>
            {readable.trim() ? (
              <p className="gm2-text">{readable}</p>
            ) : (
              <p className="gm2-text gm2-text-empty">
                עדיין לא בחרתם הודעה לשלב הזה.
              </p>
            )}

            <div className="gm2-actions">
              <button type="button" className="gm2-btn gm2-btn-main" onClick={startBrowsing}>
                {readable.trim() ? 'בחירת הודעה אחרת' : 'בחירת הודעה'}
              </button>
              <button
                type="button"
                className="gm2-btn"
                onClick={() => {
                  setNote('')
                  setMode('edit')
                }}
              >
                ✏️ עריכה
              </button>
              {!wide && (
                <button
                  type="button"
                  className="gm2-btn gm2-btn-quiet"
                  onClick={() => setShowPreview(true)}
                >
                  👀 תצוגה מקדימה
                </button>
              )}
            </div>
          </>
        )}

        {mode === 'browse' && (
          <>
            {loadingOptions && <p className="mb-empty">טוענים…</p>}
            {!loadingOptions && options !== null && options.length === 0 && (
              <p className="gm2-text gm2-text-empty">
                עדיין אין הודעות מוכנות לשלב הזה.
              </p>
            )}
            {current && (
              <>
                <p className="gm2-text">{asReadableText(current.content, values)}</p>

                <div className="gm2-nav">
                  <button
                    type="button"
                    className="gm2-arrow"
                    disabled={index === 0}
                    onClick={() => setIndex((i) => Math.max(0, i - 1))}
                    aria-label="הקודמת"
                  >
                    →
                  </button>
                  <span className="gm2-counter">
                    {index + 1} מתוך {options!.length}
                  </span>
                  <button
                    type="button"
                    className="gm2-arrow"
                    disabled={index >= options!.length - 1}
                    onClick={() => setIndex((i) => Math.min(options!.length - 1, i + 1))}
                    aria-label="הבאה"
                  >
                    ←
                  </button>
                </div>

                <div className="gm2-actions">
                  <button
                    type="button"
                    className="gm2-btn gm2-btn-main"
                    disabled={busy || isCurrentChosen}
                    onClick={() => save(current.content)}
                  >
                    {isCurrentChosen ? '✓ ההודעה שבחרתם' : '✓ בחירת ההודעה הזו'}
                  </button>
                  <button
                    type="button"
                    className="gm2-btn gm2-btn-quiet"
                    onClick={() => setMode('view')}
                  >
                    חזרה
                  </button>
                </div>
              </>
            )}
          </>
        )}

        {mode === 'edit' && (
          <Editor
            content={message.content}
            values={values}
            busy={busy}
            onCancel={() => setMode('view')}
            onSave={save}
          />
        )}

        {note && <p className="gm2-note">{note}</p>}
      </section>

      {/* במסך רחב התצוגה פשוט נמצאת שם, בגובה מלא — ולכן אין בה צורך בכפתור.
          במובייל אין מקום לזה לצד הכרטיס, ושם היא נפתחת מהכפתור. */}
      {wide && (
        <aside className="gm2-side">
          <FittedPhone message={message} event={event} />
          <p className="gm2-side-cap">👀 כך האורחים יראו את ההודעה</p>
        </aside>
      )}

      {/* מוגש ישירות ל-body: אב עם transform (כמו .wiz-panel של אשף
          ההזמנה הראשונה) הופך להיות מסגרת הייחוס של position:fixed, והיריעה
          הייתה נפתחת הרחק מתחת למסך במקום למרכזו. */}
      {!wide && showPreview &&
        createPortal(
          <div className="gm2-sheet-backdrop" onClick={() => setShowPreview(false)}>
            <div className="gm2-sheet" onClick={(e) => e.stopPropagation()}>
              <div className="gm2-sheet-head">
                <h3 className="gm2-card-title">כך האורחים יראו את ההודעה</h3>
                <button
                  type="button"
                  className="gm2-sheet-close"
                  onClick={() => setShowPreview(false)}
                  aria-label="סגירה"
                >
                  ✕
                </button>
              </div>
              <FittedPhone message={message} event={event} />
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}

/**
 * עריכת ההודעה. הזוג כותב טקסט רגיל לגמרי; הפרטים שהמערכת ממלאת לבד (שם
 * האורח, התאריך, קישור אישור ההגעה) מוצגים כגלולה קטנה עם הערך האמיתי,
 * ולא כקוד. הגלולה נשמרת כיחידה אחת — כך ההודעה נשארת אישית לכל אורח גם
 * אחרי שהזוג שינה את הניסוח סביבה.
 */
function Editor({
  content,
  values,
  busy,
  onCancel,
  onSave,
}: {
  content: string
  values: Record<string, string>
  busy: boolean
  onCancel: () => void
  onSave: (content: string) => void
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    box.textContent = ''
    for (const seg of splitToSegments(content, values)) {
      if (seg.kind === 'text') {
        box.appendChild(document.createTextNode(seg.text))
      } else {
        const chip = document.createElement('span')
        chip.className = 'gm2-chip'
        chip.contentEditable = 'false'
        chip.dataset.field = seg.key
        chip.textContent = seg.shown
        box.appendChild(chip)
      }
    }
  }, [content, values])

  function readBack(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? ''
    if (node.nodeType !== Node.ELEMENT_NODE) return ''
    const el = node as HTMLElement
    if (el.dataset.field) return `{{${el.dataset.field}}}`
    if (el.tagName === 'BR') return '\n'
    let out = ''
    for (const child of Array.from(el.childNodes)) out += readBack(child)
    // כל בלוק שהדפדפן יוצר בלחיצת Enter מסתיים בשורה חדשה.
    if (['DIV', 'P'].includes(el.tagName)) out += '\n'
    return out
  }

  function submit() {
    const box = boxRef.current
    if (!box) return
    let out = ''
    for (const child of Array.from(box.childNodes)) out += readBack(child)
    onSave(out.replace(/\n$/, ''))
  }

  return (
    <>
      <div
        ref={boxRef}
        className="gm2-editor"
        contentEditable
        role="textbox"
        aria-multiline="true"
        aria-label="נוסח ההודעה"
        dir="rtl"
        onInput={() => setDirty(true)}
        suppressContentEditableWarning
      />
      <div className="gm2-actions">
        <button
          type="button"
          className="gm2-btn gm2-btn-main"
          disabled={busy || !dirty}
          onClick={submit}
        >
          {busy ? 'שומר…' : 'שמירת שינויים'}
        </button>
        <button type="button" className="gm2-btn gm2-btn-quiet" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </>
  )
}

/** גבול ההקטנה של התצוגה המקדימה: מתחת לזה הטקסט כבר קטן מכדי לקרוא. */
const MIN_PREVIEW_SCALE = 0.72

/** רוחב שממנו התצוגה נכנסת לעמודה שלצד הכרטיס. תואם ל-CSS. */
const WIDE_QUERY = '(min-width: 1040px)'

/**
 * מוקאפ הטלפון עם ההודעה כפי שהאורח יקבל אותה.
 *
 * המכשיר שומר על פרופורציות של טלפון אמיתי (``PHONE_ASPECT``) וממלא את
 * הגובה הפנוי — הוא לעולם לא נמתח לפי אורך ההודעה. כשההודעה ארוכה מדי
 * למסך, מה שמוקטן הוא *התוכן* בתוך הבועה ולא המכשיר: כך הכל עדיין נכנס
 * בלי גלילה, אבל הטלפון ממשיך להיראות כמו טלפון.
 *
 * ההקטנה נעצרת ב-``MIN_PREVIEW_SCALE``; מתחת לזה עדיף לתת לגלול בתוך
 * הצ'אט, בדיוק כמו במכשיר אמיתי, מאשר להציג טקסט שאי אפשר לקרוא.
 */
function FittedPhone({
  message,
  event,
}: {
  message: EventMessage
  event: EventDetails | null
}) {
  const chatRef = useRef<HTMLDivElement>(null)
  const bubbleRef = useRef<HTMLDivElement>(null)
  const [fitted, setFitted] = useState({ scale: 0, height: 0 })
  const text = usePreviewText(message)

  const measure = useCallback(() => {
    const chat = chatRef.current
    const bubble = bubbleRef.current
    if (!chat || !bubble) return
    // clientHeight כולל את ה-padding של הצ'אט; המקום שהבועה באמת מקבלת הוא
    // תיבת התוכן בלבד, אחרת נשאר עודף בגובה ה-padding והצ'אט עדיין נגלל.
    const cs = getComputedStyle(chat)
    const available =
      chat.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)
    // הבועה נמדדת תמיד בגודלה המלא — transform אינו משפיע על offsetHeight.
    const needed = bubble.offsetHeight
    if (!available || !needed) return
    const next = {
      scale: Math.max(Math.min(1, available / needed), MIN_PREVIEW_SCALE),
      height: needed,
    }
    // חובה לצאת כשאין שינוי אמיתי: העדכון משנה את הפריסה של הבועה, מה
    // שמעיר שוב את המשקיף — ואובייקט חדש בכל פעם היה סוגר לולאת רינדור
    // אינסופית שמקפיאה את המסך.
    setFitted((prev) =>
      Math.abs(prev.scale - next.scale) < 0.001 &&
      Math.abs(prev.height - next.height) < 0.5
        ? prev
        : next,
    )
  }, [])

  // המידה משתנה כשהנוסח מגיע מהשרת, כשתמונת ההזמנה נטענת (onLoad למטה),
  // וכששטח התצוגה עצמו משתנה. ה-rAF תופס את הפריים שאחרי הפריסה, שבו
  // הגבהים כבר סופיים.
  useLayoutEffect(() => {
    measure()
    const raf = requestAnimationFrame(measure)
    window.addEventListener('resize', measure)
    // תוספת ליתר ביטחון לשינויי גובה שאינם מגיעים עם אירוע resize. לא כל
    // סביבה מפעילה אותו, ולכן המדידה לא נשענת עליו.
    const ro =
      typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null
    if (ro && chatRef.current) ro.observe(chatRef.current)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', measure)
      ro?.disconnect()
    }
  }, [measure, text])

  const showImage =
    STEPS_WITH_INVITE_IMAGE.has(message.message_type) && !!event?.invite_image
  const showRsvp = message.content.includes('{{rsvp_link}}')
  const showNav = message.content.includes('{{navigation_link}}')
  const showGift = message.content.includes('{{gift_link}}')

  const terms = event ? EVENT_TERMS[event.event_type] ?? EVENT_TERMS.wedding : null
  const chatName =
    [event?.groom_name, event?.bride_name].filter(Boolean).join(' ו') ||
    terms?.celebration ||
    'האירוע'

  return (
    <div className="gm2-fit">
      <div className="ph" dir="rtl">
        <div className="ph-screen">
          <div className="ph-status">
            <span>9:41</span>
            <span className="ph-status-icons" aria-hidden="true">▮▮ ⌁</span>
          </div>
          <div className="ph-bar">
            <span className="ph-back" aria-hidden="true">›</span>
            <span className="ph-avatar" aria-hidden="true">
              {chatName.trim().charAt(0) || '♡'}
            </span>
            <span className="ph-chat-name">{chatName}</span>
          </div>
          <div className="ph-chat" ref={chatRef}>
            <div
              className="ph-bubble"
              ref={bubbleRef}
              style={{
                transform: `scale(${fitted.scale || 1})`,
                visibility: fitted.scale ? 'visible' : 'hidden',
                // ההקטנה ויזואלית בלבד — בלי הקיזוז הזה הצ'אט חושב שהתוכן
                // עדיין בגובה המקורי ומאפשר גלילה מיותרת.
                marginBottom: fitted.scale
                  ? -(fitted.height * (1 - fitted.scale))
                  : 0,
              }}
            >
              {showImage && (
                <img
                  className="ph-image"
                  src={mediaUrl(event!.invite_image)}
                  alt=""
                  onLoad={measure}
                />
              )}
              <div className="ph-text">
                {text && text.trim() ? (
                  text.split('\n').map((line, i) => (
                    <div key={i} className="ph-line">
                      {line || ' '}
                    </div>
                  ))
                ) : (
                  <span className="ph-empty">אין עדיין הודעה להצגה</span>
                )}
              </div>
              {(showRsvp || showNav || showGift) && (
                <div className="ph-btns">
                  {showRsvp && <span className="ph-btn">✅ אישור הגעה</span>}
                  {showNav && <span className="ph-btn">🧭 ניווט</span>}
                  {showGift && <span className="ph-btn">🎁 מתנה באשראי</span>}
                </div>
              )}
              <span className="ph-meta">12:30 ✓✓</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** האם יש מקום להציג את התצוגה לצד הכרטיס (תואם ל-breakpoint ב-CSS). */
function useWideScreen(): boolean {
  const [wide, setWide] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(WIDE_QUERY).matches,
  )
  useEffect(() => {
    const mq = window.matchMedia(WIDE_QUERY)
    const onChange = () => setWide(mq.matches)
    mq.addEventListener('change', onChange)
    onChange()
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return wide
}

/** הנוסח המוגמר של ההודעה כפי שהשרת מרנדר אותו עבור מוזמן לדוגמה. */
function usePreviewText(message: EventMessage): string | null {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    previewCommunicationMessage(message.message_type)
      .then((t) => alive && setText(t))
      .catch(() => alive && setText(''))
    return () => {
      alive = false
    }
  }, [message.message_type, message.content])
  return text
}
