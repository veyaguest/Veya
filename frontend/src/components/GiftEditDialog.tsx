import { useEffect, useMemo, useRef, useState } from 'react'
import { useBackToClose } from '../lib/backToClose'
import type { EnvelopeInput, GiftEntry, Guest } from '../types'
import { strings } from '../strings/he'
import { ConfirmDialog } from './ConfirmDialog'
import { loadAllGuests, matchGuests } from './EnvelopeCounter'

const t = strings.finance
const g = t.giftsView

interface Props {
  /** מעטפה בלבד — מתנה באשראי מגיעה מנותן המתנה ולא נערכת כאן. */
  entry: GiftEntry
  busy?: boolean
  error?: string | null
  onSave: (input: EnvelopeInput) => void
  onDelete: () => void
  onClose: () => void
}

/**
 * עריכת מתנה (מעטפה) — **אותן שאלות כמו בהוספה: ממי? כמה?**, והערה.
 *
 * עד 2026-09-30 לא הייתה עריכה בכלל: סכום שגוי או מעטפה "לא מזוהה" אפשר
 * היה רק למחוק ולהזין מחדש — למרות שהמסך הבטיח "תמיד אפשר לחזור ולשייך
 * אותה". השרת תמך בזה (``PUT /finance/envelopes/{id}``); חסר רק המסך.
 *
 * **השותפים למתנה נשמרים.** העריכה שולחת את השורה כולה, ולכן היא מחזירה
 * את ``shared_guest_ids`` כפי שהגיעו — אחרת תיקון סכום היה מוחק אותם בשקט.
 *
 * תיקון סכום או מחיקה אחרי "סיימנו לספור" מחזירים את המאזן ל"עד עכשיו"
 * (בשרת) — הטופס עצמו לא צריך לדעת את זה.
 */
