/**
 * "צריכים עזרה עם זה?" — שורה קטנה מתחת לשגיאה שמוצגת על המסך.
 * HELP_CENTER_PLAN.md שלב 5.
 *
 * מופיעה **רק** כש:
 *  - העזרה פתוחה לאירוע (help_enabled), וגם
 *  - ההודעה שעל המסך היא בדיוק השגיאה האחרונה שהשרת החזיר (אחרי ניקוי),
 *    מ-5 הדקות האחרונות, וגם
 *  - זו שגיאה שהעזרה מזהה (help/errorHelp.ts).
 * אחרת — כלום. שגיאה לא מזוהה לא מקבלת "פתרון" מומצא.
 *
 * לחיצה פותחת את העזרה ישר על בדיקת התקלה, מול **השגיאה הזו** בלבד.
 * לא משנה שום נתון, לא שולח ולא שומר.
 */
import { useEffect, useState } from 'react'
import { strings } from '../strings/he'
import { ERROR_WINDOW_MS, currentKnownError } from './errorHelp'
import { openHelpFor, useHelpEnabled } from './helpStore'

export function HelpErrorHint({ message }: { message: string | null | undefined }) {
  const enabled = useHelpEnabled()
  const [, setTick] = useState(0)
  const match = enabled && message ? currentKnownError(message) : null

  // השגיאה "מתיישנת" אחרי 5 דקות — אז השורה נעלמת, גם אם ההודעה עוד על המסך.
  useEffect(() => {
    if (!match) return
    const left = ERROR_WINDOW_MS - (Date.now() - match.at)
    const id = window.setTimeout(() => setTick((n) => n + 1), Math.max(0, left) + 50)
    return () => window.clearTimeout(id)
  }, [match?.at]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!match) return null
  const t = strings.help
  return (
    <p className="help-error-hint">
      <span>{t.errorHint}</span>{' '}
      <button
        type="button"
        className="help-error-hint-btn"
        onClick={() => openHelpFor({ tree: match.tree, errorAt: match.at })}
      >
        {t.errorHintCta}
      </button>
    </p>
  )
}
