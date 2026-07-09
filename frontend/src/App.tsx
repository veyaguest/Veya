import { useEffect, useState } from 'react'
import './App.css'
import { healthCheck } from './api'
import { GuestsPage } from './components/GuestsPage'
import { RsvpPage } from './components/RsvpPage'
import { SeatingPage } from './components/SeatingPage'

type Page = 'guests' | 'rsvp' | 'seating'

const PAGE_TITLES: Record<Page, string> = {
  guests: 'ניהול מוזמנים',
  rsvp: 'אישורי הגעה',
  seating: 'שיבוץ הושבה',
}

const NAV_ITEMS: { key: Page; label: string }[] = [
  { key: 'guests', label: 'מוזמנים' },
  { key: 'rsvp', label: 'אישורי הגעה' },
  { key: 'seating', label: 'שיבוץ הושבה' },
]

function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [page, setPage] = useState<Page>('guests')
  const [logoOk, setLogoOk] = useState(true)

  useEffect(() => {
    healthCheck().then(setOnline)
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="logo">
          {logoOk ? (
            <img
              src="/logo.png"
              alt="VEYA"
              className="logo-img"
              onError={() => setLogoOk(false)}
            />
          ) : (
            <span className="logo-text">VEYA</span>
          )}
        </div>
        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <span
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              {item.label}
            </span>
          ))}
        </nav>
        <div className="conn">
          {online === null && <span className="dot loading" />}
          {online === true && (
            <>
              <span className="dot ok" /> מחובר
            </>
          )}
          {online === false && (
            <>
              <span className="dot err" /> אין חיבור לשרת
            </>
          )}
        </div>
      </header>

      <main className="content">
        <h1 className="page-title">{PAGE_TITLES[page]}</h1>
        {page === 'guests' && <GuestsPage />}
        {page === 'rsvp' && <RsvpPage />}
        {page === 'seating' && <SeatingPage />}
      </main>
    </div>
  )
}

export default App
