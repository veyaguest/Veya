/**
 * מרכז השליטה של VEYA — נקודת הכניסה.
 *
 * Dashboard → תחום → פרטים → הגדרות מתקדמות. הניווט ב-hash (``route.ts``),
 * ההרשאות מהשרת (``/admin/me``) — ה-UI מסתיר, השרת אוכף.
 */
import { useEffect, useState, type ReactNode } from 'react'
import type { User } from '../types'
import { AdminPayoutReview } from '../components/AdminPayoutReview'
import { AdminPostponements } from '../components/AdminPostponements'
import { fetchAdminMe, type AdminOverview } from './adminApi'
import { AdminShell, pageAllowed } from './AdminShell'
import { navigate, useAdminRoute, type AdminRoute } from './route'
import { AdminSettingsPage } from './pages/AdminSettingsPage'
import { AuditPage } from './pages/AuditPage'
import { DashboardPage } from './pages/DashboardPage'
import { CallOpsPage } from './pages/calls/CallOpsPage'
import { PeoplePage } from './pages/people/PeoplePage'
import { FeaturesPage } from './pages/rules/FeaturesPage'
import { RulesPage } from './pages/rules/RulesPage'
import { RsvpPage } from './pages/rsvp/RsvpPage'
import { VenuesPage } from './pages/venues/VenuesPage'
import {
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  PermissionContext,
  ToastProvider,
  useAsync,
  useCan,
} from './ui'
import './admin.css'

export function AdminApp({
  user,
  onLogout,
  onImpersonate,
}: {
  user: User
  onLogout: () => void
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  const route = useAdminRoute()
  const me = useAsync(fetchAdminMe, [])
  const [attentionCount, setAttentionCount] = useState(0)

  useEffect(() => {
    document.title = 'VEYA · ניהול'
  }, [])

  if (me.loading && !me.data) {
    return (
      <div className="adm-root adm-boot" dir="rtl">
        <Loading />
      </div>
    )
  }
  if (!me.data) {
    return (
      <div className="adm-root adm-boot" dir="rtl">
        <ErrorState message={me.error ?? 'לא ניתן לטעון את ההרשאות'} onRetry={me.reload} />
      </div>
    )
  }

  const permissions = me.data.permissions
  return (
    <PermissionContext.Provider value={permissions}>
      <ToastProvider>
        <AdminShell user={user} me={me.data} route={route} attentionCount={attentionCount} onLogout={onLogout}>
          {pageAllowed(route.page, permissions) ? (
            <Page
              key={route.page}
              route={route}
              onImpersonate={onImpersonate}
              onOverview={(o: AdminOverview) =>
                setAttentionCount(o.attention.filter((a) => a.severity !== 'info').length)
              }
            />
          ) : (
            <div className="adm-page">
              <EmptyState
                title="אין לך הרשאה למסך הזה"
                text="הדרגה שלך לא כוללת את התחום הזה. אפשר לבקש שינוי מ-Super Admin."
                action={
                  <button type="button" className="adm-btn" onClick={() => navigate('home')}>
                    חזרה לראשי
                  </button>
                }
              />
            </div>
          )}
        </AdminShell>
      </ToastProvider>
    </PermissionContext.Provider>
  )
}

function Page({
  route,
  onImpersonate,
  onOverview,
}: {
  route: AdminRoute
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
  onOverview: (o: AdminOverview) => void
}) {
  switch (route.page) {
    case 'home':
      return <DashboardPage onLoaded={onOverview} />
    case 'people':
      return <PeoplePage route={route} onImpersonate={onImpersonate} />
    case 'venues':
      return <VenuesPage route={route} />
    case 'rsvp':
      return <RsvpPage route={route} />
    case 'calls':
      return <CallOpsPage route={route} />
    case 'postponements':
      return (
        <LegacyPage title="בקשות דחייה">
          <AdminPostponements />
        </LegacyPage>
      )
    case 'fees':
      return <FeesPage />
    case 'audit':
      return <AuditPage route={route} />
    case 'settings':
      return <AdminSettingsPage />
    case 'features':
      return <FeaturesPage />
    case 'rules':
      return <RulesPage route={route} />
    case 'plans':
    case 'addons':
    case 'coupons':
    case 'subscriptions':
      return <InProgressPage page={route.page} />
  }
}

function LegacyPage({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="adm-page adm-legacy">
      <PageHeader title={title} subtitle={subtitle} />
      {children}
    </div>
  )
}

function FeesPage() {
  const can = useCan()
  return (
    <div className="adm-page adm-legacy">
      <PageHeader title="עמלות" subtitle="עמלת המתנות ואישור פרטי חשבון לקבלת כספים" />
      {can('payouts.review') ? (
        <AdminPayoutReview />
      ) : (
        <EmptyState title="אישור פרטי חשבון זמין ל-Super Admin בלבד" />
      )}
    </div>
  )
}

const IN_PROGRESS: Record<string, string> = {
  features: "פיצ'רים והרשאות",
  rules: 'כללי המערכת',
  plans: 'מסלולים ומחירים',
  addons: 'תוספים',
  coupons: 'קופונים והטבות',
  subscriptions: 'מנויים',
}

function InProgressPage({ page }: { page: string }) {
  return (
    <div className="adm-page">
      <PageHeader title={IN_PROGRESS[page] ?? ''} />
      <EmptyState
        title="המסך הזה עדיין לא מחובר"
        text="אין עדיין נתונים או פעולות אמיתיות מאחוריו, ולכן הוא לא מציג כלום במקום להציג נתונים מזויפים."
      />
    </div>
  )
}