export function GiftEditDialog({ entry, busy, error, onSave, onDelete, onClose }: Props) {
  const [amount, setAmount] = useState(
    entry.amount_agorot ? String(Math.trunc(entry.amount_agorot / 100)) : '',
  )
  const [note, setNote] = useState(entry.note ?? '')
  // ממי: ``undefined`` = לא שונה (נשאר מה שהיה, כולל נותן חיצוני).
  const [guest, setGuest] = useState<Guest | null | undefined>(undefined)
  const [changingFrom, setChangingFrom] = useState(false)
  const [query, setQuery] = useState('')
  const [guests, setGuests] = useState<Guest[] | null>(null)
  const [tried, setTried] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const amountRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useBackToClose(true, onClose)

  // המוזמנים נטענים רק כשבאמת משנים "ממי" — רוב העריכות הן תיקון סכום.
  useEffect(() => {
    if (!changingFrom || guests !== null) return
    let alive = true
    loadAllGuests()
      .then((items) => alive && setGuests(items))
      .catch(() => alive && setGuests([]))
    return () => {
      alive = false
    }
  }, [changingFrom, guests])

  useEffect(() => {
    if (changingFrom) searchRef.current?.focus()
  }, [changingFrom])

  const results = useMemo(() => matchGuests(guests ?? [], query), [guests, query])

  const agorot = parseInt(amount || '0', 10) * 100
  const amountError = agorot > 0 ? null : g.amountError

  const fromLabel =
    guest === undefined
      ? entry.guest_name || g.unknownFrom
      : guest === null
        ? g.unknownFrom
        : guest.full_name

  function submit() {
    setTried(true)
    if (amountError) {
      amountRef.current?.focus()
      return
    }
    const keepFrom = guest === undefined
    onSave({
      amount_agorot: agorot,
      guest_id: keepFrom ? entry.guest_id : (guest?.id ?? null),
      // השותפים נשארים כפי שהיו; השרת מסנן את הנותן הראשי מתוכם.
      shared_guest_ids: entry.shared_guest_ids ?? [],
      // נותן חיצוני נשאר חיצוני — אלא אם שויך עכשיו למוזמן או ל"לא ידוע".
      external_name: keepFrom && entry.is_external ? entry.guest_name : '',
      external_phone: keepFrom && entry.is_external ? entry.external_phone : '',
      note: note.trim() || null,
    })
  }

  return (
    <>
      <div className="overlay fin-editor-overlay" onClick={() => !busy && onClose()}>
        <div
          className="dialog fin-editor"
          role="dialog"
          aria-modal="true"
          aria-labelledby="fin-gift-edit-title"
          onClick={(ev) => ev.stopPropagation()}
        >
          <div className="dialog-head">
            <h2 id="fin-gift-edit-title">
              {g.editTitle}
              {entry.envelope_number != null && (
                <span className="fin-step-sub"> · {t.envelopeNumber(entry.envelope_number)}</span>
              )}
            </h2>
            <button type="button" className="x" onClick={onClose} aria-label={strings.common.cancel}>
              ✕
            </button>
          </div>

          <form
            className="dialog-body fin-form"
            noValidate
            onSubmit={(ev) => {
              ev.preventDefault()
              submit()
            }}
          >
            {/* ── ממי? ── */}
            <fieldset className="fin-step">
              <legend className="fin-step-title">{g.fromLabel}</legend>
              {!changingFrom ? (
                <div className="fin-chosen">
                  <span className="fin-chosen-name">{fromLabel}</span>
                  {entry.shared_names.length > 0 && guest === undefined && (
                    <span className="fin-chosen-group">{t.sharedWith(entry.shared_names)}</span>
                  )}
                  <span className="fin-chosen-actions">
                    <button type="button" className="btn-link" onClick={() => setChangingFrom(true)}>
                      {g.change}
                    </button>
                  </span>
                </div>
              ) : (
                <div className="fin-choose">
                  <input
                    ref={searchRef}
                    type="search"
                    className="fin-search"
                    value={query}
                    onChange={(ev) => setQuery(ev.target.value)}
                    placeholder={t.envelopeSearchPlaceholder}
                    aria-label={g.fromLabel}
                    autoComplete="off"
                  />
                  {query.trim() && (
                    <ul className="fin-results">
                      {guests === null ? (
                        <li className="fin-results-empty">{strings.common.loading}</li>
                      ) : results.length === 0 ? (
                        <li className="fin-results-empty">{t.envelopeSearchEmpty}</li>
                      ) : (
                        results.map((r) => (
                          <li key={r.id}>
                            <button
                              type="button"
                              className="fin-result"
                              onClick={() => {
                                setGuest(r)
                                setChangingFrom(false)
                                setQuery('')
                              }}
                            >
                              <span className="fin-result-name">{r.full_name}</span>
                            </button>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                  <button
                    type="button"
                    className="btn-link fin-catalog-more"
                    onClick={() => {
                      setGuest(null)
                      setChangingFrom(false)
                      setQuery('')
                    }}
                  >
                    {g.unknownFrom}
                  </button>
                </div>
              )}
            </fieldset>

            {/* ── כמה? ── */}
            <div className="fin-step">
              <label className="fin-step-title" htmlFor="fin-gift-amount">
                {g.amountLabel}
              </label>
              <div className={`fin-money ${tried && amountError ? 'is-invalid' : ''}`}>
                <input
                  id="fin-gift-amount"
                  ref={amountRef}
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  value={amount ? Number(amount).toLocaleString('he-IL') : ''}
                  onChange={(ev) => setAmount(ev.target.value.replace(/[^\d]/g, ''))}
                  placeholder="0"
                  dir="ltr"
                  aria-invalid={tried && !!amountError}
                  aria-describedby={tried && amountError ? 'fin-gift-amount-error' : undefined}
                />
                <span className="fin-money-cur" aria-hidden="true">₪</span>
              </div>
              {tried && amountError && (
                <span id="fin-gift-amount-error" className="fin-field-error">{amountError}</span>
              )}
            </div>

            <label className="field">
              <span className="field-label">{g.noteLabel}</span>
              <input
                type="text"
                value={note}
                onChange={(ev) => setNote(ev.target.value)}
                maxLength={500}
              />
            </label>

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            <div className="dialog-foot fin-editor-foot">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? strings.common.saving : g.save}
              </button>
            </div>

            {/* מחיקה — קיימת, אבל שקטה: קישור מתחת לשמירה. */}
            <button
              type="button"
              className="btn-link fin-delete-link"
              onClick={() => setConfirmDelete(true)}
              disabled={busy}
            >
              {g.deleteLink}
            </button>
          </form>
        </div>
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title={t.deleteEnvelopeTitle}
          message={t.deleteEnvelopeBody(entry.envelope_number ?? 0, entry.amount_display)}
          confirmLabel={strings.common.delete}
          danger
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  )
}
