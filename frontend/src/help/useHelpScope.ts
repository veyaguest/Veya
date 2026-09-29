import { useEffect } from 'react'
import { pushScope } from './scopes'
import type { ScopeId } from './scopes'

/**
 * מכריז שהרכיב הזה הוא "המקום" שבו המשתמש נמצא — לצורך העזרה בלבד.
 *
 * ``null`` = לא פעיל כרגע (hooks לא נקראים בתנאי, אז מעבירים null במקום
 * לדלג): ``useHelpScope(editing ? 'dashboard.editEvent' : null)``.
 *
 * אין לזה שום השפעה על הרכיב עצמו — רק רישום ב-``scopes.ts``.
 */
export function useHelpScope(scope: ScopeId | null): void {
  useEffect(() => {
    if (!scope) return
    return pushScope(scope)
  }, [scope])
}
