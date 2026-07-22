import { useState } from 'react'
import { createGuest, updateGuest } from '../api'
import type { GroupType, Guest, GuestCreate, Side } from '../types'
import { GROUP_LABELS } from '../types'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

const t = strings.guests
const tc = strings.common

interface Props {
  onAdded: () => void
  onCancel: () => void
  guest?: Guest // אם קיים — מצב עריכה של מוזמן קיים
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

// האם ערך הקבוצה הוא קבוצה מותאמת (לא אחת מהמוכרות)?
function isCustomGroup(group: string): boolean {
  return !!group && !(group in GROUP_LABELS)
}

export function AddGuestForm({ onAdded, onCancel, guest }: Props) {
  const editing = !!guest
  const [form, setForm] = useState<GuestCreate>(
    guest
      ? {
          full_name: guest.full_name,
          phone: guest.phone,
          side: guest.side,
          group_type: guest.group_type,
          party_size: guest.party_size,
          notes_raw: guest.notes_raw ?? '',
          is_child: guest.is_child ?? false,
        }
      : EMPTY,
  )
  const [customGroup, setCustomGroup] = useState(
    guest ? isCustomGroup(guest.group_type) : false,
  )
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
      if (guest) {
        await updateGuest(guest.id, {
          ...form,
          group_type: group,
          notes_raw: form.notes_raw || null,
        })
      } else {
        await createGuest({
          ...form,
          group_type: group,
          notes_raw: form.notes_raw || undefined,
        })
        setForm(EMPTY)
        setCustomGroup(false)
      }
      onAdded()
    } catch (err) {
      setError(err instanceof Error ? err.message : t.saveErrorGeneric)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="add-form" onSubmit={submit}>
      <div className="add-grid">
        <label>
          {t.fullNameLabel}
          <input
            value={form.full_name}
            onChange={(e) => update('full_name', e.target.value)}
            placeholder={t.fullNamePlaceholder}
          />
        </label>
        <label>
          {t.phoneLabel}
          <input
            value={form.phone}
            onChange={(e) => update('phone', e.target.value)}
            placeholder={t.phonePlaceholder}
            dir="ltr"
          />
        </label>
        <label>
          {t.sideLabel}
          <select
            value={form.side}
            onChange={(e) => update('side', e.target.value as Side)}
          >
            {Object.entries(activeEventTerms().sideLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.groupLabelText}
          <select
            value={customGroup ? CUSTOM : form.group_type}
            onChange={(e) => onGroupSelect(e.target.value)}
          >
            {activeEventTerms().groupOptions.map(({ key, label }) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
            <option value={CUSTOM}>{t.newGroupOption}</option>
          </select>
          {customGroup && (
            <input
              className="custom-group-input"
              value={form.group_type}
              onChange={(e) => update('group_type', e.target.value)}
              placeholder={t.newGroupPlaceholder}
              autoFocus
            />
          )}
        </label>
        <label>
          {t.partySizeLabel}
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
          {t.isChildLabel}
        </label>
        <label className="wide">
          {t.notesFieldLabel}
          <input
            value={form.notes_raw}
            onChange={(e) => update('notes_raw', e.target.value)}
            placeholder={t.notesFieldPlaceholder}
          />
        </label>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="add-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? t.saving : editing ? t.submitEdit : t.submitAdd}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          {tc.cancel}
        </button>
      </div>
    </form>
  )
}
