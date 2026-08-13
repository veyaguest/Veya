import { createPortal } from 'react-dom'
import type { EventDetails, EventMessage } from '../types'
import type { MessagePanelMode } from './messageShared'
import { MessagePanel, useWideScreen } from './messageShared'

/**
 * מעטפת בלבד — אין כאן שום לוגיקת עריכה/בחירה, הכל ב-MessagePanel המשותף.
 * במובייל: מסך מלא (יש למישהו שעורך טקסט צריך מקום, לא יריעה קטנה).
 * בדסקטופ: פאנל צד קבוע — כשה-MessagePanel פותח לצדו גם תצוגה מקדימה
 * (gm2-side, רוחב ≥1040px), זה תמיד "כרטיס + טלפון" בפאנל אחד, אף פעם לא
 * מודל בתוך מודל.
 */
export function MessageEditDrawer({
  message,
  event,
  initialMode,
  onSaved,
  onClose,
}: {
  message: EventMessage
  event: EventDetails | null
  initialMode: MessagePanelMode
  onSaved: () => void
  onClose: () => void
}) {
  const wide = useWideScreen()

  return createPortal(
    <div
      className={`msg-drawer-backdrop ${wide ? 'msg-drawer-backdrop-side' : ''}`}
      onClick={onClose}
    >
      <div
        className={`msg-drawer ${wide ? 'msg-drawer-side' : 'msg-drawer-full'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="msg-drawer-head">
          <h3 className="gm2-card-title">{message.title}</h3>
          <button
            type="button"
            className="msg-drawer-close x"
            onClick={onClose}
            aria-label="סגירה"
          >
            ✕
          </button>
        </div>
        <div className="msg-drawer-body">
          <MessagePanel
            message={message}
            event={event}
            onSaved={onSaved}
            initialMode={initialMode}
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}
