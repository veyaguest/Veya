import { useState } from 'react'
import { completePostponement, requestPostponement } from '../api'
import type { Postponement } from '../types'
import { strings } from '../strings/he'

const t = strings.postpone

/**
 * דיאלוג בקשת נוהל דחייה.
 *
 * **אין כאן שדה תאריך, ובמכוון.** זוג שמבקש לדחות אירוע לרוב עדיין לא יודע
 * מתי הוא יתקיים — שדה תאריך היה מכריח אותו להמציא אחד, או לחכות עם הבקשה
 * עד שיידע. שני המצבים גרועים, ולכן המסך אומר את זה במפורש.
 */
export function PostponeRequestDialog({
  onDone,
  onClose,
}: {
  onDone: (p: Postponement) => void
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setBusy(true)
    setError('')
    try {
      const p = await requestPostponement()
      setSent(true)
      onDone(p)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.sendError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog postpone-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{sent ? t.sentTitle : t.dialogTitle}</h2>
          <button className="x" onClick={onClose} aria-label={strings.common.close}>
            ✕
          </button>
        </div>

        {sent ? (
          <>
            <p className="postpone-body">{t.sentBody}</p>
            <div className="add-actions">
              <button className="btn-primary" onClick={onClose}>
                {strings.common.close}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="postpone-body">{t.dialogBody}</p>
            <div className="postpone-note">
              <strong>{t.dialogNoDateTitle}</strong>
              <span>{t.dialogNoDateBody}</span>
            </div>
            {error && <p className="form-error">{error}</p>}
            <div className="add-actions">
              <button className="btn-primary" onClick={submit} disabled={busy}>
                {busy ? strings.common.saving : t.dialogSubmit}
              </button>
              <button className="btn-ghost" onClick={onClose} disabled={busy}>
                {strings.common.cancel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/**
 * דיאלוג סיום הנוהל — הרגע שבו אישורי ההגעה מתחילים מחדש.
 *
 * הטקסט אומר במפורש מה נשמר (מוזמנים, שיבוץ) ומה מתחיל מחדש (התשובות), כי
 * זו השאלה היחידה שמדאיגה זוג בנקודה הזו. אין כאן "פעולה בלתי הפיכה" —
 * ההיסטוריה באמת נשמרת בשרת, אז אין מה להפחיד.
 */
export function PostponeFinishDialog({
  onDone,
  onClose,
}: {
  onDone: (p: Postponement) => void
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setBusy(true)
    setError('')
    try {
      const p = await completePostponement()
      onDone(p)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t.finishError)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog postpone-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{t.finishTitle}</h2>
          <button className="x" onClick={onClose} aria-label={strings.common.close}>
            ✕
          </button>
        </div>
        <p className="postpone-body">{t.finishBody}</p>
        {error && <p className="form-error">{error}</p>}
        <div className="add-actions">
          <button className="btn-primary" onClick={submit} disabled={busy}>
            {busy ? strings.common.saving : t.finishCta}
          </button>
          <button className="btn-ghost" onClick={onClose} disabled={busy}>
            {strings.common.cancel}
          </button>
        </div>
      </div>
    </div>
  )
}
