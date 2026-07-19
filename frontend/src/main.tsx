import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './App.css'
import App from './App.tsx'
import { ConfirmPage } from './components/ConfirmPage.tsx'

// ---- חסימת Pinch Zoom ברמת המסמך (iOS Safari) ----
// iOS Safari מתעלם מ-user-scalable=no ב-viewport, ולכן חוסמים ידנית את
// אירועי ה-Gesture (הצביטה של Safari). Double-Tap Zoom כבר מנוטרל דרך
// touch-action: manipulation ב-index.css. מפת האולם עובדת ב-Pointer Events
// בלבד ולא נפגעת; הקלדה וסימון טקסט בשדות ממשיכים כרגיל.
function installMobileZoomGuard() {
  const stop = (e: Event) => e.preventDefault()
  document.addEventListener('gesturestart', stop, { passive: false })
  document.addEventListener('gesturechange', stop, { passive: false })
  document.addEventListener('gestureend', stop, { passive: false })
}
installMobileZoomGuard()

// נתיב ציבורי לאישור הגעה: /confirm/{token} — נפתח ללא התחברות.
const confirmMatch = window.location.pathname.match(/^\/confirm\/([^/]+)/)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {confirmMatch ? <ConfirmPage token={decodeURIComponent(confirmMatch[1])} /> : <App />}
  </StrictMode>,
)
