import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import './App.css'
import App from './App.tsx'
import { ConfirmPage } from './components/ConfirmPage.tsx'
import { CookieBanner } from './components/CookieBanner.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
const DemoDashboard = lazy(() =>
  import('./demo/DemoDashboard.tsx').then((m) => ({ default: m.DemoDashboard })),
)
const DemoGiftCounting = lazy(() =>
  import('./demo/DemoGiftCounting.tsx').then((m) => ({ default: m.DemoGiftCounting })),
)
import { GOOGLE_CLIENT_ID } from './lib/supabase.ts'
import { initPwa } from './lib/pwa.ts'

// ---- חסימת Pinch Zoom — רק על משטחים שמנהלים זום בעצמם (iOS Safari) ----
// הגדלה בצביטה היא דרישת נגישות (WCAG 1.4.4): מי שרואה פחות טוב חייב
// להיות מסוגל להגדיל את הטקסט — בכל המערכת ובדף אישור ההגעה של המוזמנים.
// לכן הזום של הדפדפן פתוח בכל מקום, ונחסם **רק** כשהצביטה מתחילה על משטח
// עם ``touch-action: none`` (מפת האולם וסקיצת האולם, שמזיזות ומגדילות את
// הקנבס בעצמן ב-Pointer Events). iOS Safari מתעלם מ-touch-action בצביטה,
// ולכן נדרש כאן גם חוסם gesture — אבל ממוקד.
function startsOnSelfZoomingSurface(target: EventTarget | null): boolean {
  let el = target instanceof Element ? target : null
  while (el && el !== document.body) {
    if (getComputedStyle(el).touchAction === 'none') return true
    el = el.parentElement
  }
  return false
}

function installMobileZoomGuard() {
  let guarding = false
  const start = (e: Event) => {
    guarding = startsOnSelfZoomingSurface(e.target)
    if (guarding) e.preventDefault()
  }
  const during = (e: Event) => {
    if (guarding) e.preventDefault()
  }
  document.addEventListener('gesturestart', start, { passive: false })
  document.addEventListener('gesturechange', during, { passive: false })
  document.addEventListener('gestureend', during, { passive: false })
}
installMobileZoomGuard()

// ---- מצב "אפליקציה מותקנת" (PWA) ----
// מסמן על <html> אם VEYA רצה מהאייקון במסך הבית, עוקב אחרי גובה החלון
// האמיתי (כדי שמקלדת פתוחה לא תחתוך דיאלוגים), ורושם Service Worker
// מינימלי בייצור. לא נוגע בהתחברות, בניווט או בקריאות ל-API —
// ראו התיעוד המלא ב-src/lib/pwa.ts.
initPwa()

// נתיב ציבורי לאישור הגעה: /confirm/{token} — נפתח ללא התחברות.
// (העמוד מוגש דרך app.html שכבר מסומן noindex, ולכן לא נדרש טיפול נוסף כאן.)
const confirmMatch = window.location.pathname.match(/^\/confirm\/([^/]+)/)
// הדגמת ספירת המעטפות לדף הנחיתה (/demo/gifts). נטענת ב-``lazy`` כדי
// שהיא לא תיכנס ל-bundle של האפליקציה עצמה, ורצה על שרת דמו בזיכרון.
const demoMatch = /^\/demo\/gifts\/?$/.test(window.location.pathname)
const demoDashboardMatch = /^\/demo\/dashboard\/?$/.test(window.location.pathname)

// עוטפים ב-GoogleOAuthProvider רק כשה-Client ID קיים — אחרת הכפתור ממילא לא
// מוצג (isGoogleAuthConfigured מחזיר false), ובלי clientId ה-provider זורק.
// דף אישור ההגעה הציבורי לא צריך את זה (המוזמן לא מתחבר בגוגל).
function AppTree() {
  if (demoDashboardMatch) {
    return (
      <Suspense fallback={null}>
        <DemoDashboard />
      </Suspense>
    )
  }
  if (demoMatch) {
    return (
      <Suspense fallback={null}>
        <DemoGiftCounting />
      </Suspense>
    )
  }
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
