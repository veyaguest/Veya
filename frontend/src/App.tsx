import { useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import './App.css'
import { adminImpersonate, getMe, healthCheck, listMyEvents } from './api'
import {
  clearAdminToken,
  clearAuth,
  getAdminToken,
  getEventId,
  getToken,
  isImpersonating,
  setActiveEventType,
  setAdminToken,
  setEventId,
  setToken,
} from './authStore'
import { getEventTerms, hostNames } from './strings/eventTypes'
import { AdminApp } from './components/AdminApp'
import { AuthPage } from './components/AuthPage'
import { DashboardPage } from './components/DashboardPage'
import { ErrorBoundary } from './components/ErrorBoundary'
import { EventMembersDialog } from './components/EventMembersDialog'
import { GuestsPage } from './components/GuestsPage'
import { HallPage } from './components/HallPage'
import { OnboardingWizard } from './components/OnboardingWizard'
import { ProfileDialog } from './components/ProfileDialog'
import { RsvpPage } from './components/RsvpPage'
import type { EventSummary, User } from './types'
import type { EventTerms } from './strings/eventTypes'

type Page = 'dashboard' | 'guests' | 'rsvp' | 'hall'

// כותרות/ניווט תלויי-סוג-אירוע: "מוזמנים" הופך ל"משתתפים" באירוע עסקי וכו'.
function pageTitles(terms: EventTerms): Record<Page, string> {
  return {
    dashboard: 'האירוע שלנו',
    guests: `ניהול ${terms.guestsLabel}`,
    rsvp: 'אישורי הגעה',
    hall: 'סידור הושבה',
  }
}

// label — הטקסט המלא בסרגל הצד (דסקטופ); short — טקסט קצר לניווט התחתון בטלפון.
function navItemsFor(terms: EventTerms): { key: Page; label: string; short: string }[] {
  return [
    { key: 'dashboard', label: 'תמונת מצב', short: 'בית' },
    { key: 'guests', label: `ניהול ${terms.guestsLabel}`, short: terms.guestsLabel },
    { key: 'rsvp', label: 'אישורי הגעה', short: 'אישורים' },
    { key: 'hall', label: 'סידור הושבה', short: 'הושבה' },
  ]
}

/** אייקון קווי לכל פריט ניווט — מוצג בניווט התחתון בטלפון. */
function NavIcon({ page }: { page: Page }) {
  const common = {
    className: 'nav-icon',
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (page) {
    case 'dashboard':
      return (
        <svg {...common}>
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V21h14V9.5" />
          <path d="M9.5 21v-6h5v6" />
        </svg>
      )
    case 'guests':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
          <path d="M16 6.5a3 3 0 0 1 0 5.8" />
          <path d="M17.5 20a5.5 5.5 0 0 0-2.5-4.6" />
        </svg>
      )
    case 'rsvp':
      return (
        <svg {...common}>
          <path d="M4 5h16v11H8l-4 3z" />
          <path d="m9 10 2 2 4-4" />
        </svg>
      )
    case 'hall':
      return (
        <svg {...common}>
          <circle cx="7" cy="8" r="2.4" />
          <circle cx="17" cy="8" r="2.4" />
          <circle cx="12" cy="17" r="2.4" />
          <path d="M4 20h16" />
        </svg>
      )
  }
}

function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [page, setPage] = useState<Page>('dashboard')

  const [user, setUser] = useState<User | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [membersOpen, setMembersOpen] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [events, setEvents] = useState<EventSummary[]>([])
  const [activeEventId, setActiveEventId] = useState<number | null>(getEventId())
  // מצב התחזות: אדמין שמחובר כרגע כמשתמש (טוקן האדמין שמור בצד).
  const [impersonating, setImpersonating] = useState<boolean>(isImpersonating())
  const [impBusy, setImpBusy] = useState(false)

  // בדיקת "מחובר" חוזרת (לא רק פעם אחת בטעינה) — אם השרת נופל באמצע
  // השימוש, הנקודה תתעדכן בתוך עד 20 שניות ולא תישאר תקועה על "מחובר".
  useEffect(() => {
    let alive = true
    const check = () => healthCheck().then((ok) => alive && setOnline(ok))
    check()
    const interval = window.setInterval(check, 20000)
    return () => {
      alive = false
      window.clearInterval(interval)
    }
  }, [])

  // טעינת האירועים של המשתמש ובחירת האירוע הפעיל.
  async function loadEvents() {
    const evs = await listMyEvents().catch(() => [] as EventSummary[])
    setEvents(evs)
    const stored = getEventId()
    const chosen = evs.find((e) => e.id === stored)?.id ?? evs[0]?.id ?? null
    setActiveEventId(chosen)
    setEventId(chosen)
    return evs
  }

  // בדיקת טוקן קיים בעת טעינת האפליקציה.
  useEffect(() => {
    const token = getToken()
    if (!token) {
      setAuthChecked(true)
      return
    }
    getMe()
      .then(async (u) => {
        setUser(u)
        await loadEvents()
      })
      .catch(() => {
        /* 401 כבר טופל — נשאר לא מחובר */
      })
      .finally(() => setAuthChecked(true))
  }, [])

  // האזנה ל-401 גלובלי (טוקן פג) — מחזיר למסך התחברות.
  useEffect(() => {
    const handler = () => {
      clearAdminToken()
      setImpersonating(false)
      setUser(null)
      setEvents([])
      setActiveEventId(null)
    }
    window.addEventListener('veya-unauthorized', handler)
    return () => window.removeEventListener('veya-unauthorized', handler)
  }, [])

  // אדמין "מתחבר כמשתמש": שומר את טוקן האדמין בצד, מכניס טוקן משתמש במקומו,
  // וטוען מחדש את הממשק בעיני אותו משתמש. שגיאות מוחזרות לקורא (AdminApp).
  async function handleImpersonate(userId: number) {
    const adminToken = getToken()
    if (!adminToken) return
    const res = await adminImpersonate(userId)
    setAdminToken(adminToken)
    setToken(res.token)
    setEventId(null)
    setImpersonating(true)
    setPage('dashboard')
    const u = await getMe()
    setUser(u)
    await loadEvents()
  }

  // חזרה מהתחזות למצב אדמין: משחזר את טוקן האדמין ומרענן את המשתמש.
  async function handleStopImpersonate() {
    const adminToken = getAdminToken()
    setImpBusy(true)
    try {
      if (adminToken) setToken(adminToken)
      clearAdminToken()
      setImpersonating(false)
      setEventId(null)
      setEvents([])
      setActiveEventId(null)
      setPage('dashboard')
      const u = await getMe()
      setUser(u)
    } catch {
      handleLogout()
    } finally {
      setImpBusy(false)
    }
  }

  async function handleAuth(u: User) {
    setUser(u)
    await loadEvents()
  }

  async function handleEventCreated(ev: EventSummary) {
    setEvents((prev) => [ev, ...prev.filter((e) => e.id !== ev.id)])
    setActiveEventId(ev.id)
    setEventId(ev.id)
    setPage('dashboard')
  }

  function handleLogout() {
    clearAuth()
    setUser(null)
    setEvents([])
    setActiveEventId(null)
    setPage('dashboard')
  }

  // עדיין בודקים אם יש טוקן תקין.
  if (!authChecked) {
    return (
      <div className="boot-screen">
        <span className="dot loading" /> טוען…
      </div>
    )
  }

  // לא מחובר → מסך התחברות/הרשמה.
  if (!user) {
    return <AuthPage onAuth={handleAuth} />
  }

  // אדמין → פאנל ניהול מלא ונפרד (לא נכנס למסלול יצירת אירוע של זוג).
  if (user.is_admin) {
    return (
      <AdminApp user={user} onLogout={handleLogout} onImpersonate={handleImpersonate} />
    )
  }

  // בזמן התחזות עוטפים את ממשק הזוג בבאנר קבוע עם דרך חזרה לאדמין.
  const withImpersonation = (view: ReactElement): ReactElement =>
    impersonating ? (
      <>
        <div className="imp-banner" role="status">
          <span className="imp-banner-text">
            <span className="imp-banner-dot" aria-hidden="true" />
            אתה מחובר כרגע כאדמין למשתמש זה — {user.display_name || user.email}
          </span>
          <button
            type="button"
            className="imp-banner-exit"
            onClick={handleStopImpersonate}
            disabled={impBusy}
          >
            {impBusy ? 'רגע…' : 'חזרה לאדמין'}
          </button>
        </div>
        <div className="imp-shift">{view}</div>
      </>
    ) : (
      view
    )

  // מחובר אבל אין עדיין אירוע.
  if (events.length === 0) {
    // מפיק/אולם לא יוצרים אירוע בעצמם — הם מחכים שבעל אירוע יזמין אותם.
    if (user.account_type === 'planner' || user.account_type === 'venue') {
      return withImpersonation(
        <div className="auth-wrap">
          <div className="auth-card">
            <h1 className="first-event-title">ברוכים הבאים ל-VEYA</h1>
            <p className="auth-tagline">
              עדיין לא שותפה איתכם גישה לאף אירוע. בקשו מבעל האירוע להוסיף
              אתכם דרך האימייל שאיתו נרשמתם: <strong dir="ltr">{user.email}</strong>
            </p>
          </div>
        </div>,
      )
    }
    return withImpersonation(<OnboardingWizard onCreated={handleEventCreated} />)
  }

  const activeEvent = events.find((e) => e.id === activeEventId) ?? null
  // מסנכרן את סוג האירוע הפעיל ל-store, כדי שמסכים יגזרו ממנו מונחים דינמיים.
  setActiveEventType(activeEvent?.event_type ?? null)
  const activeTerms = getEventTerms(activeEvent?.event_type)
  const navItems = navItemsFor(activeTerms)
  const pageTitle = pageTitles(activeTerms)
  const eventLabel = activeEvent
    ? hostNames(activeTerms, activeEvent.groom_name, activeEvent.bride_name) ||
      activeTerms.defaultTitle
    : '—'
  const userInitial = (user.display_name || user.email || '?').trim().charAt(0).toUpperCase()

  return withImpersonation(
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-logo" dir="ltr">
          <span className="auth-monogram">
            <span className="auth-monogram-diamond" />
            <span className="auth-monogram-v">V</span>
          </span>
          <span className="logo-text">VEYA</span>
        </div>

        <nav className="side-nav">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              <span className="nav-bullet" aria-hidden="true" />
              <NavIcon page={item.key} />
              <span className="nav-label">{item.label}</span>
              <span className="nav-label-short">{item.short}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <button
            type="button"
            className="user-chip"
            onClick={() => setProfileOpen(true)}
            title="החשבון שלי"
          >
            <span className="user-avatar">{userInitial}</span>
            <span className="user-meta">
              <span className="user-name">{user.display_name || 'משתמש'}</span>
              <span className="user-event">{eventLabel}</span>
            </span>
          </button>
          <div className="sidebar-foot-row">
            <span className="conn">
              {online === null && <span className="dot loading" />}
              {online === true && <span className="dot ok" />}
              {online === false && <span className="dot err" />}
              <span className="conn-text">
                {online === false ? 'לא מחובר' : 'מחובר'}
              </span>
            </span>
            <button type="button" className="logout-btn" onClick={handleLogout}>
              יציאה
            </button>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="page-header">
          <h1 className="page-title">{pageTitle[page]}</h1>
        </header>
        <main className="content" key={`${page}-${activeEventId}`}>
          <ErrorBoundary>
            {page === 'dashboard' && (
              <DashboardPage onNavigate={(p) => setPage(p)} />
            )}
            {page === 'guests' && <GuestsPage />}
            {page === 'rsvp' && (
              <RsvpPage isAdmin={user.is_admin} onNavigate={(p) => setPage(p)} />
            )}
            {page === 'hall' && <HallPage onNavigate={(p) => setPage(p)} />}
          </ErrorBoundary>
        </main>
      </div>

      {profileOpen && (
        <ProfileDialog
          user={user}
          onClose={() => setProfileOpen(false)}
          onUpdated={(u) => setUser(u)}
          onLogout={() => {
            setProfileOpen(false)
            handleLogout()
          }}
          onManageAccess={
            user.account_type === 'couple' && activeEventId != null
              ? () => {
                  setProfileOpen(false)
                  setMembersOpen(true)
                }
              : undefined
          }
        />
      )}

      {membersOpen && activeEventId != null && (
        <EventMembersDialog eventId={activeEventId} onClose={() => setMembersOpen(false)} />
      )}
    </div>,
  )
}

export default App
