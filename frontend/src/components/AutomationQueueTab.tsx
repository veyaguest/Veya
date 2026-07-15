import { useCallback, useEffect, useState } from 'react'
import { getDueQueue, runDueQueue } from '../api'
import type { DueAction, TriggerType } from '../types'
import { TRIGGER_LABELS } from '../types'

/** התור לאישור — מי אמור לקבל הודעה עכשיו, ושליחה בלחיצה. */
export function AutomationQueueTab({ onSent }: { onSent?: () => void }) {
  const [actions, setActions] = useState<DueAction[]>([])
  const [mode, setMode] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const q = await getDueQueue()
      setActions(q.actions)
      setMode(q.mode)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת התור')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function onRun(ruleId?: number) {
    setBusy(true)
    setError('')
    setNote('')
    try {
      const res = await runDueQueue(ruleId != null ? [ruleId] : undefined)
      setNote(
        `נשלחו ${res.sent} הודעות` +
          (res.failed ? ` · ${res.failed} נכשלו` : '') +
          (res.skipped ? ` · ${res.skipped} דולגו` : '') +
          (res.mode === 'mock' ? ' · מצב בדיקה (לא נשלח בפועל)' : ''),
      )
      await refresh()
      onSent?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשליחה')
    } finally {
      setBusy(false)
    }
  }

  // קיבוץ לפי חוק — כדי שהזוג יראה "מה החוק הזה עומד לשלוח".
  const byRule = new Map<number, { name: string; items: DueAction[] }>()
  for (const a of actions) {
    const g = byRule.get(a.rule_id) ?? { name: a.rule_name, items: [] }
    g.items.push(a)
    byRule.set(a.rule_id, g)
  }

  return (
    <div className="auto-queue">
      <div className="auto-side-head auto-rules-head">
        <div>
          <h3 className="clar-title">תור לשליחה</h3>
          <span className="clar-sub">
            אלו ההודעות שהגיע זמנן לפי החוקים שהגדרתם. בדקו את התצוגה המקדימה,
            ושִלחו בלחיצה. שום דבר לא נשלח בלי אישורכם.
          </span>
        </div>
        <div className="auto-queue-actions">
          {mode && (
            <span className={`mode-badge ${mode}`}>
              {mode === 'mock' ? 'מצב בדיקה' : 'מצב חי'}
            </span>
          )}
          <button
            className="btn-primary"
            onClick={() => onRun()}
            disabled={busy || actions.length === 0}
          >
            {busy ? 'שולח…' : `שליחת הכול (${actions.length})`}
          </button>
        </div>
      </div>

      {note && <p className="rsvp-note">{note}</p>}
      {error && <p className="form-error">{error}</p>}

      {actions.length === 0 ? (
        <p className="auto-empty">
          אין כרגע הודעות בתור. כשחוק "יבשיל" עבור מוזמן — הוא יופיע כאן.
        </p>
      ) : (
        <div className="auto-queue-groups">
          {[...byRule.entries()].map(([ruleId, group]) => (
            <div key={ruleId} className="auto-queue-group">
              <div className="auto-queue-group-head">
                <span className="auto-queue-group-name">{group.name}</span>
                <button
                  className="btn-ghost"
                  onClick={() => onRun(ruleId)}
                  disabled={busy}
                >
                  שליחת {group.items.length} הודעות
                </button>
              </div>
              <ul className="auto-queue-list">
                {group.items.map((a) => (
                  <li key={`${a.rule_id}-${a.guest_id}`} className="auto-queue-item">
                    <div className="auto-queue-item-head">
                      <span className="auto-queue-guest">{a.guest_name}</span>
                      <span className="auto-queue-trigger">
                        {TRIGGER_LABELS[a.trigger_type as TriggerType] ?? a.trigger_type}
                      </span>
                    </div>
                    <div className="auto-queue-preview">{a.preview}</div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
