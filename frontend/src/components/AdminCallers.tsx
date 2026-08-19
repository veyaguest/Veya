import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  adminCreateAccount,
  adminDisableUser,
  adminEnableUser,
  adminListCallers,
  adminSetCallerAssignments,
} from '../api'
import type { AdminCallerEventOption, AdminCallersPage } from '../types'
import './AdminCallers.css'

/**
 * ניהול טלפנים (``account_type = 'phone_agent'``) בפאנל האדמין.
 *
 * המסך הזה לא הוסיף שום מנגנון חדש — הוא רק ממשק למה שכבר קיים:
 * - יצירה   → ``POST /admin/accounts`` (אותו מסלול של מפיק/אולם).
 * - השבתה   → ``POST /admin/users/{id}/disable`` הקיים, שכבר פוסל גם טוקן פעיל.
 * - הקצאה   → ``call_assignments`` שנבנתה עם התפקיד.
 * - מונים    → ``call_logs`` ותור השיחות הקיים, לא טבלת סטטיסטיקות חדשה.
 *
 * ההרשאות נאכפות בשרת (``get_current_admin``); ההסתרה כאן היא נוחות בלבד.
 */

function eventDateText(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : iso
}

export function AdminCallers() {
  const [data, setData] = useState<AdminCallersPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [assigning, setAssigning] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [query, setQuery] = useState('')

  const reload = useCallback(async () => {
    try {
      setData(await adminListCallers())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת רשימת הטלפנים נכשלה')
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  async function toggleDisabled(userId: number, disabled: boolean) {
    setError(null)
    try {
      if (disabled) {
        await adminEnableUser(userId)
        setNotice('הטלפן הופעל מחדש')
      } else {
        await adminDisableUser(userId)
        setNotice('הטלפן הושבת. היסטוריית השיחות שלו נשמרת במלואה.')
      }
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'הפעולה נכשלה')
    }
  }

  if (error && !data) return <div className="admin-error">{error}</div>
  if (!data) return <div className="admin-loading">טוען…</div>

  const eventsById = new Map(data.events.map((e) => [e.event_id, e]))
  const q = query.trim().toLowerCase()
  const visible = q
    ? data.callers.filter(
        (c) =>
          c.display_name.toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q) ||
          c.phone.includes(q),
      )
    : data.callers

  return (
    <div className="ac-wrap">
      <div className="ac-head">
        <div>
          <h2 className="admin-section-title">ניהול טלפנים</h2>
          <p className="ac-sub">
            טלפן רואה אך ורק את מסך "שיחות להיום". בלי הקצאה הוא מקבל את התור
            המשותף; ברגע שמקצים לו אירועים — הוא רואה רק אותם.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
          + הוסף טלפן
        </button>
      </div>

      {data.callers.length > 0 && (
        <div className="ac-listhead">
          <span className="ac-count">
            {visible.length}
            {visible.length !== data.callers.length ? ` מתוך ${data.callers.length}` : ''} טלפנים
          </span>
          <input
            type="search"
            className="adm-search"
            placeholder="חיפוש לפי שם, אימייל או טלפון…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}

      {error && <div className="admin-error">{error}</div>}
      {notice && <div className="ac-notice">{notice}</div>}

      {data.callers.length === 0 ? (
        <div className="ac-empty">
          עדיין אין טלפנים במערכת. "הוסף טלפן" יוצר חשבון עם סיסמה זמנית.
        </div>
      ) : visible.length === 0 ? (
        <div className="ac-empty">אין טלפן שמתאים לחיפוש הזה.</div>
      ) : (
        <div className="ac-list">
          {visible.map((c) => {
            const assigned = c.assigned_event_ids
              .map((id) => eventsById.get(id))
              .filter((e): e is AdminCallerEventOption => !!e)
            return (
              <div key={c.id} className={`ac-card ${c.disabled ? 'ac-card-off' : ''}`}>
                <div className="ac-card-top">
                  <div className="ac-identity">
                    <span className="ac-name">{c.display_name || c.email}</span>
                    <span className={`ac-status ${c.disabled ? 'off' : 'on'}`}>
                      {c.disabled ? 'מושבת' : 'פעיל'}
                    </span>
                  </div>
                  <div className="ac-actions">
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => setAssigning(c.id)}
                    >
                      הקצאת אירועים
                    </button>
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => toggleDisabled(c.id, c.disabled)}
                    >
                      {c.disabled ? 'הפעלה' : 'השבתה'}
                    </button>
                  </div>
                </div>

                <div className="ac-contact">
                  <span dir="ltr">{c.email}</span>
                  {c.phone && (
                    <>
                      <span className="ac-dot">·</span>
                      <span dir="ltr">{c.phone}</span>
                    </>
                  )}
                </div>

                <div className="ac-metrics">
                  <span className="ac-metric">
                    <strong>{c.calls_made}</strong> שיחות שביצע
                  </span>
                  <span className="ac-metric">
                    <strong>{c.waiting_tasks}</strong> ממתינות לו
                  </span>
                </div>

                <div className="ac-assigned">
                  {assigned.length === 0 ? (
                    <span className="ac-shared">תור משותף — כל האירועים הפתוחים</span>
                  ) : (
                    assigned.map((e) => (
                      <span key={e.event_id} className="ac-chip">
                        {e.hosts}
                      </span>
                    ))
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {creating && (
        <CreateCallerDialog
          onClose={() => setCreating(false)}
          onCreated={() => {
            void reload()
          }}
        />
      )}

      {assigning !== null && (
        <AssignEventsDialog
          caller={data.callers.find((c) => c.id === assigning)!}
          events={data.events}
          onClose={() => setAssigning(null)}
          onSaved={() => {
            setAssigning(null)
            setNotice('ההקצאה עודכנה')
            void reload()
          }}
        />
      )}
    </div>
  )
}

/** יצירת טלפן — אותו endpoint של מפיק/אולם, עם סיסמה זמנית למסירה. */
function CreateCallerDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ email: string; temporary_password: string } | null>(
    null,
  )

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await adminCreateAccount({
        email: email.trim(),
        display_name: displayName.trim(),
        account_type: 'phone_agent',
      })
      setResult({ email: res.email, temporary_password: res.temporary_password })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'יצירת הטלפן נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog ac-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>הוספת טלפן</h3>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>
        <div className="dialog-body">
          {result ? (
            <>
              <div className="ac-notice">
                החשבון נוצר עבור <strong dir="ltr">{result.email}</strong>.
              </div>
              <label className="adm-field">
                <span className="adm-field-label">סיסמה זמנית — למסירה חד-פעמית</span>
                <input className="adm-field-input" dir="ltr" readOnly value={result.temporary_password} />
              </label>
              <p className="ac-hint">
                הטלפן מתחבר עם האימייל והסיסמה הזו, ומחליף אותה בעצמו במסך
                "החשבון שלי". הסיסמה לא תוצג שוב.
              </p>
              <button type="button" className="btn-primary" onClick={onClose}>
                סיום
              </button>
            </>
          ) : (
            <form onSubmit={submit} className="ac-form">
              <label className="adm-field">
                <span className="adm-field-label">שם מלא</span>
                <input
                  className="adm-field-input"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="דנה כהן"
                  required
                />
              </label>
              <label className="adm-field">
                <span className="adm-field-label">אימייל להתחברות</span>
                <input
                  className="adm-field-input"
                  type="email"
                  dir="ltr"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="dana@example.com"
                  required
                />
              </label>
              <p className="ac-hint">
                המערכת תייצר סיסמה זמנית. אין הרשמה עצמאית לטלפנים — רק אדמין
                יוצר להם חשבון.
              </p>
              {error && <div className="admin-error">{error}</div>}
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? 'רגע…' : 'יצירת טלפן'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

/** בחירת האירועים שהטלפן יעבוד עליהם. ריק = תור משותף. */
function AssignEventsDialog({
  caller,
  events,
  onClose,
  onSaved,
}: {
  caller: { id: number; display_name: string; email: string; assigned_event_ids: number[] }
  events: AdminCallerEventOption[]
  onClose: () => void
  onSaved: () => void
}) {
  const [selected, setSelected] = useState<number[]>(caller.assigned_event_ids)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return events
    return events.filter(
      (e) =>
        e.hosts.toLowerCase().includes(q) ||
        e.venue_name.toLowerCase().includes(q) ||
        String(e.event_id) === q,
    )
  }, [events, query])

  function toggle(eventId: number) {
    setSelected((prev) =>
      prev.includes(eventId) ? prev.filter((id) => id !== eventId) : [...prev, eventId],
    )
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await adminSetCallerAssignments(caller.id, selected)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שמירת ההקצאה נכשלה')
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog ac-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>הקצאת אירועים · {caller.display_name || caller.email}</h3>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>
        <div className="dialog-body">
          <p className="ac-hint">
            {selected.length === 0
              ? 'בלי סימון אף אירוע — הטלפן מקבל את התור המשותף (כל האירועים הפתוחים).'
              : `נבחרו ${selected.length} אירועים. הטלפן יראה רק אותם.`}
          </p>
          <input
            type="search"
            className="adm-search ac-search"
            placeholder="חיפוש אירוע…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="ac-events">
            {filtered.length === 0 ? (
              <div className="ac-empty">אין אירוע שמתאים לחיפוש.</div>
            ) : (
              filtered.map((e) => (
                <label key={e.event_id} className="ac-event">
                  <input
                    type="checkbox"
                    checked={selected.includes(e.event_id)}
                    onChange={() => toggle(e.event_id)}
                  />
                  <span className="ac-event-body">
                    <span className="ac-event-name">{e.hosts}</span>
                    <span className="ac-event-meta">
                      {e.event_date && <span>{eventDateText(e.event_date)}</span>}
                      {e.venue_name && (
                        <>
                          <span className="ac-dot">·</span>
                          <span>{e.venue_name}</span>
                        </>
                      )}
                      {e.waiting > 0 && (
                        <>
                          <span className="ac-dot">·</span>
                          <span className="ac-waiting">{e.waiting} שיחות ממתינות</span>
                        </>
                      )}
                    </span>
                  </span>
                </label>
              ))
            )}
          </div>
          {error && <div className="admin-error">{error}</div>}
          <div className="ac-dialog-actions">
            <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
              ביטול
            </button>
            <button type="button" className="btn-primary" onClick={save} disabled={busy}>
              {busy ? 'רגע…' : 'שמירת ההקצאה'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
