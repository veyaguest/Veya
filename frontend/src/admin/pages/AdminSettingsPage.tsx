import { useState } from 'react'
import { fetchAdmins, setAdminRole, type AdminAccount, type AdminRole } from '../adminApi'
import {
  ConfirmAction,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  Section,
  StatusPill,
  fmtDateTime,
  useAsync,
  useToast,
} from '../ui'

const ROLE_OPTIONS: { value: AdminRole; label: string; desc: string }[] = [
  { value: 'support', label: 'Support', desc: 'משתמשים, אירועים וטלפנים. בלי מחיקות, מסחר או הגדרות.' },
  { value: 'admin', label: 'Admin', desc: 'ניהול שוטף: + הגדרות, אולמות, הודעות ויומן.' },
  { value: 'super_admin', label: 'Super Admin', desc: 'הכול, כולל מחיקות, מחירים, עמלות וניהול אדמינים.' },
]

type Pending = { account: AdminAccount; role: AdminRole | null }

export function AdminSettingsPage() {
  const { data, error, loading, reload } = useAsync(fetchAdmins, [])
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const toast = useToast()

  async function apply(reason: string) {
    if (!pending) return
    setBusy(true)
    setActionError(null)
    try {
      await setAdminRole(pending.account.id, pending.role, reason)
      toast(pending.role ? 'הדרגה עודכנה' : 'הרשאת האדמין הוסרה')
      setPending(null)
      reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'הפעולה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adm-page">
      <PageHeader title="הגדרות Admin" subtitle="מי מנהל את VEYA ובאיזו דרגה" />

      <Section
        title="אדמינים"
        description="כדי להפוך משתמש קיים לאדמין: משתמשים ואירועים ← פרטי המשתמש. כאן קובעים את הדרגה."
      >
        {loading && !data ? (
          <Loading />
        ) : error && !data ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState title="אין אדמינים" />
        ) : (
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>שם</th>
                  <th>דרגה</th>
                  <th className="adm-hide-sm">נוצר</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="adm-cell-title">{a.display_name || a.email}</div>
                      <div className="adm-cell-sub">{a.email}</div>
                    </td>
                    <td>
                      {a.is_self ? (
                        <span>
                          {a.role_label} <span className="adm-muted">(את/ה)</span>
                        </span>
                      ) : (
                        <select
                          className="adm-input adm-input-sm"
                          value={a.role}
                          aria-label={`דרגה של ${a.email}`}
                          onChange={(e) => setPending({ account: a, role: e.target.value as AdminRole })}
                        >
                          {ROLE_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      )}
                      {a.disabled && <StatusPill tone="bad">חסום</StatusPill>}
                    </td>
                    <td className="adm-hide-sm adm-muted">{fmtDateTime(a.created_at)}</td>
                    <td className="adm-col-action">
                      {!a.is_self && (
                        <button
                          type="button"
                          className="adm-link-btn adm-danger-text"
                          onClick={() => setPending({ account: a, role: null })}
                        >
                          הסרת הרשאה
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="מה כל דרגה יכולה">
        <dl className="adm-defs">
          {ROLE_OPTIONS.map((o) => (
            <div key={o.value}>
              <dt>{o.label}</dt>
              <dd>{o.desc}</dd>
            </div>
          ))}
        </dl>
        <p className="adm-quiet">ההרשאות נאכפות בשרת. שינוי דרגה מנתק את המשתמש מכל המכשירים.</p>
      </Section>

      <ConfirmAction
        open={pending !== null}
        title={pending?.role ? 'שינוי דרגת אדמין' : 'הסרת הרשאת אדמין'}
        body={
          pending && (
            <p>
              {pending.role
                ? `${pending.account.email} יקבל/תקבל דרגת ${ROLE_OPTIONS.find((o) => o.value === pending.role)?.label}.`
                : `${pending.account.email} יאבד/תאבד את הגישה לניהול.`}{' '}
              המשתמש ינותק מכל המכשירים.
            </p>
          )
        }
        confirmLabel={pending?.role ? 'שינוי דרגה' : 'הסרת הרשאה'}
        danger={!pending?.role || pending.role === 'super_admin'}
        typeToConfirm={!pending?.role || pending.role === 'super_admin' ? pending?.account.email : undefined}
        requireReason
        busy={busy}
        error={actionError}
        onConfirm={apply}
        onCancel={() => {
          setPending(null)
          setActionError(null)
          reload()
        }}
      />
    </div>
  )
}
