import { useEffect, useState } from 'react'
import './App.css'
import { healthCheck } from './api'
import { GuestsPage } from './components/GuestsPage'

function App() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    healthCheck().then(setOnline)
  }, [])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="logo">VEYA</div>
        <nav className="nav">
          <span className="nav-item active">מוזמנים</span>
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
        <h1 className="page-title">ניהול מוזמנים</h1>
        <GuestsPage />
      </main>
    </div>
  )
}

export default App
