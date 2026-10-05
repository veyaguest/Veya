import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

/**
 * תפריט נפתח (כפתור + רשימת פעולות) — התנהגות מקלדת אחת לכל התפריטים.
 *
 * ``role="menu"`` מבטיח לקורא מסך שאפשר לזוז בחיצים. קודם התפריטים
 * הכריזו על עצמם כ-menu אבל החיצים לא עשו כלום, והפוקוס נשאר על הכפתור —
 * גרוע מכפתורים רגילים. כאן (לפי דפוס ה-Menu Button של WAI-ARIA):
 *
 * - פתיחה מעבירה פוקוס לפריט הראשון; ↓/↑ מסתובבים, Home/End לקצוות.
 * - Escape סוגר ומחזיר פוקוס לכפתור. Tab סוגר וממשיך הלאה כרגיל.
 * - בחירה בפריט מחזירה קודם את הפוקוס לכפתור, ורק אז מפעילה את הפעולה —
 *   כך חלון שנפתח מהתפריט יודע לאן להחזיר את הפוקוס כשייסגר (הפריט עצמו
 *   כבר לא קיים).
 */
export function useMenu() {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const items = () =>
    Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? [])

  function close(returnFocus = true) {
    setOpen(false)
    if (returnFocus) triggerRef.current?.focus()
  }

  // סגירה בלחיצה מחוץ לתפריט.
  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  // בפתיחה — פוקוס לפריט הראשון.
  useEffect(() => {
    if (open) items()[0]?.focus()
  }, [open])

  function onListKeyDown(e: ReactKeyboardEvent) {
    const list = items()
    const at = list.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      close()
    } else if (e.key === 'Tab') {
      setOpen(false)
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
      e.preventDefault()
      if (list.length === 0) return
      const next =
        e.key === 'Home' ? 0
          : e.key === 'End' ? list.length - 1
            : e.key === 'ArrowDown' ? (at + 1) % list.length
              : (at - 1 + list.length) % list.length
      list[next].focus()
    }
  }

  function onTriggerKeyDown(e: ReactKeyboardEvent) {
    if (e.key === 'ArrowDown' && !open) {
      e.preventDefault()
      setOpen(true)
    }
  }

  /** עוטף פעולה של פריט: סוגר, מחזיר פוקוס לכפתור, ואז מפעיל. */
  const select = (action: () => void) => () => {
    close()
    action()
  }

  return {
    open,
    wrapRef,
    select,
    triggerProps: {
      ref: triggerRef,
      onClick: () => setOpen((o) => !o),
      onKeyDown: onTriggerKeyDown,
      'aria-haspopup': 'menu' as const,
      'aria-expanded': open,
    },
    listProps: {
      ref: listRef,
      role: 'menu' as const,
      onKeyDown: onListKeyDown,
    },
  }
}
