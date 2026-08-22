import { lazy, Suspense, useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import './App.css'
import {
  adminImpersonate,
  confirmEmailVerification,
  getMe,
  healthCheck,
  listMyEvents,
} from './api'
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
import { AccountCenter } from './components/AccountCenter'
import { AuthPage } from './components/AuthPage'
import { CompleteProfilePage } from './components/CompleteProfilePage'
import { DashboardPage } from './components/DashboardPage'
import { JoinEventPage } from './components/JoinEventPage'
import { ResetPasswordPage } from './components/ResetPasswordPage'
import { VerifyEmailPage } from './components/VerifyEmailPage'
import { ErrorBoundary } from './components/ErrorBoundary'
import { EventMembersDialog } from './components/EventMembersDialog'
import { Footer } from './components/Footer'
import { GuestsPage } from './components/GuestsPage'
import { MessagesPage } from './components/MessagesPage'
import { OnboardingWizard } from './components/OnboardingWizard'
import { ReconsentModal } from './components/ReconsentModal'
import { RsvpPage } from './components/RsvpPage'
import type { EventSummary, User } from './types'
import type { EventTerms } from './strings/eventTypes'

// Code splitting: AdminApp ו-HallPage הם הקבצים הכבדים ביותר בבנדל (פאנל
// אדמין שלם / עורך מפת אולם עם ~4400 שורות), אבל רוב הסשנים (זוג רגיל
// שלא נכנס למפת ההושבה, וכל מי שאינו אדמין) אף פעם לא צריכים אותם. טעינה
// עצלה (lazy) מוציאה אותם מה-bundle הראשוני לצ'אנק נפרד שנטען רק בשימוש בפועל.
const AdminApp = lazy(() =>
  import('./components/AdminApp').then((m) => ({ default: m.AdminApp })),
)
const HallPage = lazy(() =>
  import('./components/HallPage').then((m) => ({ default: m.HallPage })),
)
// מסך הטלפן — רלוונטי לחלק זעיר מהמשתמשים, ולכן גם הוא בצ'אנק נפרד.
const PhoneAgentApp = lazy(() =>
  import('./components/PhoneAgentApp').then((m) => ({ default: m.PhoneAgentApp })),
)

// אותו מסך "טוען…" שכבר קיים לבדיקת ההתחברות הראשונית (boot-screen) — משתמשים
// בו גם כ-fallback ל-Suspense, כדי שלא תיווסף שפת טעינה חדשה לאפליקציה.
const bootFallback = (
  <div className="boot-screen">
    <span className="dot loading" /> טוען…
  </div>
)

type Page = 'dashboard' | 'guests' | 'messages' | 'rsvp' | 'hall'

// כותרות/ניווט תלויי-סוג-אירוע: "מוזמנים" הופך ל"משתתפים" באירוע עסקי וכו'.
function pageTitles(terms: EventTerms): Record<Page, string> {
  return {
    dashboard: 'האירוע שלנו',
    guests: `ניהול ${terms.guestsLabel}`,
    messages: 'ניהול הודעות',
    rsvp: 'אישורי הגעה',
    hall: 'סידור הושבה',
  }
}

// label — הטקסט המלא בסרגל הצד (דסקטופ); short — טקסט קצר לניווט התחתון בטלפון.
// הסדר תואם את זרימת העבודה: מה לשלוח? (ניהול הודעות) → מה המצב? (אישורי הגעה).
function navItemsFor(terms: EventTerms): { key: Page; label: string; short: string }[] {
  return [
    { key: 'dashboard', label: 'תמונת מצב', short: 'בית' },
    { key: 'guests', label: `ניהול ${terms.guestsLabel}`, short: terms.guestsLabel },
    { key: 'messages', label: 'ניהול הודעות', short: 'הודעות' },
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
    case 'messages':
      return (
        <svg {...common}>
          <path d="M4 5h16v11H8l-4 3z" />
          <path d="m9 10 2 2 4-4" />
        </svg>
      )
    case 'rsvp':
      return (
        <svg {...common}>
          <rect x="5" y="3.5" width="14" height="17" rx="2" />
          <path d="M9 3.5V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v.5" />
          <path d="M8.5 12.5 11 15l4.5-5" />
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

  // ---- שלושה נתיבים מיוחדים שמגיעים מקישור במייל ----
  // /app/join?token=...           — הזמנה לניהול משותף של אירוע
  // /app/verify-email?token=...   — אימות כתובת המייל
  // /app/reset-password?token=... — איפוס סיסמה עצמאי ("שכחתי סיסמה")
  // נקראים פעם אחת בטעינה (אין router בפרויקט — הניווט הוא state פנימי).
  // נקרא פעם אחת בטעינה ולא משתנה אחר כך: יציאה מדף ההצטרפות נעשית ע"י
  // ניווט אמיתי (window.location.assign) ולא ע"י שינוי state.
  const [joinToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search)
    return window.location.pathname === '/app/join' ? params.get('token') : null
  })
  const [verifyToken, setVerifyToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search)
    return window.location.pathname === '/app/verify-email' ? params.get('token') : null
  })
  const [resetToken, setResetToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search)
    return window.location.pathname === '/app/reset-password' ? params.get('token') : null
  })
  const [verifyError, setVerifyError] = useState<string | null>(null)
  // כשמגיעים להזמנה בלי להיות מחוברים, שולחים למסך הכניסה ואז חוזרים לכאן.
  const [authIntent, setAuthIntent] = useState<
    { mode: 'login' | 'register'; email: string } | null
  >(null)
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

  // טעינת האירועים של המשתמש ובחירת האירוע הפעיל. לטלפן אין אירועים משלו
  // ואין לו הרשאה ל-/events (השרת מחזיר 403) — אז לא יורים את הבקשה בכלל.
  async function loadEvents(u?: User) {
    if ((u ?? user)?.account_type === 'phone_agent') {
      setEvents([])
      return [] as EventSummary[]
    }
    const evs = await listMyEvents().catch(() => [] as EventSummary[])
    setEvents(evs)
    const stored = getEventId()
    const chosen = evs.find((e) => e.id === stored)?.id ?? evs[0]?.id ?? null
    setActiveEventId(chosen)
    setEventId(chosen)
    return evs
  }

  // מימוש קישור אימות המייל (/verify-email?token=...). רץ **לפני** בדיקת
  // הטוקן הרגילה כי הקישור עשוי להיפתח בדפדפן שבו המשתמש כלל לא מחובר —
  // האימות עצמו מחזיר טוקן כניסה, וזה מה שמכניס אותו פנימה.
  useEffect(() => {
    if (!verifyToken) return
    let alive = true
    confirmEmailVerification(verifyToken)
      .then(async (res) => {
        if (!alive) return
        setToken(res.access_token)
        setUser(res.user)
        await loadEvents(res.user)
        // מנקים את הטוקן מה-URL כדי שלא יישאר בהיסטוריה/בשיתוף.
        // מנקים את טוקן האימות מה-URL; אם הגענו גם עם הזמנה לאירוע,
        // משאירים אותה כדי שנמשיך ישר להצטרפות. ה-React מוגש תחת /app.
        window.history.replaceState({}, '', joinToken ? `/app/join?token=${joinToken}` : '/app')
        setVerifyToken(null)
      })
      .catch((err) => {
        if (alive) setVerifyError(err instanceof Error ? err.message : 'האימות נכשל')
      })
      .finally(() => alive && setAuthChecked(true))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifyToken])

  // בדיקת טוקן קיים בעת טעינת האפליקציה.
  useEffect(() => {
    // כשיש טוקן אימות ב-URL, ה-effect שלמעלה אחראי על הכניסה — לא רצים פעמיים.
    if (verifyToken) return
    const token = getToken()
    if (!token) {
      setAuthChecked(true)
      return
    }
    getMe()
      .then(async (u) => {
        setUser(u)
        await loadEvents(u)
      })
      .catch(() => {
        /* 401 כבר טופל — נשאר לא מחובר */
      })
      .finally(() => setAuthChecked(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    await loadEvents(u)
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
    await loadEvents(u)
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

  // קישור איפוס סיסמה מהמייל — מסך עצמאי, בלי קשר למצב ההתחברות הנוכחי
  // (המשתמש בדיוק כי שכח את הסיסמה, לא בהכרח מחובר בטאב הזה בכלל).
  if (resetToken) {
    return (
      <ResetPasswordPage
        token={resetToken}
        onDone={async (u) => {
          setUser(u)
          await loadEvents(u)
          window.history.replaceState({}, '', '/app')
          setResetToken(null)
        }}
        onBack={() => {
          window.history.replaceState({}, '', '/app')
          setResetToken(null)
        }}
      />
    )
  }

  // שגיאת אימות מייל (קישור פג/לא תקין) — מסך הסבר במקום מסך לבן.
  if (verifyError) {
    return (
      <div className="join-page" dir="rtl">
        <div className="join-card">
          <div className="join-logo" dir="ltr">VEYA</div>
          <h1 className="join-title">הקישור לאימות כבר לא תקף</h1>
          <p className="join-text">{verifyError}</p>
          <button
            type="button"
            className="join-btn join-btn-primary"
            onClick={() => {
              setVerifyError(null)
              setVerifyToken(null)
              window.history.replaceState({}, '', '/app')
            }}
          >
            להתחברות
          </button>
        </div>
      </div>
    )
  }

  // לא מחובר → מסך התחברות/הרשמה. אם הגיעו דרך הזמנה לאירוע, קודם מציגים
  // את ההזמנה עצמה (מי הזמין ולאיזה אירוע) — ורק אז שולחים להתחברות, כדי
  // שהמשתמש יידע למה הוא מתבקש להתחבר.
  if (!user) {
    if (joinToken && !authIntent) {
      return (
        <JoinEventPage
          token={joinToken}
          onJoined={() => window.location.assign('/app')}
          onNeedAuth={(mode, email) => setAuthIntent({ mode, email })}
        />
      )
    }
    return (
      <AuthPage
        onAuth={handleAuth}
        initialMode={authIntent?.mode}
        lockedEmail={authIntent?.email}
      />
    )
  }

  // תנאים/פרטיות עודכנו מאז שהמשתמש אישר לאחרונה → מודל חוסם, אבל **מעל**
  // המסך האמיתי שהמשתמש נמצא בו (לא מחליף אותו). לכן זו עטיפה שמופעלת על
  // כל מסך שהיה מוצג בכל מקרה, ולא return מוקדם שמבטל את שאר הרנדור.
  const withReconsent = (view: ReactElement): ReactElement =>
    user.needs_reconsent ? (
      <>
        {view}
        <ReconsentModal onAccepted={() => setUser({ ...user, needs_reconsent: false })} />
      </>
    ) : (
      view
    )

  // הגענו דרך קישור הזמנה ואנחנו מחוברים → מסך ההצטרפות, לפני כל דבר אחר.
  // אחרי הצטרפות מוצלחת טוענים מחדש מ-/ כדי שכל המצב (אירועים, הרשאות)
  // ייבנה נקי סביב האירוע המשותף.
  if (joinToken) {
    return withReconsent(
      <JoinEventPage
        token={joinToken}
        onJoined={() => window.location.assign('/app')}
        onNeedAuth={(mode, email) => {
          handleLogout()
          setAuthIntent({ mode, email })
        }}
      />,
    )
  }

  // אדמין → פאנל ניהול מלא ונפרד (לא נכנס למסלול יצירת אירוע של זוג).
  if (user.is_admin) {
    return withReconsent(
      <Suspense fallback={bootFallback}>
        <AdminApp user={user} onLogout={handleLogout} onImpersonate={handleImpersonate} />
      </Suspense>,
    )
  }

  // טלפן → מסך "שיחות להיום" בלבד. לא Dashboard, לא מסלול יצירת אירוע, ולא
  // סרגל האדמין. ההסתרה כאן היא נוחות בלבד — ההרשאה נאכפת בשרת
  // (backend/app/roles.py), כך שגם קריאה ישירה ל-API תיחסם.
  if (user.account_type === 'phone_agent') {
    return withReconsent(
      <Suspense fallback={bootFallback}>
        <PhoneAgentApp user={user} onLogout={handleLogout} onUserUpdated={setUser} />
      </Suspense>,
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
    // הזרימה המחייבת לפני יצירת אירוע: אימות מייל → פרטים מלאים → יצירה.
    // שני השערים האלה חלים רק על מי שעתיד ליצור אירוע (זוג), ולא על
    // מפיק/אולם שממתינים לשיתוף. אותם כללים נאכפים גם בשרת
    // (backend/app/routers/events.py::create_event) — כאן זו רק החוויה.
    const isCouple = user.account_type !== 'planner' && user.account_type !== 'venue'

    if (isCouple && user.email_verified === false) {
      return withReconsent(
        withImpersonation(
          <VerifyEmailPage
            user={user}
            onUpdated={setUser}
            onRefresh={async () => {
              const u = await getMe()
              setUser(u)
              await loadEvents(u)
            }}
            onLogout={handleLogout}
          />,
        ),
      )
    }

    if (isCouple && user.profile_complete === false) {
      return withReconsent(
        withImpersonation(
          <CompleteProfilePage user={user} onUpdated={setUser} onLogout={handleLogout} />,
        ),
      )
    }

    // מפיק/אולם לא יוצרים אירוע בעצמם — הם מחכים שבעל אירוע יזמין אותם.
    if (user.account_type === 'planner' || user.account_type === 'venue') {
      return withReconsent(
        withImpersonation(
          <>
            <div className="auth-wrap">
              <div className="auth-card">
                <h1 className="first-event-title">ברוכים הבאים ל-VEYA</h1>
                <p className="auth-tagline">
                  עדיין לא שותפה איתכם גישה לאף אירוע. בקשו מבעל האירוע להוסיף
                  אתכם דרך האימייל שאיתו נרשמתם: <strong dir="ltr">{user.email}</strong>
                </p>
              </div>
            </div>
            <Footer />
          </>,
        ),
      )
    }
    return withReconsent(
      withImpersonation(
        <>
          <OnboardingWizard onCreated={handleEventCreated} />
          <Footer />
        </>,
      ),
    )
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

  return withReconsent(
    withImpersonation(
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
        {page !== 'dashboard' && (
          <header className="page-header">
            <h1 className="page-title">{pageTitle[page]}</h1>
          </header>
        )}
        <main className="content" key={`${page}-${activeEventId}`}>
          <ErrorBoundary>
            {page === 'dashboard' && (
              <DashboardPage onNavigate={(p) => setPage(p)} />
            )}
            {page === 'guests' && <GuestsPage />}
            {page === 'messages' && (
              <MessagesPage isAdmin={user.is_admin} onNavigate={(p) => setPage(p)} />
            )}
            {page === 'rsvp' && (
              <RsvpPage isAdmin={user.is_admin} onNavigate={(p) => setPage(p)} />
            )}
            {page === 'hall' && (
              <Suspense fallback={bootFallback}>
                <HallPage onNavigate={(p) => setPage(p)} />
              </Suspense>
            )}
          </ErrorBoundary>
        </main>
        <Footer />
      </div>

      {profileOpen && (
        <AccountCenter
          user={user}
          onClose={() => setProfileOpen(false)}
          onUpdated={(u) => setUser(u)}
          onLogout={() => {
            setProfileOpen(false)
            handleLogout()
          }}
        />
      )}

      {membersOpen && activeEventId != null && (
        <EventMembersDialog eventId={activeEventId} onClose={() => setMembersOpen(false)} />
      )}
    </div>,
    ),
  )
}

export default App
