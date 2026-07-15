import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createAutomationTemplate,
  deleteAutomationTemplate,
  getAutomationPlaceholders,
  listAutomationTemplates,
  updateAutomationTemplate,
} from '../api'
import type {
  AutomationTemplate,
  TemplateKind,
  TemplatePlaceholder,
} from '../types'
import { TEMPLATE_KIND_LABELS } from '../types'

const KIND_OPTIONS: TemplateKind[] = [
  'invitation',
  'reminder',
  'pre_event',
  'thank_you',
  'custom',
]

const BLANK = { name: '', kind: 'custom' as TemplateKind, body: '' }

/** ניהול תבניות הודעה בעלות שם — הבסיס לחוקי האוטומציה. */
export function AutomationTemplatesTab({
  onChanged,
}: {
  onChanged?: () => void
}) {
  const [templates, setTemplates] = useState<AutomationTemplate[]>([])
  const [placeholders, setPlaceholders] = useState<TemplatePlaceholder[]>([])
  const [selectedId, setSelectedId] = useState<number | 'new'>('new')
  const [form, setForm] = useState(BLANK)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const bodyRef = useRef<HTMLTextAreaElement | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [tpls, phs] = await Promise.all([
        listAutomationTemplates(),
        getAutomationPlaceholders(),
      ])
      setTemplates(tpls)
      setPlaceholders(phs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת התבניות')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  function selectTemplate(t: AutomationTemplate) {
    setSelectedId(t.id)
    setForm({ name: t.name, kind: t.kind as TemplateKind, body: t.body })
    setNote('')
    setError('')
  }

  function startNew() {
    setSelectedId('new')
    setForm(BLANK)
    setNote('')
    setError('')
  }

  function insertPlaceholder(key: string) {
    const ta = bodyRef.current
    if (!ta) {
      setForm((f) => ({ ...f, body: f.body + key }))
      return
    }
    const start = ta.selectionStart
    const end = ta.selectionEnd
    setForm((f) => ({ ...f, body: f.body.slice(0, start) + key + f.body.slice(end) }))
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + key.length
    }, 0)
  }

  async function onSave() {
    if (!form.name.trim()) {
      setError('צריך לתת שם לתבנית')
      return
    }
    setBusy(true)
    setError('')
    setNote('')
    try {
      if (selectedId === 'new') {
        const t = await createAutomationTemplate(form)
        await refresh()
        selectTemplate(t)
        setNote('התבנית נוצרה ✓')
      } else {
        const t = await updateAutomationTemplate(selectedId, form)
        await refresh()
        selectTemplate(t)
        setNote('התבנית נשמרה ✓')
      }
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשמירת התבנית')
    } finally {
      setBusy(false)
    }
  }

  async function onDelete() {
    if (selectedId === 'new') return
    if (!confirm('למחוק את התבנית? חוקים שמשתמשים בה יישארו אך ללא תבנית.')) return
    setBusy(true)
    setError('')
    try {
      await deleteAutomationTemplate(selectedId)
      startNew()
      await refresh()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה במחיקת התבנית')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auto-templates">
      <div className="auto-two-col">
        {/* רשימת תבניות */}
        <aside className="auto-side-list">
          <div className="auto-side-head">
            <h3 className="clar-title">התבניות שלי</h3>
            <button className="btn-ghost auto-new-btn" onClick={startNew}>
              + תבנית חדשה
            </button>
          </div>
          {templates.length === 0 ? (
            <p className="auto-empty">עדיין אין תבניות. צרו את הראשונה ←</p>
          ) : (
            <ul className="auto-tpl-list">
              {templates.map((t) => (
                <li key={t.id}>
                  <button
                    className={`auto-tpl-item ${selectedId === t.id ? 'active' : ''}`}
                    onClick={() => selectTemplate(t)}
                  >
                    <span className="auto-tpl-name">{t.name}</span>
                    <span className="auto-tpl-kind">
                      {TEMPLATE_KIND_LABELS[t.kind as TemplateKind] ?? t.kind}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* עורך התבנית */}
        <div className="auto-editor">
          <div className="auto-field-row">
            <label className="field-group auto-grow">
              <span className="field-label">שם התבנית</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="למשל: תזכורת ראשונה"
              />
            </label>
            <label className="field-group">
              <span className="field-label">סוג</span>
              <select
                value={form.kind}
                onChange={(e) =>
                  setForm({ ...form, kind: e.target.value as TemplateKind })
                }
              >
                {KIND_OPTIONS.map((k) => (
                  <option key={k} value={k}>
                    {TEMPLATE_KIND_LABELS[k]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="tpl-placeholders">
            {placeholders.map((p) => (
              <button
                key={p.key}
                type="button"
                className="tpl-chip"
                title={p.desc}
                onClick={() => insertPlaceholder(p.key)}
              >
                {p.key}
              </button>
            ))}
          </div>

          <textarea
            ref={bodyRef}
            className="tpl-textarea"
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
            rows={7}
            dir="rtl"
            placeholder="כתבו את נוסח ההודעה. הוסיפו משתנים בלחיצה למעלה."
          />

          <div className="tpl-actions">
            <button className="btn-primary" onClick={onSave} disabled={busy}>
              {busy ? 'שומר…' : selectedId === 'new' ? 'יצירת תבנית' : 'שמירה'}
            </button>
            {selectedId !== 'new' && (
              <button className="btn-text" onClick={onDelete} disabled={busy}>
                מחיקה
              </button>
            )}
            {note && <span className="tpl-saved">{note}</span>}
          </div>
          {error && <p className="form-error">{error}</p>}
        </div>
      </div>
    </div>
  )
}
