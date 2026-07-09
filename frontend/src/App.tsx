import { useEffect, useState } from 'react'
import './App.css'

const API_URL = 'http://localhost:8000'

type Health = { status: string; service: string }

function App() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [detail, setDetail] = useState<string>('')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Health>
      })
      .then((data) => {
        setStatus('ok')
        setDetail(data.service)
      })
      .catch((err) => {
        setStatus('error')
        setDetail(String(err))
      })
  }, [])

  return (
    <main className="app">
      <div className="card">
        <h1 className="brand">VEYA</h1>
        <p className="subtitle">מערכת ניהול מוזמנים, אישורי הגעה וסידורי הושבה</p>

        {status === 'loading' && <p className="status loading">בודק חיבור לשרת…</p>}
        {status === 'ok' && (
          <p className="status ok">המערכת מחוברת ✓</p>
        )}
        {status === 'error' && (
          <p className="status error">
            אין חיבור לשרת ✗
            <br />
            <small>ודא שה-Backend רץ. פרטים: {detail}</small>
          </p>
        )}
      </div>
    </main>
  )
}

export default App
