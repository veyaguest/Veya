import { useEffect, useState } from 'react'
import { getGroupNotes, setGroupNote } from '../api'
import type { GroupInUse } from '../types'
import { groupLabel } from '../types'
import { strings } from '../strings/he'

const t = strings.guests

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
        setError(err instanceof Error ? err.message : t.notesLoadError),
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
      setError(err instanceof Error ? err.message : t.notesSaveError)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog notes-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{t.notesTitle}</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="paste-hint">{t.notesHint}</p>

        {loading && <div className="empty">{t.loadingRows}</div>}
        {!loading && groups.length === 0 && (
          <div className="empty">{t.notesEmpty}</div>
        )}

        {!loading && groups.length > 0 && (
          <div className="notes-list">
            {groups.map((g) => (
              <div key={g.group_type} className="note-row">
                <div className="note-group">
                  <span className="note-group-name">
                    {groupLabel(g.group_type)}
                  </span>
                  <span className="note-group-count">{t.groupCount(g.count)}</span>
                </div>
                <div className="note-input-wrap">
                  <input
                    className="cell-input"
                    defaultValue={notes[g.group_type] ?? ''}
                    placeholder={t.notesInputPlaceholder}
                    onBlur={(e) => {
                      const v = e.target.value.trim()
                      if (v !== (notes[g.group_type] ?? ''))
                        save(g.group_type, v)
                    }}
                  />
                  {savedKey === g.group_type && (
                    <span className="note-saved">{t.notesSaved}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        <div className="add-actions">
          <button className="btn-primary" onClick={onClose}>
            {t.notesDone}
          </button>
        </div>
      </div>
    </div>
  )
}
