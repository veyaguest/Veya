import type { EventMessage } from '../types'
import { MESSAGE_TYPE_ICONS } from '../types'
import { asReadableText, usePreviewText } from './messageShared'

/** נוסחים — הנוסח הנבחר לכל שלב, עם אפשרות להחליף אותו דרך ספריית 12 הנוסחים. */
export function MessageTemplates({
  messages,
  onChoose,
}: {
  messages: EventMessage[]
  onChoose: (type: EventMessage['message_type']) => void
}) {
  return (
    <ul className="tmpl-list">
      {messages.map((m) => (
        <TemplateRow key={m.message_type} message={m} onChoose={() => onChoose(m.message_type)} />
      ))}
    </ul>
  )
}

function TemplateRow({
  message,
  onChoose,
}: {
  message: EventMessage
  onChoose: () => void
}) {
  const previewText = usePreviewText(message)
  const preview = message.content.trim()
    ? previewText ?? asReadableText(message.content, {})
    : ''

  return (
    <li className="tmpl-row">
      <div className="tmpl-row-head">
        <span className="tmpl-row-icon" aria-hidden="true">
          {MESSAGE_TYPE_ICONS[message.message_type]}
        </span>
        <h3 className="tmpl-row-title">{message.title}</h3>
      </div>
      {preview ? (
        <p className="tmpl-row-preview">{preview}</p>
      ) : (
        <p className="tmpl-row-preview tmpl-row-preview-empty">עדיין לא נבחר נוסח.</p>
      )}
      <button type="button" className="gm2-btn gm2-btn-main tmpl-row-btn" onClick={onChoose}>
        החלפת נוסח
      </button>
    </li>
  )
}
