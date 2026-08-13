import { useCallback, useEffect, useRef, useState } from 'react'
import { getCommunicationSequence, getEvent, getMessageStatusByType } from '../api'
import type {
  EventDetails,
  EventMessage,
  MessageType,
  MessageTypeStatus,
  RsvpTrackStatus,
} from '../types'
import { MESSAGE_TYPES } from '../types'
import { MessageBoard } from './MessageBoard'
import { MessageEditDrawer } from './MessageEditDrawer'
import type { MessagePanelMode } from './messageShared'
import { MessageTemplates } from './MessageTemplates'
import { MessageTracking } from './MessageTracking'

type Tab = 'board' | 'tracking' | 'templates'

type DrawerState = { type: MessageType; mode: MessagePanelMode } | null

/**
 * "ניהול הודעות" — שלד דק בלבד: מביא את הנתונים המשותפים (רצף ההודעות,
 * פרטי האירוע, סטטוס מסירה לכל סוג הודעה) ומעביר אותם ל-3 הטאבים. כל
 * הלוגיקה של עריכה/בחירת נוסח/מעקב חיה בקבצים הייעודיים שלה
 * (MessageBoard/MessageTracking/MessageTemplates/messageShared) — כאן רק
 * ניווט ומצב משותף.
 *
 * ``track``/``onResend`` מגיעים רק מהמסך של הזוג אחרי שליחה ראשונה. בלעדיהם
 * (באשף לפני שליחה, ובפאנל הטכני של האדמין) טאב "מעקב" לא מוצג — אין עדיין
 * שום דבר למעקב.
 */
export function CommunicationTab({
  track,
  onResend,
}: {
  track?: RsvpTrackStatus
  onResend?: () => void
}) {
  const [messages, setMessages] = useState<EventMessage[] | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('board')
  const [drawer, setDrawer] = useState<DrawerState>(null)
  const [trackingInitialType, setTrackingInitialType] = useState<MessageType | undefined>()
  const [statusByType, setStatusByType] = useState<
    Partial<Record<MessageType, MessageTypeStatus>>
  >({})
  const statusRef = useRef<Partial<Record<MessageType, MessageTypeStatus>>>({})

  const refreshMessages = useCallback(async () => {
    try {
      const seq = await getCommunicationSequence()
      setMessages(seq)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת ההודעות נכשלה')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [seq, ev] = await Promise.all([
          getCommunicationSequence(),
          getEvent().catch(() => null),
        ])
        if (cancelled) return
        setMessages(seq)
        if (ev) setEvent(ev)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'טעינת ההודעות נכשלה')
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  // סטטוס המסירה לכל 6 הסוגים — נטען מראש כדי שכמות הנמענים תופיע על כל
  // כרטיס בלוח בלי קליק נוסף, ומתרענן שוב כשמספר המוזמנים שקיבלו הזמנה
  // משתנה (למשל אחרי "שליחת הזמנות" למוזמנים חדשים).
  useEffect(() => {
    let cancelled = false
    async function loadAll() {
      try {
        const pairs = await Promise.all(
          MESSAGE_TYPES.map(async (type) => [type, await getMessageStatusByType(type)] as const),
        )
        if (cancelled) return
        const next: Partial<Record<MessageType, MessageTypeStatus>> = {}
        for (const [type, s] of pairs) next[type] = s
        statusRef.current = next
        setStatusByType(next)
      } catch {
        /* שקט — הלוח פשוט יציג "טוענים…" ומעקב עדיין יכול לטעון סוג בודד לבד */
      }
    }
    loadAll()
    return () => {
      cancelled = true
    }
  }, [track?.invited])

  // עבור טאב מעקב: מחזיר מהמטמון אם כבר קיים, אחרת שולף סוג בודד ומעדכן.
  const fetchStatus = useCallback(async (type: MessageType): Promise<MessageTypeStatus> => {
    const cached = statusRef.current[type]
    if (cached) return cached
    const s = await getMessageStatusByType(type)
    statusRef.current = { ...statusRef.current, [type]: s }
    setStatusByType(statusRef.current)
    return s
  }, [])

  function openEdit(type: MessageType) {
    setDrawer({ type, mode: 'view' })
  }
  function openTemplatePicker(type: MessageType) {
    setDrawer({ type, mode: 'browse' })
  }
  function goToTracking(type: MessageType) {
    setDrawer(null)
    setTrackingInitialType(type)
    setTab('tracking')
  }

  const drawerMessage = drawer ? messages?.find((m) => m.message_type === drawer.type) : null

  return (
    <div className="mgmt-wrap">
      <div className="mgmt-head">
        <h2 className="mgmt-title">💬 ניהול הודעות</h2>
      </div>

      {error && <p className="form-error">{error}</p>}
      {messages === null && !error && <p className="mb-empty">טוענים…</p>}

      {messages && (
        <>
          <nav className="mgmt-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              className={`mgmt-tab ${tab === 'board' ? 'active' : ''}`}
              onClick={() => setTab('board')}
            >
              לוח הודעות
            </button>
            {track && (
              <button
                type="button"
                role="tab"
                className={`mgmt-tab ${tab === 'tracking' ? 'active' : ''}`}
                onClick={() => setTab('tracking')}
              >
                מעקב
              </button>
            )}
            <button
              type="button"
              role="tab"
              className={`mgmt-tab ${tab === 'templates' ? 'active' : ''}`}
              onClick={() => setTab('templates')}
            >
              נוסחים
            </button>
          </nav>

          <div className="mgmt-panel">
            {tab === 'board' && (
              <MessageBoard
                messages={messages}
                statusByType={statusByType}
                onEdit={openEdit}
                onViewTracking={track ? goToTracking : undefined}
              />
            )}
            {tab === 'tracking' && track && (
              <MessageTracking
                sequence={messages}
                statusByType={statusByType}
                fetchStatus={fetchStatus}
                initialType={trackingInitialType}
                track={track}
                onResend={onResend}
              />
            )}
            {tab === 'templates' && (
              <MessageTemplates messages={messages} onChoose={openTemplatePicker} />
            )}
          </div>
        </>
      )}

      {drawer && drawerMessage && (
        <MessageEditDrawer
          message={drawerMessage}
          event={event}
          initialMode={drawer.mode}
          onSaved={refreshMessages}
          onClose={() => setDrawer(null)}
        />
      )}
    </div>
  )
}
