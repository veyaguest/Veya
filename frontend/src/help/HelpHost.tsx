/**
 * "עזרה" — הכפתור והמארח (HELP_CENTER_PLAN.md שלב 4). בחבילה הראשית.
 *
 * - ``HelpLauncher`` — הכפתור. יושב ב-``sidebar-foot`` של App.tsx: בדסקטופ
 *   בסרגל הצד, בטלפון בפס העליון ליד "החשבון שלי". לא כפתור צף.
 * - ``HelpHost`` — טוען את העזרה עצמה (חלונית + הדרכות) **רק בפתיחה הראשונה**.
 *
 * App.tsx מרנדר את שניהם רק כש-``EventSummary.help_enabled`` — כשהפיצ'ר כבוי
 * שום דבר מכאן לא מופיע ולא נטען.
 */
import { Suspense, lazy, useEffect, useState } from 'react'
import { strings } from '../strings/he'
import { closeHelp, toggleHelp, useHelpOpen, useHelpSwitchedOff } from './helpStore'
import type { HelpAppProps } from './ui/HelpApp'
import './help-launcher.css'

const loadHelpApp = () => import('./ui/HelpApp')
const HelpApp = lazy(loadHelpApp)

/** טעינה מוקדמת כשמתקרבים לכפתור — כדי שהפתיחה תהיה מיידית. */
function preload(): void {
  void loadHelpApp()
}

export function HelpLauncher() {
  const open = useHelpOpen()
  const off = useHelpSwitchedOff()
  const t = strings.help
  if (off) return null
  return (
    <button
      type="button"
      className={`help-launcher${open ? ' is-open' : ''}`}
      data-help-launcher=""
      aria-expanded={open}
      aria-controls="veya-help-panel"
      aria-label={t.launcherAria}
      title={t.launcher}
      onClick={toggleHelp}
      onPointerEnter={preload}
      onFocus={preload}
    >
      <svg className="help-launcher-icon" viewBox="0 0 24 24" width="20" height="20" fill="none"
        stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6" />
        <path d="M12 16.9v.1" />
      </svg>
      <span className="help-launcher-label">{t.launcher}</span>
    </button>
  )
}

export function HelpHost(props: Omit<HelpAppProps, 'open'>) {
  const open = useHelpOpen()
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    if (open) setMounted(true)
  }, [open])
  // יציאה / אירוע בלי עזרה → החלונית לא נשארת "פתוחה" לפעם הבאה.
  useEffect(() => () => closeHelp(), [])
  // העזרה נסגרה באמצע (helpStore) — מורידים הכול, כולל הדרכה שרצה.
  const off = useHelpSwitchedOff()
  // נשאר טעון אחרי הסגירה הראשונה — כדי שהדרכה ("תראו לי") תמשיך לרוץ
  // כשהחלונית עצמה סגורה.
  if (!mounted || off) return null
  return (
    <Suspense fallback={null}>
      <HelpApp {...props} open={open} />
    </Suspense>
  )
}
