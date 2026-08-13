import type { EventMessage, MessageType, MessageTypeStatus } from '../types'
import { MESSAGE_TYPE_ICONS } from '../types'
import { asReadableText } from './messageShared'
import { usePreviewText } from './messageShared'

/** לוח ההודעות — הטאב הראשי: כל 6 השלבים ברצף אנכי אחד, כרטיס לכל שלב. */
export function MessageBoard({
  messages,
  statusByType,
  onEdit,
  onViewTracking,
}: {
  messages: EventMessage[]
  statusByType: Partial<Record<MessageType, MessageTypeStatus>>
  onEdit: (type: MessageType) => void
  onViewTracking?: (type: MessageType) => void
}) {
  return (
    <ol className="board-list">
      {messages.map((m, i) => (
        <li key={m.message_type} className="board-item">
          <BoardCard
            message={m}
            status={statusByType[m.message_type]}
            onEdit={() => onEdit(m.message_type)}
            onViewTracking={onViewTracking ? () => onViewTracking(m.message_type) : undefined}
          />
          {i < messages.length - 1 && (
            <span className="board-arrow" aria-hidden="true">↓</span>
          )}
        </li>
      ))}
    </ol>
  )
}

function BoardCard({
  message,
  status,
  onEdit,
  onViewTracking,
}: {
  message: EventMessage
  status: MessageTypeStatus | undefined
  onEdit: () => void
  onViewTracking?: () => void
}) {
  const previewText = usePreviewText(message)
  const preview = message.content.trim()
    ? previewText ?? asReadableText(message.content, {})
    : ''

  const statusLabel = !status
    ? 'טוענים…'
    : status.not_sent_yet
      ? 'טרם נשלחה'
      : status.queued > 0
        ? 'בתהליך שליחה'
        : 'נשלחה'
  const statusTone = !status || status.not_sent_yet ? 'wait' : status.queued > 0 ? 'wait' : 'ok'

  return (
    <div className="board-card">
      <div className="board-card-head">
        <span className="board-card-icon" aria-hidden="true">
          {MESSAGE_TYPE_ICONS[message.message_type]}
        </span>
        <h3 className="board-card-title">{message.title}</h3>
        <span className={`board-card-status ${statusTone}`}>{statusLabel}</span>
      </div>

      {preview ? (
        <p className="board-card-preview">{preview}</p>
      ) : (
        <p className="board-card-preview board-card-preview-empty">
          עדיין לא בחרתם הודעה לשלב הזה.
        </p>
      )}

      {status && !status.not_sent_yet && status.total > 0 && (
        <p className="board-card-count">{status.total} נמענים</p>
      )}

      <div className="board-card-actions">
        <button type="button" className="gm2-btn gm2-btn-main" onClick={onEdit}>
          עריכת הודעה
        </button>
        {onViewTracking && status && !status.not_sent_yet && (
          <button type="button" className="gm2-btn gm2-btn-quiet" onClick={onViewTracking}>
            צפייה במעקב
          </button>
        )}
      </div>
    </div>
  )
}
