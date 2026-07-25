import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import './App.css'
import App from './App.tsx'
import { ConfirmPage } from './components/ConfirmPage.tsx'
import { CookieBanner } from './components/CookieBanner.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { GOOGLE_CLIENT_ID } from './lib/supabase.ts'

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
// (העמוד מוגש דרך app.html שכבר מסומן noindex, ולכן לא נדרש טיפול נוסף כאן.)
const confirmMatch = window.location.pathname.match(/^\/confirm\/([^/]+)/)

// עוטפים ב-GoogleOAuthProvider רק כשה-Client ID קיים — אחרת הכפתור ממילא לא
// מוצג (isGoogleAuthConfigured מחזיר false), ובלי clientId ה-provider זורק.
// דף אישור ההגעה הציבורי לא צריך את זה (המוזמן לא מתחבר בגוגל).
function AppTree() {
  const tree = confirmMatch
    ? <ConfirmPage token={decodeURIComponent(confirmMatch[1])} />
    : <App />
  if (!confirmMatch && GOOGLE_CLIENT_ID) {
    return <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{tree}</GoogleOAuthProvider>
  }
  return tree
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <AppTree />
      <CookieBanner />
    </ErrorBoundary>
  </StrictMode>,
)
