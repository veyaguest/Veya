import { useEffect, useState } from 'react'
import './App.css'
import { healthCheck } from './api'
import { GuestsPage } from './components/GuestsPage'
import { SeatingPage } from './components/SeatingPage'

type Page = 'guests' | 'seating'

function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [page, setPage] = useState<Page>('guests')

  useEffect(() => {
    healthCheck().then(setOnline)
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="logo">VEYA</div>
        <nav className="nav">
          <span
            className={`nav-item ${page === 'guests' ? 'active' : ''}`}
            onClick={() => setPage('guests')}
          >
            מוזמנים
          </span>
          <span
            className={`nav-item ${page === 'seating' ? 'active' : ''}`}
            onClick={() => setPage('seating')}
          >
            שיבוץ הושבה
          </span>
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
        <h1 className="page-title">
          {page === 'guests' ? 'ניהול מוזמנים' : 'שיבוץ הושבה'}
        </h1>
        {page === 'guests' ? <GuestsPage /> : <SeatingPage />}
      </main>
    </div>
  )
}

export default App
