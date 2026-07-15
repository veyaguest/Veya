import { useCallback, useEffect, useState } from 'react'
import {
  createAutomationRule,
  deleteAutomationRule,
  listAutomationRules,
  listAutomationTemplates,
  updateAutomationRule,
} from '../api'
import type {
  AutomationRule,
  AutomationTemplate,
  TargetGroup,
  TriggerType,
} from '../types'
import { TARGET_GROUP_LABELS, TRIGGER_LABELS } from '../types'

const TRIGGER_OPTIONS: TriggerType[] = [
  'event_created',
  'invitation_sent',
  'no_response',
  'before_event_date',
  'guest_confirmed',
]

const TARGET_OPTIONS: TargetGroup[] = [
  'all',
  'pending',
  'confirmed',
  'declined',
  'maybe',
  'side_groom',
  'side_bride',
]

// הסבר קצר לכל טריגר — עוזר לזוג להבין מתי ההודעה תישלח.
const TRIGGER_HINT: Record<TriggerType, string> = {
  event_created: 'נמדד מרגע יצירת האירוע במערכת',
  invitation_sent: 'נמדד מרגע שנשלחה ההזמנה למוזמן',
  no_response: 'רק אם המוזמן עדיין לא הגיב, X ימים אחרי ההזמנה',
  before_event_date: 'X ימים לפני תאריך האירוע',
  guest_confirmed: 'X ימים אחרי שהמוזמן אישר הגעה',
}

const BLANK = {
  rule_name: '',
  trigger_type: 'no_response' as TriggerType,
  delay_days: 3,
  target_group: 'pending' as TargetGroup,
  template_id: null as number | null,
}

