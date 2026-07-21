import { useEffect, useMemo, useState } from 'react'
import { bulkGroup, listGuests } from '../api'
import type { Guest } from '../types'
import { groupLabel } from '../types'
import { sideLabel } from '../strings/eventTypes'
import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  onClose: () => void
  onCreated: (message: string) => void
}

/**
 * חלונית "יצירת קבוצה": בעל האירוע נותן שם לקבוצה חדשה, מסמן אילו מוזמנים
 * שייכים אליה, ואנחנו משייכים את כולם בבת אחת (bulk-group). זו הדרך הברורה
 * ליצור קבוצה ידנית — מעבר להצעות האוטומטיות ולבחירה בטופס הוספת מוזמן.
 */
export function CreateGroupDialog({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [guests, setGuests] = useState<Guest[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // טוענים את כל המוזמנים (עד 200) לבחירה. לרשימות גדולות יש חיפוש.
  useEffect(() => {
    let alive = true
    listGuests('', 200, 0)
      .then((page) => {
        if (alive) setGuests(page.items)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : t.loadError),
      )
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  const filtered = useMemo(() => {
    const q = search.trim()
    if (!q) return guests
    return guests.filter(
      (g) => g.full_name.includes(q) || (g.phone ?? '').includes(q),
    )
  }, [guests, search])

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function save() {
    const group = name.trim()
    if (!group) {
      setError(t.createGroupNoName)
      return
    }
    if (selected.size === 0) {
      setError(t.createGroupNoGuests)
      return
    }
    setError('')
    setSaving(true)
    try {
      const res = await bulkGroup([...selected], group)
      onCreated(t.createGroupSavedToast(group, res.updated))
    } catch (err) {
      setError(err instanceof Error ? err.message : t.createGroupError)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog notes-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{t.createGroupTitle}</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="paste-hint">{t.createGroupHint}</p>

        <label className="cg-name-label">
          {t.createGroupNameLabel}
          <input
            className="cell-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t.createGroupNamePlaceholder}
            autoFocus
          />
        </label>

        <div className="cg-pick-head">
          <span>{t.createGroupPickHint}</span>
          <span className="cg-selected-count">
            {t.createGroupSelected(selected.size)}
          </span>
        </div>

        {!loading && guests.length > 0 && (
          <input
            className="cell-input cg-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t.searchPlaceholder}
          />
        )}

        {loading && <div className="empty">{t.createGroupLoading}</div>}
        {!loading && guests.length === 0 && (
          <div className="empty">{t.createGroupEmpty}</div>
        )}

        {!loading && guests.length > 0 && (
          <div className="cg-guest-list">
            {filtered.map((g) => (
              <label key={g.id} className="cg-guest-row">
                <input
                  type="checkbox"
                  checked={selected.has(g.id)}
                  onChange={() => toggle(g.id)}
                />
                <span className="cg-guest-name">{g.full_name}</span>
                <span className="cg-guest-meta">
                  {sideLabel(g.side)} · {groupLabel(g.group_type)}
                </span>
              </label>
            ))}
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        <div className="add-actions">
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? t.createGroupSaving : t.createGroupSave}
          </button>
          <button className="btn-ghost" onClick={onClose}>
            {strings.common.cancel}
          </button>
        </div>
      </div>
    </div>
  )
}
