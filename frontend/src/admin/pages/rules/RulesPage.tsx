import { useMemo, useState } from 'react'
import { rules, showValue, type SettingRow, type SettingValue } from '../../rulesApi'
import { navigate, type AdminRoute } from '../../route'
import {
  ConfirmAction,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SourceTag,
  StatusPill,
  Tabs,
  useAsync,
  useToast,
} from '../../ui'
import { SettingControl } from './SettingControl'

export function RulesPage({ route }: { route: AdminRoute }) {
  const toast = useToast()
  const data = useAsync(rules.get, [])
  const [draft, setDraft] = useState<Record<string, SettingValue>>({})
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stopConfirm, setStopConfirm] = useState<boolean | null>(null)

  const domains = data.data?.domains ?? {}
  const domain = route.params.get('domain') && domains[route.params.get('domain') as string] ? (route.params.get('domain') as string) : 'rsvp'
  const settings = data.data?.settings ?? []
  const byKey = useMemo(() => Object.fromEntries(settings.map((s) => [s.key, s])), [settings])
  const changed = Object.entries(draft).filter(([k, v]) => byKey[k] && byKey[k].value !== v)

  async function save(reason: string, changes: Record<string, SettingValue>) {
    setBusy(true)
    setError(null)
    try {
      const r = await rules.save(changes, reason)
      data.setData(data.data ? { ...data.data, settings: r.settings } : null)
      setDraft({})
      setReview(false)
      setStopConfirm(null)
      toast(r.updated ? `${r.updated} כללים נשמרו` : 'לא היו שינויים')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'השמירה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data
  if (!d) return null

  const stop = byKey['whatsapp.emergency_stop']
  const visible = settings.filter((s) => s.domain === domain && s.key !== 'whatsapp.emergency_stop')

  return (
    <div className="adm-page">
      <PageHeader title="כללי המערכת" subtitle="ברירות המחדל של VEYA. אירוע מסוים יכול לקבל Override ממסך האירוע." />

      {stop?.value === true && (
        <div className="adm-banner adm-banner-bad" role="alert">
          <strong>עצירת חירום פעילה</strong> — אף הודעת WhatsApp לא יוצאת במערכת.
          {d.can_edit_critical && (
            <button type="button" className="adm-btn adm-btn-sm" onClick={() => setStopConfirm(false)}>
              הסרת העצירה
            </button>
          )}
        </div>
      )}

      <Tabs
        label="תחומים"
        tabs={Object.entries(domains).map(([k, label]) => ({ key: k, label }))}
        active={domain}
        onChange={(k) => navigate('rules', null, k === 'rsvp' ? {} : { domain: k }, { replace: true })}
      />

      {domain === 'whatsapp' && stop && (
        <section className="adm-danger-zone adm-danger-top">
          <div>
            <strong>{stop.label}</strong>
            <p className="adm-muted">{stop.help}</p>
          </div>
          {d.can_edit_critical ? (
            <button
              type="button"
              className={`adm-btn ${stop.value ? '' : 'adm-btn-danger'}`}
              onClick={() => setStopConfirm(!stop.value)}
            >
              {stop.value ? 'הסרת העצירה' : 'עצירת כל השליחות'}
            </button>
          ) : (
            <StatusPill tone={stop.value ? 'bad' : 'ok'}>{stop.value ? 'עצור' : 'שליחה רגילה'}</StatusPill>
          )}
        </section>
      )}

      {visible.length === 0 ? (
        <EmptyState title="אין הגדרות בתחום הזה" />
      ) : (
        <ul className="adm-settings">
          {visible.map((s) => (
            <SettingItem
              key={s.key}
              s={s}
              value={s.key in draft ? draft[s.key] : s.value}
              canEdit={d.can_edit && s.live}
              onChange={(v) => setDraft((prev) => ({ ...prev, [s.key]: v }))}
              onReset={() => setDraft((prev) => ({ ...prev, [s.key]: s.default }))}
            />
          ))}
        </ul>
      )}

      {changed.length > 0 && (
        <div className="adm-savebar" role="region" aria-label="שינויים שלא נשמרו">
          <span>{changed.length} שינויים שלא נשמרו</span>
          <button type="button" className="adm-btn" onClick={() => setDraft({})}>ביטול</button>
          <button type="button" className="adm-btn adm-btn-primary" onClick={() => setReview(true)}>בדיקה ושמירה</button>
        </div>
      )}

      <ConfirmAction
        open={review}
        title="שמירת כללי מערכת"
        body={
          <>
            <ul className="adm-plain-list">
              {changed.map(([k, v]) => (
                <li key={k}>
                  {byKey[k].label}: <span className="adm-before">{showValue(byKey[k], byKey[k].value)}</span> ←{' '}
                  <strong>{showValue(byKey[k], v)}</strong>
                </li>
              ))}
            </ul>
            <p className="adm-muted">השינוי חל על כל האירועים שאין להם Override, כולל אירועים שהמסלול שלהם כבר פעיל.</p>
          </>
        }
        confirmLabel="שמירה"
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => save(reason, Object.fromEntries(changed))}
        onCancel={() => setReview(false)}
      />
      <ConfirmAction
        open={stopConfirm !== null}
        title={stopConfirm ? 'עצירת חירום לכל שליחות WhatsApp' : 'הסרת עצירת החירום'}
        body={
          <p>
            {stopConfirm
              ? 'מרגע האישור אף הודעה לא תצא לאף מוזמן, בכל האירועים. ניסיונות שליחה יירשמו כנכשלים וניתן יהיה לשלוח שוב אחרי ההסרה.'
              : 'השליחות יחזרו לפעול לפי לוח הזמנים של כל אירוע.'}
          </p>
        }
        confirmLabel={stopConfirm ? 'עצירת כל השליחות' : 'הסרת העצירה'}
        danger={Boolean(stopConfirm)}
        typeToConfirm={stopConfirm ? 'עצירה' : undefined}
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => save(reason, { 'whatsapp.emergency_stop': Boolean(stopConfirm) })}
        onCancel={() => setStopConfirm(null)}
      />
    </div>
  )
}

function SettingItem({
  s,
  value,
  canEdit,
  onChange,
  onReset,
}: {
  s: SettingRow
  value: SettingValue
  canEdit: boolean
  onChange: (v: SettingValue) => void
  onReset: () => void
}) {
  const dirty = value !== s.value
  return (
    <li className={`adm-setting${dirty ? ' is-dirty' : ''}`}>
      <div className="adm-setting-text">
        <div className="adm-setting-label">{s.label}</div>
        {s.help && <div className="adm-setting-help">{s.help}</div>}
        {!s.live && s.readonly_reason && <div className="adm-setting-help adm-setting-ro">{s.readonly_reason}</div>}
      </div>
      <div className="adm-setting-control">
        {s.live && canEdit ? (
          <SettingControl setting={s} value={value} onChange={onChange} />
        ) : (
          <strong>{s.source === 'env' ? String(s.value) : showValue(s, s.value)}</strong>
        )}
        <div className="adm-setting-meta">
          {s.source === 'env' ? (
            <span className="adm-source">משתנה סביבה בשרת</span>
          ) : (
            <SourceTag source={s.source} fallback={s.source === 'system' ? showValue(s, s.default) : undefined} />
          )}
          {canEdit && s.live && s.source === 'system' && value !== s.default && (
            <button type="button" className="adm-link-btn" onClick={onReset}>איפוס</button>
          )}
        </div>
      </div>
    </li>
  )
}
