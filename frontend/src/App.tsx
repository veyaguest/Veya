import { useEffect, useState } from 'react'
import './App.css'
import { getMe, healthCheck, listMyEvents } from './api'
import { clearAuth, getEventId, getToken, setEventId } from './authStore'
import { AdminPage } from './components/AdminPage'
import { AuthPage } from './components/AuthPage'
import { DashboardPage } from './components/DashboardPage'
import { EventPicker, FirstEventScreen } from './components/EventControls'
import { GuestsPage } from './components/GuestsPage'
import { HallPage } from './components/HallPage'
import { RsvpPage } from './components/RsvpPage'
import { SeatingPage } from './components/SeatingPage'
import type { EventSummary, User } from './types'

type Page = 'dashboard' | 'guests' | 'rsvp' | 'seating' | 'hall' | 'admin'

const PAGE_TITLES: Record<Page, string> = {
  dashboard: 'סקירה כללית',
  guests: 'ניהול מוזמנים',
  rsvp: 'אישורי הגעה',
  seating: 'שיבוץ הושבה',
  hall: 'מפת אולם',
  admin: 'ניהול המערכת',
}

const NAV_ITEMS: { key: Page; label: string }[] = [
  { key: 'dashboard', label: 'סקירה' },
  { key: 'guests', label: 'מוזמנים' },
  { key: 'rsvp', label: 'אישורי הגעה' },
  { key: 'seating', label: 'שיבוץ הושבה' },
  { key: 'hall', label: 'מפת אולם' },
]

function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [page, setPage] = useState<Page>('dashboard')
  const [logoOk, setLogoOk] = useState(true)

  const [user, setUser] = useState<User | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [events, setEvents] = useState<EventSummary[]>([])
  const [activeEventId, setActiveEventId] = useState<number | null>(getEventId())

  useEffect(() => {
    healthCheck().then(setOnline)
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
      setUser(null)
      setEvents([])
      setActiveEventId(null)
    }
    window.addEventListener('veya-unauthorized', handler)
    return () => window.removeEventListener('veya-unauthorized', handler)
  }, [])

  async function handleAuth(u: User) {
    setUser(u)
    await loadEvents()
  }

  function handleSwitchEvent(id: number) {
    setActiveEventId(id)
    setEventId(id)
    setPage('dashboard')
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

  // מחובר אבל אין עדיין אירוע → מסך יצירת אירוע ראשון.
  if (events.length === 0) {
    return <FirstEventScreen onCreated={handleEventCreated} />
  }

  const navItems: { key: Page; label: string }[] = user.is_admin
    ? [...NAV_ITEMS, { key: 'admin', label: 'ניהול' }]
    : NAV_ITEMS

  return (
    <div className="shell">
      <header className="topbar">
        <div className="logo">
          {logoOk ? (
            <img
              src="/logo.svg"
              alt="VEYA"
              className="logo-img"
              onError={() => setLogoOk(false)}
            />
          ) : (
            <span className="logo-text">VEYA</span>
          )}
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <span
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              {item.label}
            </span>
          ))}
        </nav>
        <div className="topbar-end">
          {page !== 'admin' && (
            <EventPicker
              events={events}
              activeEventId={activeEventId}
              onSwitch={handleSwitchEvent}
              onCreated={handleEventCreated}
            />
          )}
          <div className="conn">
            {online === null && <span className="dot loading" />}
            {online === true && <span className="dot ok" />}
            {online === false && <span className="dot err" />}
          </div>
          <button type="button" className="logout-btn" onClick={handleLogout}>
            יציאה
          </button>
        </div>
      </header>

      <main className="content" key={`${page}-${activeEventId}`}>
        <h1 className="page-title">{PAGE_TITLES[page]}</h1>
        {page === 'dashboard' && <DashboardPage />}
        {page === 'guests' && <GuestsPage />}
        {page === 'rsvp' && <RsvpPage />}
        {page === 'seating' && <SeatingPage />}
        {page === 'hall' && <HallPage />}
        {page === 'admin' && <AdminPage />}
      </main>
    </div>
  )
}

export default App
