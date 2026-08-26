import { useRef, useState } from 'react'
import { createMyEvent, invitePartner, updateEvent } from '../api'
import { setActiveEventType, setEventId } from '../authStore'
import type { EventSummary, EventType } from '../types'
import { EVENT_TYPE_OPTIONS, getEventTerms } from '../strings/eventTypes'
import { VenueAutocomplete } from './VenueAutocomplete'
import { TimePicker } from './TimePicker'
import { EventTypeIcon } from './EventTypeIcon'
import { AddGuestForm } from './AddGuestForm'
import { ContactsImportDialog, isContactPickerSupported } from './ContactsImportDialog'
import { ImportDialog } from './ImportDialog'
import { PasteImportDialog } from './PasteImportDialog'
import { strings } from '../strings/he'

const t = strings.guests
// נבדק פעם אחת בטעינת המודול — בדיוק כמו ב-GuestsPage.
const contactsSupported = isContactPickerSupported()

interface Props {
  onCreated: (ev: EventSummary) => void
}

type StepKey = 'details' | 'partner' | 'guests'

const STEPS: { key: StepKey; label: string; desc: string }[] = [
  { key: 'details', label: 'פרטי האירוע', desc: 'שמות, אולם, תאריך ותמונת ההזמנה' },
  { key: 'partner', label: 'ניהול משותף', desc: 'להזמין את בן/בת הזוג' },
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
  // שלב ההזמנה לניהול משותף — לעולם לא חוסם: אפשר לדלג ולחזור לזה מהדשבורד.
  const [partnerEmail, setPartnerEmail] = useState('')
  const [partnerSentTo, setPartnerSentTo] = useState<string | null>(null)

  // שלב 3 (הוספת מוזמנים): אותם מנגנוני ייבוא בדיוק כמו ב-GuestsPage — כאן
  // רק בפריסה בולטת יותר. ההוספה הידנית נשארת זמינה אך מתחילה מקופלת,
  // כדי שדרכי הייבוא (המהירות יותר לרשימה קיימת) יהיו הפעולה הראשית.
  const fileInput = useRef<HTMLInputElement>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [showPaste, setShowPaste] = useState(false)
  const [showContacts, setShowContacts] = useState(false)
  const [showManualForm, setShowManualForm] = useState(false)

  const [form, setForm] = useState({
    event_type: 'wedding' as EventType,
    groom_name: '',
    bride_name: '',
    venue_name: '',
    venue_address: '',
    event_date: '',
    event_time: '',
    invite_image: '' as string,
    venue_commit_days_before: '' as number | '',
  })

  // מנוע המונחים לפי סוג האירוע שנבחר — קובע תוויות שדות, ולידציה וניסוח.
  const terms = getEventTerms(form.event_type)

  function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError(strings.errors.imageTypeError)
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      setError(strings.errors.imageSize3MB)
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
    if (terms.hasTwoHosts) {
      if (!form.groom_name.trim() || !form.bride_name.trim()) {
        setError(strings.errors.onboardingHostsMissing(terms.hostsLabel))
        return
      }
    } else if (!form.groom_name.trim()) {
      setError(strings.errors.onboardingHostAMissing(terms.hostAField))
      return
    }
    setBusy(true)
    try {
      const ev = await createMyEvent({
        event_type: form.event_type,
        groom_name: form.groom_name,
        bride_name: terms.hasTwoHosts ? form.bride_name : '',
        venue_name: form.venue_name,
      })
      // עוברים לאירוע החדש מיד, כדי שהעדכון הבא (updateEvent) ידע על איזה אירוע לדבר.
      setEventId(ev.id)
      // מסנכרן את סוג האירוע הפעיל ל-store, כדי ששלב 2 (הוספת מוזמנים,
      // activeEventTerms) יציג מיד את התוויות הנכונות — לא ישאר על הסוג
      // הקודם/ברירת המחדל שנשאר ב-localStorage מסשן קודם.
      setActiveEventType(ev.event_type)

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
      setStep('partner')
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.eventCreateFailed)
    } finally {
      setBusy(false)
    }
  }

  async function sendPartnerInvite(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const invite = await invitePartner(partnerEmail)
      setPartnerSentTo(invite.invited_email)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את ההזמנה')
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
        <div className="onboard-logo">
          <img className="onboard-logo-img" src="/logo.png" alt="VEYA" width={152} height={133} />
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
            <div className="event-type-field">
              <span className="field-label">סוג האירוע</span>
              <div className="event-type-grid" role="radiogroup" aria-label="סוג האירוע">
                {EVENT_TYPE_OPTIONS.map((opt) => (
                  <button
                    key={opt.type}
                    type="button"
                    role="radio"
                    aria-checked={form.event_type === opt.type}
                    className={`event-type-chip ${form.event_type === opt.type ? 'active' : ''}`}
                    onClick={() => setForm({ ...form, event_type: opt.type })}
                  >
                    <span className="event-type-chip-icon" aria-hidden="true">
                      <EventTypeIcon type={opt.type} />
                    </span>
                    <span className="event-type-chip-label">{opt.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="event-fields">
              <input
                placeholder={terms.hostAField}
                value={form.groom_name}
                onChange={(e) => setForm({ ...form, groom_name: e.target.value })}
              />
              {terms.hasTwoHosts && (
                <input
                  placeholder={terms.hostBField}
                  value={form.bride_name}
                  onChange={(e) => setForm({ ...form, bride_name: e.target.value })}
                />
              )}
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
                  onClick={(e) => e.currentTarget.showPicker?.()}
                />
              </label>
              <div className="field-group">
                <span className="field-label">שעת האירוע</span>
                <TimePicker
                  value={form.event_time}
                  onChange={(time) => setForm({ ...form, event_time: time })}
                  ariaLabel="שעת האירוע"
                />
              </div>
            </div>

            <div className="commit-field">
              <span className="field-label">מועד סגירת הרשימה</span>
              <p className="commit-explain">
                כמה ימים לפני האירוע אתם צריכים למסור לאולם מספר סופי? זה היום
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
                  <div className="invite-frame">
                    <div className="invite-frame-mat">
                      <img
                        className="event-image-thumb"
                        src={form.invite_image}
                        alt="תצוגה מקדימה של ההזמנה"
                      />
                    </div>
                    <span className="invite-frame-caption">{terms.inviteLabel}</span>
                  </div>
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
                {busy ? 'רגע…' : 'להוספת מוזמנים →'}
              </button>
            </div>
          </form>
        ) : step === 'partner' ? (
          <div className="onboard-guest-step">
            {partnerSentTo ? (
              <>
                <p className="onboard-guest-count">
                  שלחנו הזמנה ל-<span dir="ltr">{partnerSentTo}</span> ✓
                </p>
                <p className="onboard-subtitle onboard-guest-intro">
                  ברגע שההזמנה תאושר, תנהלו את האירוע יחד — אותם מוזמנים, אותם
                  אישורי הגעה, אותה הושבה.
                </p>
                <div className="onboard-actions">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setStep('guests')}
                  >
                    להמשך
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="onboard-subtitle onboard-guest-intro">
                  VEYA נועדה לעזור לשניכם לנהל את האירוע. הזמינו את בן/בת הזוג
                  כדי שתוכלו לעבוד יחד על אותו אירוע.
                </p>
                <form className="event-edit" onSubmit={sendPartnerInvite}>
                  <label className="field-group">
                    <span className="field-label">האימייל של בן/בת הזוג</span>
                    <input
                      type="email"
                      dir="ltr"
                      value={partnerEmail}
                      onChange={(e) => setPartnerEmail(e.target.value)}
                      placeholder="partner@example.com"
                      required
                    />
                  </label>
                  <div className="onboard-actions">
                    <button type="submit" className="btn-primary" disabled={busy}>
                      {busy ? 'שולח…' : 'שליחת הזמנה'}
                    </button>
                    <button
                      type="button"
                      className="onboard-skip"
                      onClick={() => setStep('guests')}
                    >
                      אעשה זאת מאוחר יותר
                    </button>
                  </div>
                </form>
              </>
            )}
          </div>
        ) : (
          <div className="onboard-guest-step">
            <h2 className="onboard-step-title">הוסיפו את המוזמנים שלכם</h2>
            <p className="onboard-subtitle onboard-guest-intro">
              יש לכם רשימה מוכנה? מייבאים אותה בלחיצה אחת — מוואטסאפ, מאקסל או
              מאנשי הקשר. אפשר גם להוסיף מוזמנים אחד-אחד.
            </p>
            {guestCount > 0 && (
              <p className="onboard-guest-count">הוספתם {guestCount} מוזמנים ✓</p>
            )}

            <div className="onboarding-import-options">
              <button
                type="button"
                className="onboarding-import-btn"
                onClick={() => setShowPaste(true)}
              >
                {t.pasteButton}
              </button>
              <button
                type="button"
                className="onboarding-import-btn"
                onClick={() => fileInput.current?.click()}
              >
                {t.uploadButton}
              </button>
              {contactsSupported && (
                <button
                  type="button"
                  className="onboarding-import-btn"
                  onClick={() => setShowContacts(true)}
                >
                  {t.contactsButton}
                </button>
              )}
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".xlsx,.xlsm,.csv"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) setImportFile(f)
                e.target.value = ''
              }}
            />

            {!showManualForm ? (
              <button
                type="button"
                className="btn-text onboarding-manual"
                onClick={() => setShowManualForm(true)}
              >
                {t.onboardingManualCta}
              </button>
            ) : (
              <AddGuestForm onAdded={() => setGuestCount((c) => c + 1)} onCancel={() => {}} />
            )}

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

      {/* שלושת דיאלוגי הייבוא מוצגים כאן, *מחוץ* ל-.onboard-card בכוונה:
          .onboard-card חלק מרשימת ה-selector שהופכת --cream/--charcoal/--line
          למצב כהה (ראו App.css). הדיאלוגים האלה מיובאים כמו שהם מ-GuestsPage
          ומיועדים לרקע בהיר — קינון אותם בתוך .onboard-card היה גורם להם
          לרשת צבעים כהים בטעות דרך ה-CSS variables, בלי לגעת בקוד שלהם. */}
      {importFile && (
        <ImportDialog
          file={importFile}
          onClose={() => setImportFile(null)}
          onImported={(created) => {
            setImportFile(null)
            setGuestCount((c) => c + created)
          }}
        />
      )}
      {showPaste && (
        <PasteImportDialog
          onClose={() => setShowPaste(false)}
          onImported={(created) => {
            setShowPaste(false)
            setGuestCount((c) => c + created)
          }}
        />
      )}
      {showContacts && (
        <ContactsImportDialog
          onClose={() => setShowContacts(false)}
          onImported={(created) => {
            setShowContacts(false)
            setGuestCount((c) => c + created)
          }}
        />
      )}
    </div>
  )
}
