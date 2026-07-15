import { useState } from 'react'
import { createMyEvent, updateEvent } from '../api'
import { setEventId } from '../authStore'
import type { EventSummary } from '../types'
import { VenueAutocomplete } from './VenueAutocomplete'
import { AddGuestForm } from './AddGuestForm'

interface Props {
  onCreated: (ev: EventSummary) => void
}

type StepKey = 'details' | 'guests'

const STEPS: { key: StepKey; label: string; desc: string }[] = [
  { key: 'details', label: 'פרטי האירוע', desc: 'שמות, אולם, תאריך ותמונת ההזמנה' },
  { key: 'guests', label: 'הוספת מוזמנים', desc: 'אפשר להוסיף עוד בהמשך' },
]

/**
 * אשף פתיחה מדורג לזוג חדש שאין לו עדיין אירוע — שני שלבים:
 * (1) כל פרטי האירוע, באותם שדות שקיימים במסך עריכת האירוע בדשבורד;
 * (2) התחלת רשימת המוזמנים, עם אפשרות לדלג ולהמשיך אחר כך.
 * בסיום (או בדילוג) קורא ל-onCreated בדיוק כמו FirstEventScreen הישן,
 * כדי שהניווט להמשך האפליקציה יישאר זהה.
 */
export function OnboardingWizard({ onCreated }: Props) {
  const [step, setStep] = useState<StepKey>('details')
  const [event, setEvent] = useState<EventSummary | null>(null)
  const [guestCount, setGuestCount] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const [form, setForm] = useState({
    groom_name: '',
    bride_name: '',
    venue_name: '',
    venue_address: '',
    event_date: '',
    event_time: '',
    invite_image: '' as string,
    venue_commit_days_before: '' as number | '',
  })

  function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('אפשר להעלות קובץ תמונה בלבד')
      return
    }
    if (file.size > 3 * 1024 * 1024) {
      setError('התמונה גדולה מדי — עד 3MB')
      return
    }
    setError('')
    const reader = new FileReader()
    reader.onload = () =>
      setForm((f) => ({ ...f, invite_image: String(reader.result) }))
    reader.readAsDataURL(file)
  }

  async function submitDetails(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!form.groom_name.trim() || !form.bride_name.trim()) {
      setError('נשמח לדעת קודם את שמות בני הזוג')
      return
    }
    setBusy(true)
    try {
      const ev = await createMyEvent({
        groom_name: form.groom_name,
        bride_name: form.bride_name,
        venue_name: form.venue_name,
      })
      // עוברים לאירוע החדש מיד, כדי שהעדכון הבא (updateEvent) ידע על איזה אירוע לדבר.
      setEventId(ev.id)

      const rest: Parameters<typeof updateEvent>[0] = {}
      if (form.venue_address.trim()) rest.venue_address = form.venue_address
      if (form.event_date) rest.event_date = form.event_date
      if (form.event_time) rest.event_time = form.event_time
      if (form.invite_image) rest.invite_image = form.invite_image
      if (form.venue_commit_days_before !== '') {
        rest.venue_commit_days_before = form.venue_commit_days_before
      }
      if (Object.keys(rest).length > 0) {
        await updateEvent(rest)
      }

      setEvent(ev)
      setStep('guests')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו ליצור את האירוע, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  function finish() {
    if (event) onCreated(event)
  }

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  return (
    <div className="onboard-wrap" dir="rtl">
      <div className="onboard-card">
        <div className="onboard-logo" dir="ltr">
          <span className="auth-monogram">
            <span className="auth-monogram-diamond" />
            <span className="auth-monogram-v">V</span>
          </span>
          <span className="onboard-logo-name">VEYA</span>
        </div>

        <h1 className="onboard-title">ברוכים הבאים ל-VEYA</h1>
        <p className="onboard-subtitle">
          בואו נכיר את האירוע שלכם — זה ייקח רק כמה דקות
        </p>

        <ol className="onboard-steps">
          {STEPS.map((s, i) => {
            const state = step === s.key ? 'current' : stepIndex > i ? 'done' : 'todo'
            return (
              <li key={s.key} className={`onboard-step-pill ${state}`}>
                <span className="wizard-num">{state === 'done' ? '✓' : i + 1}</span>
                <span className="wizard-step-text">
                  <span className="wizard-step-label">{s.label}</span>
                  <span className="wizard-step-desc">{s.desc}</span>
                </span>
              </li>
            )
          })}
        </ol>

        {step === 'details' ? (
          <form className="event-edit onboard-details-step" onSubmit={submitDetails}>
            <div className="event-fields">
              <input
                placeholder="שם החתן"
                value={form.groom_name}
                onChange={(e) => setForm({ ...form, groom_name: e.target.value })}
              />
              <input
                placeholder="שם הכלה"
                value={form.bride_name}
                onChange={(e) => setForm({ ...form, bride_name: e.target.value })}
              />
              <VenueAutocomplete
                value={form.venue_name}
                onChange={(name) => setForm({ ...form, venue_name: name })}
                onPick={(name, address) =>
                  setForm((f) => ({
                    ...f,
                    venue_name: name,
                    venue_address: f.venue_address.trim() ? f.venue_address : address,
                  }))
                }
                placeholder="שם האולם"
              />
              <input
                placeholder="כתובת האולם (לניווט בהודעות)"
                value={form.venue_address}
                onChange={(e) => setForm({ ...form, venue_address: e.target.value })}
              />
            </div>

            <div className="event-datetime">
              <label className="field-group">
                <span className="field-label">תאריך האירוע</span>
                <input
                  type="date"
                  value={form.event_date}
                  onChange={(e) => setForm({ ...form, event_date: e.target.value })}
                />
              </label>
              <label className="field-group">
                <span className="field-label">שעת האירוע</span>
                <input
                  type="time"
                  value={form.event_time}
                  onChange={(e) => setForm({ ...form, event_time: e.target.value })}
                />
              </label>
            </div>

            <div className="commit-field">
              <span className="field-label">יום ההתחייבות לאולם</span>
              <p className="commit-explain">
                כמה ימים לפני החתונה אתם צריכים למסור לאולם מספר סופי? זה היום
                שבו כל אישורי ההגעה נסגרים. אפשר גם להשלים את זה מאוחר יותר.
              </p>
              <select
                className="commit-select"
                value={form.venue_commit_days_before}
                onChange={(e) =>
                  setForm({
                    ...form,
                    venue_commit_days_before:
                      e.target.value === '' ? '' : Number(e.target.value),
                  })
                }
              >
                <option value="">בחרו מספר ימים… (אפשר גם בהמשך)</option>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n} ימים לפני האירוע
                  </option>
                ))}
              </select>
            </div>

            <div className="event-image-edit">
              <span className="event-image-label">תמונת ההזמנה</span>
              {form.invite_image ? (
                <div className="event-image-has">
                  <img
                    className="event-image-thumb"
                    src={form.invite_image}
                    alt="תצוגה מקדימה של ההזמנה"
                  />
                  <button
                    type="button"
                    className="btn-text"
                    onClick={() => setForm({ ...form, invite_image: '' })}
                  >
                    הסרת התמונה
                  </button>
                </div>
              ) : (
                <label className="event-image-drop">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={onPickImage}
                    style={{ display: 'none' }}
                  />
                  <span>⬆ העלאת תמונת הזמנה</span>
                  <small>זו התמונה שתישלח למוזמנים בהזמנה — אפשר להוסיף גם בהמשך</small>
                </label>
              )}
            </div>

            {error && <div className="auth-error">{error}</div>}

            <div className="onboard-actions">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? 'רגע…' : 'המשך →'}
              </button>
            </div>
          </form>
        ) : (
          <div className="onboard-guest-step">
            <p className="onboard-subtitle onboard-guest-intro">
              בואו נתחיל את הרשימה — אפשר להוסיף עוד מוזמנים ולסדר בקבוצות בכל
              שלב, גם אחרי שממשיכים ללוח הבקרה.
            </p>
            {guestCount > 0 && (
              <p className="onboard-guest-count">הוספתם {guestCount} מוזמנים ✓</p>
            )}
            <AddGuestForm onAdded={() => setGuestCount((c) => c + 1)} onCancel={() => {}} />

            <div className="onboard-actions">
              <button type="button" className="btn-primary" onClick={finish}>
                סיימנו — קדימה ללוח הבקרה
              </button>
              <button type="button" className="onboard-skip" onClick={finish}>
                נמשיך אחר כך
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
