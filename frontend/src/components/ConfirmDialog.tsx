import { useBackToClose } from '../lib/backToClose'
import { useDialog } from '../lib/useDialog'
import { strings } from '../strings/he'

interface Props {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * דיאלוג אישור מעוצב בסגנון VEYA — מחליף את confirm()/alert() הגנריים של
 * הדפדפן בכל מקום שדורש אישור לפני פעולה בלתי-הפיכה (כמו מחיקה).
 */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  // "חזור" בטלפון סוגר את החלון במקום לנווט אחורה (lib/backToClose).
  useBackToClose(true, onCancel)
  // alertdialog: אישור לפני פעולה בלתי-הפיכה. ההודעה מקושרת כתיאור, כך
  // שקורא מסך מקריא גם "מה יקרה" ולא רק את הכותרת.
  const dlg = useDialog(onCancel, { closeOnEscape: !busy })
  const messageId = `${dlg.titleId}-msg`
  return (
    <div className="overlay confirm-overlay" onClick={onCancel}>
      <div
        className="dialog confirm-dialog"
        {...dlg.props}
        role="alertdialog"
        aria-describedby={messageId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-head">
          <h2 id={dlg.titleId}>{title}</h2>
          <button className="x" onClick={onCancel} aria-label={strings.common.cancel}>
            ✕
          </button>
        </div>
        <p className="confirm-dialog-message" id={messageId}>{message}</p>
        <div className="add-actions">
          <button
            className={danger ? 'btn-danger' : 'btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel ?? strings.common.confirm}
          </button>
          <button className="btn-ghost" onClick={onCancel} disabled={busy}>
            {strings.common.cancel}
          </button>
        </div>
      </div>
    </div>
  )
}
