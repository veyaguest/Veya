import { useState } from 'react'
import { createGuest } from '../api'
import type { GroupType, GuestCreate, Side } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'

interface Props {
  onAdded: () => void
  onCancel: () => void
}

const EMPTY: GuestCreate = {
  full_name: '',
  phone: '',
  side: 'shared',
  group_type: 'other',
  party_size: 1,
  notes_raw: '',
  is_child: false,
}

const CUSTOM = '__custom__' // ערך דמה בבורר: "קבוצה חדשה…"

export function AddGuestForm({ onAdded, onCancel }: Props) {
  const [form, setForm] = useState<GuestCreate>(EMPTY)
  const [customGroup, setCustomGroup] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function update<K extends keyof GuestCreate>(key: K, value: GuestCreate[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function onGroupSelect(value: string) {
    if (value === CUSTOM) {
      setCustomGroup(true)
      update('group_type', '')
    } else {
      setCustomGroup(false)
      update('group_type', value as GroupType)
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const group = (form.group_type || '').trim() || 'other'
      await createGuest({
        ...form,
        group_type: group,
        notes_raw: form.notes_raw || undefined,
      })
      setForm(EMPTY)
      setCustomGroup(false)
      onAdded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור, נסו שוב')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="add-form" onSubmit={submit}>
      <div className="add-grid">
        <label>
          שם מלא *
          <input
            value={form.full_name}
            onChange={(e) => update('full_name', e.target.value)}
            placeholder="לדוגמה: דני כהן"
          />
        </label>
        <label>
          טלפון *
          <input
            value={form.phone}
            onChange={(e) => update('phone', e.target.value)}
            placeholder="050-123-4567"
            dir="ltr"
          />
        </label>
        <label>
          צד
          <select
            value={form.side}
            onChange={(e) => update('side', e.target.value as Side)}
          >
            {Object.entries(SIDE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          קבוצה
          <select
            value={customGroup ? CUSTOM : form.group_type}
            onChange={(e) => onGroupSelect(e.target.value)}
          >
            {Object.entries(GROUP_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
            <option value={CUSTOM}>➕ קבוצה חדשה…</option>
          </select>
          {customGroup && (
            <input
              className="custom-group-input"
              value={form.group_type}
              onChange={(e) => update('group_type', e.target.value)}
              placeholder="שם הקבוצה, למשל: חברים מהצבא"
              autoFocus
            />
          )}
        </label>
        <label>
          כמות אנשים
          <input
            type="number"
            min={1}
            value={form.party_size}
            onChange={(e) => update('party_size', Number(e.target.value))}
          />
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={form.is_child ?? false}
            onChange={(e) => update('is_child', e.target.checked)}
          />
          ילד/ה
        </label>
        <label className="wide">
          הערות (העדפות ישיבה וכו')
          <input
            value={form.notes_raw}
            onChange={(e) => update('notes_raw', e.target.value)}
            placeholder="לדוגמה: לא לשבת ליד משפחת לוי"
          />
        </label>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="add-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'שומר…' : 'הוספת מוזמן'}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  )
}