/** בונה חוקי אוטומציה — מתי, למי ובאיזו תבנית לשלוח. */
export function AutomationRulesTab({ onChanged }: { onChanged?: () => void }) {
  const [rules, setRules] = useState<AutomationRule[]>([])
  const [templates, setTemplates] = useState<AutomationTemplate[]>([])
  const [form, setForm] = useState(BLANK)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [r, t] = await Promise.all([
        listAutomationRules(),
        listAutomationTemplates(),
      ])
      setRules(r)
      setTemplates(t)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת החוקים')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  function templateName(id: number | null): string {
    if (id == null) return 'ללא תבנית'
    return templates.find((t) => t.id === id)?.name ?? 'תבנית שנמחקה'
  }

  function startCreate() {
    setForm({ ...BLANK, template_id: templates[0]?.id ?? null })
    setEditingId(null)
    setShowForm(true)
    setError('')
  }

  function startEdit(r: AutomationRule) {
    setForm({
      rule_name: r.rule_name,
      trigger_type: r.trigger_type as TriggerType,
      delay_days: r.delay_days,
      target_group: r.target_group as TargetGroup,
      template_id: r.template_id,
    })
    setEditingId(r.id)
    setShowForm(true)
    setError('')
  }

  async function onSubmit() {
    if (!form.rule_name.trim()) {
      setError('צריך לתת שם לחוק')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (editingId == null) {
        await createAutomationRule(form)
      } else {
        await updateAutomationRule(editingId, form)
      }
      setShowForm(false)
      await refresh()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשמירת החוק')
    } finally {
      setBusy(false)
    }
  }

  async function toggleActive(r: AutomationRule) {
    try {
      await updateAutomationRule(r.id, { active: !r.active })
      await refresh()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בעדכון החוק')
    }
  }

  async function onDelete(r: AutomationRule) {
    if (!confirm(`למחוק את החוק "${r.rule_name}"?`)) return
    try {
      await deleteAutomationRule(r.id)
      await refresh()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה במחיקת החוק')
    }
  }

  return (
    <div className="auto-rules">
      <div className="auto-side-head auto-rules-head">
        <div>
          <h3 className="clar-title">חוקי אוטומציה</h3>
          <span className="clar-sub">
            כל חוק קובע מתי לשלוח הודעה, למי, ובאיזו תבנית. שום דבר לא נשלח
            אוטומטית — הכול עובר דרך "תור לשליחה" לאישורכם.
          </span>
        </div>
        <button className="btn-primary" onClick={startCreate}>
          + חוק חדש
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <div className="auto-rule-form">
          <label className="field-group">
            <span className="field-label">שם החוק</span>
            <input
              value={form.rule_name}
              onChange={(e) => setForm({ ...form, rule_name: e.target.value })}
              placeholder="למשל: תזכורת שבוע לפני"
            />
          </label>

          <div className="auto-field-row">
            <label className="field-group auto-grow">
              <span className="field-label">מתי לשלוח</span>
              <select
                value={form.trigger_type}
                onChange={(e) =>
                  setForm({ ...form, trigger_type: e.target.value as TriggerType })
                }
              >
                {TRIGGER_OPTIONS.map((tt) => (
                  <option key={tt} value={tt}>
                    {TRIGGER_LABELS[tt]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-group auto-delay">
              <span className="field-label">מספר ימים</span>
              <input
                type="number"
                min={0}
                value={form.delay_days}
                onChange={(e) =>
                  setForm({ ...form, delay_days: Math.max(0, Number(e.target.value)) })
                }
              />
            </label>
          </div>
          <p className="auto-hint">{TRIGGER_HINT[form.trigger_type]}</p>

          <div className="auto-field-row">
            <label className="field-group auto-grow">
              <span className="field-label">למי לשלוח</span>
              <select
                value={form.target_group}
                onChange={(e) =>
                  setForm({ ...form, target_group: e.target.value as TargetGroup })
                }
              >
                {TARGET_OPTIONS.map((tg) => (
                  <option key={tg} value={tg}>
                    {TARGET_GROUP_LABELS[tg]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-group auto-grow">
              <span className="field-label">תבנית ההודעה</span>
              <select
                value={form.template_id ?? ''}
                onChange={(e) =>
                  setForm({
                    ...form,
                    template_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
              >
                <option value="">— ללא תבנית —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {templates.length === 0 && (
            <p className="auto-hint auto-warn">
              עדיין אין תבניות. מומלץ קודם ליצור תבנית בלשונית "תבניות הודעה".
            </p>
          )}

          <div className="tpl-actions">
            <button className="btn-primary" onClick={onSubmit} disabled={busy}>
              {busy ? 'שומר…' : editingId == null ? 'יצירת חוק' : 'שמירה'}
            </button>
            <button
              className="btn-text"
              onClick={() => setShowForm(false)}
              disabled={busy}
            >
              ביטול
            </button>
          </div>
        </div>
      )}

      {rules.length === 0 && !showForm ? (
        <p className="auto-empty">
          עדיין אין חוקים. צרו חוק ראשון כדי שהמערכת תתחיל להציע הודעות לשליחה.
        </p>
      ) : (
        <ul className="auto-rule-list">
          {rules.map((r) => (
            <li key={r.id} className={`auto-rule-card ${r.active ? '' : 'off'}`}>
              <div className="auto-rule-main">
                <span className="auto-rule-name">{r.rule_name}</span>
                <span className="auto-rule-meta">
                  {TRIGGER_LABELS[r.trigger_type as TriggerType]} · {r.delay_days} ימים
                  {' · '}
                  {TARGET_GROUP_LABELS[r.target_group as TargetGroup]}
                  {' · '}
                  {templateName(r.template_id)}
                </span>
              </div>
              <div className="auto-rule-side">
                <button
                  className={`auto-toggle ${r.active ? 'on' : 'off'}`}
                  onClick={() => toggleActive(r)}
                  title={r.active ? 'חוק פעיל — לחצו לכיבוי' : 'חוק כבוי — לחצו להפעלה'}
                >
                  {r.active ? 'פעיל' : 'כבוי'}
                </button>
                <button className="btn-text" onClick={() => startEdit(r)}>
                  עריכה
                </button>
                <button className="btn-text auto-del" onClick={() => onDelete(r)}>
                  מחיקה
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
