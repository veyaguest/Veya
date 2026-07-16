import { useCallback, useEffect, useState } from 'react'
import { bulkGroup, groupSuggestions } from '../api'
import type { GroupSuggestion } from '../types'
import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  // משתנה בכל רענון של רשימת המוזמנים — מפעיל טעינה מחדש של ההצעות.
  refreshToken: number
  // נקרא אחרי שיוך קבוצה מוצלח, כדי לרענן את הטבלה למעלה.
  onApplied: (message: string) => void
}

/**
 * כרטיסי "הצעות חכמות" מעל טבלת המוזמנים: כשמזהים כמה מוזמנים עם אותו שם
 * משפחה, מציעים לאחד אותם לקבוצה בלחיצה אחת. הזוג תמיד מאשר — לא אוטומטי.
 */
export function GroupSuggestions({ refreshToken, onApplied }: Props) {
  const [items, setItems] = useState<GroupSuggestion[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await groupSuggestions()
      setItems(res)
    } catch {
      setItems([]) // הצעות הן "נחמד שיהיה" — כישלון שקט, לא מפריע לעבודה.
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshToken])

  const visible = items.filter((s) => !dismissed.has(s.surname))
  if (visible.length === 0) return null

  async function apply(s: GroupSuggestion) {
    setBusy(s.surname)
    try {
      const res = await bulkGroup(s.guest_ids, s.group_name)
      onApplied(t.suggestionCreatedToast(s.group_name, res.updated))
    } catch {
      onApplied(t.suggestionCreateError)
    } finally {
      setBusy(null)
    }
  }

  function dismiss(surname: string) {
    setDismissed((prev) => new Set(prev).add(surname))
  }

  return (
    <div className="suggestions">
      {visible.map((s) => (
        <div key={s.surname} className="suggestion-card">
          <div className="suggestion-text">
            <span className="suggestion-icon">✨</span>
            {/* משפט זה משלב טקסט עברי עם <strong> סביב ערכים דינמיים —
                לא ניתן להוציא אותו כמחרוזת שטוחה יחידה ל-he.ts בלי לאבד
                את הדגשת ה-JSX. חריג מכוון ומתועד; שאר הטקסטים במסך זה
                כן ממורכזים ב-he.ts. */}
            מצאנו <strong>{s.count}</strong> מוזמנים עם שם המשפחה{' '}
            <strong>"{s.surname}"</strong>. ליצור את הקבוצה{' '}
            <strong>"{s.group_name}"</strong>?
          </div>
          <div className="suggestion-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => apply(s)}
              disabled={busy === s.surname}
            >
              {busy === s.surname ? t.suggestionCreating : t.suggestionCreateGroup}
            </button>
            <button
              className="btn-ghost btn-sm"
              onClick={() => dismiss(s.surname)}
              disabled={busy === s.surname}
            >
              {t.suggestionNotNow}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
