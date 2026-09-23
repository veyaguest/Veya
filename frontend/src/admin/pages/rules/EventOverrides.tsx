import { useState } from 'react'
import { rules, showValue, type SettingValue } from '../../rulesApi'
import { ConfirmAction, ErrorState, Loading, SourceTag, StatusPill, useAsync, useToast } from '../../ui'
import { SettingControl } from './SettingControl'

/** Overrides לאירוע אחד — מוצג במרכז השליטה של האירוע. */
export function EventOverrides({ eventId }: { eventId: number }) {
  const toast = useToast()
  const data = useAsync(() => rules.event(eventId), [eventId])
  const [draft, setDraft] = useState<Record<string, SettingValue | null>>({})
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [featureChange, setFeatureChange] = useState<{ key: string; label: string; enabled: boolean } | null>(null)

  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data
  if (!d) return null
  const overrides = d.settings.filter((s) => s.source === 'event').length
  const byKey = Object.fromEntries(d.settings.map((s) => [s.key, s]))
  const changed = Object.entries(draft)

  async function save(reason: string) {
    setBusy(true)
    setError(null)
    try {
      const r = await rules.saveEvent(eventId, draft, reason)
      data.setData(r)
      setDraft({})
      setReview(false)
      toast('ה-Overrides נשמרו')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'השמירה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  async function saveFeature(reason: string) {
    if (!featureChange) return
    setBusy(true)
    setError(null)
    try {
      await rules.addRule(featureChange.key, { scope_type: 'event', scope_id: eventId, enabled: featureChange.enabled, note: reason })
      setFeatureChange(null)
      data.reload()
      toast('עודכן')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'השמירה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="adm-section" aria-labelledby="ev-overrides">
      <div className="adm-section-head">
        <div>
          <h2 id="ev-overrides" className="adm-section-title">
            כללים לאירוע {overrides > 0 && <StatusPill tone="warn">{overrides} Overrides</StatusPill>}
          </h2>
          <p className="adm-section-desc">כל ערך מגיע מברירת המערכת, אלא אם נקבע Override לאירוע הזה.</p>
        </div>
      </div>
      <ul className="adm-settings">
        {d.settings.map((s) => {
          const inDraft = s.key in draft
          const value = inDraft ? (draft[s.key] ?? s.system_value) : s.value
          const source = inDraft ? (draft[s.key] === null ? 'system' : 'event') : s.source
          return (
            <li key={s.key} className={`adm-setting${inDraft ? ' is-dirty' : ''}`}>
              <div className="adm-setting-text">
                <div className="adm-setting-label">{s.label}</div>
              </div>
              <div className="adm-setting-control">
                {d.can_edit ? (
                  <SettingControl setting={s} value={value as SettingValue} onChange={(v) => setDraft((p) => ({ ...p, [s.key]: v }))} />
                ) : (
                  <strong>{showValue(s, s.value)}</strong>
                )}
                <div className="adm-setting-meta">
                  <SourceTag source={source === 'code' ? 'system' : source} fallback={source === 'event' ? showValue(s, s.system_value) : undefined} />
                  {d.can_edit && source === 'event' && (
                    <button type="button" className="adm-link-btn" onClick={() => setDraft((p) => ({ ...p, [s.key]: null }))}>
                      חזרה לברירת המערכת
                    </button>
                  )}
                </div>
              </div>
            </li>
          )
        })}
        {d.features.map((f) => (
          <li key={f.key} className="adm-setting">
            <div className="adm-setting-text">
              <div className="adm-setting-label">{f.label}</div>
            </div>
            <div className="adm-setting-control">
              {f.controllable && d.can_edit ? (
                <button
                  type="button"
                  role="switch"
                  aria-checked={f.enabled}
                  aria-label={f.label}
                  className={`adm-switch${f.enabled ? ' is-on' : ''}`}
                  onClick={() => setFeatureChange({ key: f.key, label: f.label, enabled: !f.enabled })}
                >
                  <span className="adm-switch-knob" />
                </button>
              ) : (
                <strong>{f.enabled ? 'פעיל' : 'כבוי'}</strong>
              )}
              <div className="adm-setting-meta">
                <SourceTag source={f.source === 'event_rule' ? 'event' : f.source === 'user_rule' ? 'user' : 'system'} />
              </div>
            </div>
          </li>
        ))}
      </ul>
      {d.track_active && changed.some(([k]) => k === 'rsvp.max_rounds') && (
        <p className="adm-inline-error">מסלול אישורי ההגעה כבר התחיל — שינוי במספר הסבבים מחשב מחדש את הסבבים שעוד לא הגיעו. סבבים שכבר עברו לא נשלחים שוב.</p>
      )}
      {changed.length > 0 && (
        <div className="adm-row-actions">
          <button type="button" className="adm-btn" onClick={() => setDraft({})}>ביטול</button>
          <button type="button" className="adm-btn adm-btn-primary" onClick={() => setReview(true)}>בדיקה ושמירה</button>
        </div>
      )}
      <ConfirmAction
        open={review}
        title="שמירת Overrides לאירוע"
        body={
          <ul className="adm-plain-list">
            {changed.map(([k, v]) => (
              <li key={k}>
                {byKey[k].label}: {v === null ? `חזרה לברירת המערכת (${showValue(byKey[k], byKey[k].system_value)})` : showValue(byKey[k], v)}
              </li>
            ))}
          </ul>
        }
        confirmLabel="שמירה"
        requireReason
        busy={busy}
        error={error}
        onConfirm={save}
        onCancel={() => setReview(false)}
      />
      <ConfirmAction
        open={featureChange !== null}
        title={`${featureChange?.enabled ? 'הפעלת' : 'כיבוי'} ${featureChange?.label ?? ''} לאירוע`}
        body={<p>החריגה חלה רק על האירוע הזה ונרשמת ביומן.</p>}
        confirmLabel={featureChange?.enabled ? 'הפעלה' : 'כיבוי'}
        danger={featureChange?.enabled === false}
        requireReason
        busy={busy}
        error={error}
        onConfirm={saveFeature}
        onCancel={() => setFeatureChange(null)}
      />
    </section>
  )
}
