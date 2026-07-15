import { useEffect, useState } from 'react'
import { getGroupNotes, setGroupNote } from '../api'
import type { GroupInUse } from '../types'
import { groupLabel } from '../types'

interface Props {
  onClose: () => void
}

/**
 * חלונית "העדפות קבוצה": לכל קבוצה שבשימוש אפשר לרשום העדפה חופשית
 * (למשל "רחוק מהרעש" / "קרוב לרחבה"). ההעדפה נשמרת לכל חברי הקבוצה
 * ותסייע בהמשך בסידור ההושבה. שמירה אוטומטית בעת יציאה מהשדה.
 */
export function GroupNotesPanel({ onClose }: Props) {
  const [groups, setGroups] = useState<GroupInUse[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savedKey, setSavedKey] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    getGroupNotes()
      .then((data) => {
        if (!alive) return
        setGroups(data.groups)
        setNotes(data.notes)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון כרגע, ננסה שוב'),
      )
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  async function save(groupType: string, current: string) {
    try {
      const data = await setGroupNote(groupType, current)
      setNotes(data.notes)
      setSavedKey(groupType)
      setTimeout(() => setSavedKey((k) => (k === groupType ? null : k)), 1800)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור, נסו שוב')
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog notes-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>העדפות קבוצה</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="paste-hint">
          לכל קבוצה אפשר לרשום העדפה קצרה — למשל "רחוק מהרעש" או "קרוב לרחבה".
          נשמור אותה לכל חברי הקבוצה כדי לעזור בסידור ההושבה.
        </p>

        {loading && <div className="empty">טוען…</div>}
        {!loading && groups.length === 0 && (
          <div className="empty">
            עדיין אין קבוצות. הוסיפו מוזמנים ושייכו אותם לקבוצות כדי להגדיר
            העדפות.
          </div>
        )}

        {!loading && groups.length > 0 && (
          <div className="notes-list">
            {groups.map((g) => (
              <div key={g.group_type} className="note-row">
                <div className="note-group">
                  <span className="note-group-name">
                    {groupLabel(g.group_type)}
                  </span>
                  <span className="note-group-count">{g.count} מוזמנים</span>
                </div>
                <div className="note-input-wrap">
                  <input
                    className="cell-input"
                    defaultValue={notes[g.group_type] ?? ''}
                    placeholder="למשל: רחוק מהרעש"
                    onBlur={(e) => {
                      const v = e.target.value.trim()
                      if (v !== (notes[g.group_type] ?? ''))
                        save(g.group_type, v)
                    }}
                  />
                  {savedKey === g.group_type && (
                    <span className="note-saved">שמרנו ✓</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        <div className="add-actions">
          <button className="btn-primary" onClick={onClose}>
            סיום
          </button>
        </div>
      </div>
    </div>
  )
}
