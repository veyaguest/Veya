import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './App.css'
import App from './App.tsx'
import { ConfirmPage } from './components/ConfirmPage.tsx'

// נתיב ציבורי לאישור הגעה: /confirm/{token} — נפתח ללא התחברות.
const confirmMatch = window.location.pathname.match(/^\/confirm\/([^/]+)/)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {confirmMatch ? <ConfirmPage token={decodeURIComponent(confirmMatch[1])} /> : <App />}
  </StrictMode>,
)
