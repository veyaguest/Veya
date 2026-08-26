import { useCallback, useEffect, useState } from 'react'
import { bulkGroup, groupSuggestions } from '../api'
import type { GroupSuggestion } from '../types'
import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  // משתנה בכל רענון של רשימת המוזמנים — מפעיל טעינה מחדש של ההצעות.
  refreshToken: number
  // האם אזור ההצעות פתוח כרגע (Drawer/Modal). הטעינה עצמה רצה תמיד,
  // כדי שה-Badge יוכל להציג מספר עדכני גם כשהאזור סגור.
  open: boolean
  onClose: () => void
  // נקרא בכל שינוי במספר ההצעות הגלויות — מזין את ה-Badge שעל הכפתור.
  onCountChange: (count: number) => void
  // נקרא אחרי שיוך קבוצה מוצלח, כדי לרענן את הטבלה למעלה.
  onApplied: (message: string) => void
}

/**
 * אזור "הצעות חכמות" לאיחוד מוזמנים: כשמזהים כמה מוזמנים עם אותו שם
 * משפחה, מציעים לאחד אותם לקבוצה בלחיצה אחת. הזוג תמיד מאשר — לא אוטומטי.
 * מוצג רק לפי דרישה (כפתור "הצעות לאיחוד" בעמוד), לא אוטומטית בכניסה לעמוד.
 */
export function GroupSuggestions({ refreshToken, open, onClose, onCountChange, onApplied }: Props) {
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

  useEffect(() => {
    onCountChange(visible.length)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible.length])

  if (!open) return null

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
    <div className="overlay" onClick={onClose}>
      <div className="dialog suggestions-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{t.suggestionsTitle}</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="paste-hint">{t.suggestionsHint}</p>

        {visible.length === 0 && <div className="empty">{t.suggestionsEmpty}</div>}

        {visible.length > 0 && (
          <div className="suggestions">
            {visible.map((s) => (
              <div key={s.surname} className="suggestion-card">
                <div className="suggestion-text">
                  <span className="suggestion-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M8.4 4.5 9.7 8l3.5 1.3L9.7 10.6 8.4 14.1 7.1 10.6 3.6 9.3 7.1 8l1.3-3.5Z" />
                      <path d="M16.6 12.4 17.5 15l2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
                    </svg>
                  </span>
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
        )}
      </div>
    </div>
  )
}
