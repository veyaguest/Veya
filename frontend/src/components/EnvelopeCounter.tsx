import { useEffect, useMemo, useRef, useState } from 'react'
import { createEnvelope, listGuests } from '../api'
import type { EnvelopeInput, Guest, GiftEntry } from '../types'
import { strings } from '../strings/he'

const t = strings.finance

interface Props {
  /** המספר שהמעטפה הבאה תקבל — מגיע מהשרת. */
  startNumber: number
  onSaved: (entry: GiftEntry, nextNumber: number) => void
  onClose: () => void
}

/**
 * מצב ספירת מעטפות — המסך שבו סופרים מאות מעטפות בערב אחד.
 *
 * ## מה המסך הזה **לא** עושה
 *
 * הוא לא שולח את הזוג לחפש מוזמן, לפתוח אותו, להזין סכום ולחזור לרשימה.
 * ערימת מעטפות מגיעה בסדר אקראי, ובקצב הזה גם מסך טוב הופך לעבודה של
 * שעה וחצי. כאן יש **טופס אחד שנשאר פתוח**: סכום, ממי, שמירה — ומיד
 * המעטפה הבאה, באותו מקום, עם הפוקוס כבר בשדה הסכום.
 *
 * ## החיפוש מקומי, ובכוונה
 *
 * רשימת המוזמנים נטענת פעם אחת בפתיחה, והסינון קורה בדפדפן. חיפוש שרץ
 * לשרת בכל הקלדה הוא חיפוש שמגמגם ברשת סלולרית באולם — וזה בדיוק הרגע
 * שבו הוא חייב לעבוד. אירוע של אלף מוזמנים הוא רשימה שהדפדפן מסנן
 * בפחות ממילישנייה.
 *
 * ## המספר הרץ מגיע מהשרת
 *
 * ``next_envelope_number`` חוזר בכל שמירה ולא נספר כאן. זו הדרך היחידה
 * ששני מכשירים שסופרים את אותה ערימה במקביל לא יקבלו את אותו מספר.
 */
export function EnvelopeCounter({ startNumber, onSaved, onClose }: Props) {
  const [number, setNumber] = useState(startNumber)
  const [amount, setAmount] = useState('')
  const [guest, setGuest] = useState<Guest | null>(null)
  const [shared, setShared] = useState<Guest[]>([])
  const [query, setQuery] = useState('')
  const [note, setNote] = useState('')
  const [addingShared, setAddingShared] = useState(false)

  const [guests, setGuests] = useState<Guest[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** אישור קצר על המעטפה האחרונה — כדי שהזוג יראה שהשמירה תפסה בלי
   *  שהמסך יזוז או שיצטרך לעצור ולקרוא הודעה. */
  const [lastSaved, setLastSaved] = useState<string | null>(null)

  const amountRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let alive = true
    // limit גבוה במכוון: המסך הזה צריך את **כל** המוזמנים בזיכרון כדי
    // שהחיפוש יהיה מיידי. זו קריאה אחת בפתיחה, לא בכל הקלדה.
    listGuests(undefined, 2000, 0, 'name')
      .then((page) => alive && setGuests(page.items))
      .catch(() => alive && setError(t.loadError))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    amountRef.current?.focus()
  }, [])

  // ── החיפוש ────────────────────────────────────────────────────────
  // תומך בשם פרטי, שם משפחה, שם מלא וטלפון — בלי לדרוש מהזוג לדעת
  // באיזה שדה הוא מחפש. כל מילה בשאילתה חייבת להימצא איפשהו ברשומה,
  // כך ש"דני כהן" מוצא גם כשהשם נשמר "כהן דני".
  const results = useMemo(() => {
    const q = query.trim()
    if (!q) return []
    const words = q.split(/\s+/).filter(Boolean)
    const chosen = new Set([guest?.id, ...shared.map((g) => g.id)].filter(Boolean))
    return guests
      .filter((g) => {
        if (chosen.has(g.id)) return false
        const haystack = `${g.full_name} ${normalizePhone(g.phone)}`
        return words.every((w) => haystack.includes(normalizePhone(w)) || haystack.includes(w))
      })
      .slice(0, 8)
  }, [query, guests, guest, shared])

  function reset(next: number) {
    setNumber(next)
    setAmount('')
    setGuest(null)
    setShared([])
    setQuery('')
    setNote('')
    setAddingShared(false)
    amountRef.current?.focus()
  }

  function pick(picked: Guest) {
    if (addingShared) {
      setShared((prev) => [...prev, picked])
      setAddingShared(false)
    } else {
      setGuest(picked)
    }
    setQuery('')
  }

  async function save(unknown = false) {
    const agorot = parseInt(amount || '0', 10) * 100
    if (!agorot) {
      amountRef.current?.focus()
      return
    }
    setBusy(true)
    setError(null)
    const input: EnvelopeInput = {
      amount_agorot: agorot,
      // "לא ידוע ממי" הוא מצב מתועד ולא דילוג — הוא נשמר כמעטפה מלאה
      // עם סכום, ואפשר לחזור ולשייך אותה בכל רגע.
      guest_id: unknown ? null : (guest?.id ?? null),
      shared_guest_ids: unknown ? [] : shared.map((g) => g.id),
      note: note.trim() || null,
    }
    try {
      const res = await createEnvelope(input)
      setLastSaved(t.envelopeSaved(res.envelope.envelope_number ?? number, res.envelope.amount_display))
      onSaved(res.envelope, res.next_envelope_number)
      reset(res.next_envelope_number)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setBusy(false)
    }
  }

  const showSearch = addingShared || !guest

  return (
    <div className="fin-counter">
      <header className="fin-counter-head">
        <p className="fin-counter-number">{t.envelopeNumber(number)}</p>
        <button type="button" className="btn-ghost" onClick={onClose}>
          {t.stopCounting}
        </button>
      </header>

      <form
        className="fin-counter-body"
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        {/* הסכום ראשון ובגדול. זה המספר שהזוג קורא מהמעטפה שבידו, וכל
            שאר המסך משרת אותו. */}
        <label className="fin-counter-amount">
          <span className="field-label">{t.envelopeAmountLabel}</span>
          <div className="fin-amount-input">
            <input
              ref={amountRef}
              type="text"
              inputMode="numeric"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ''))}
              onKeyDown={(e) => {
                // Enter בשדה הסכום מעביר לחיפוש ולא שולח: כמעט תמיד
                // נשאר עוד צעד אחד לפני שמירה.
                if (e.key === 'Enter') {
                  e.preventDefault()
                  searchRef.current?.focus()
                }
              }}
              placeholder="0"
              dir="ltr"
              autoComplete="off"
            />
            <span className="fin-amount-currency" aria-hidden="true">
              ₪
            </span>
          </div>
        </label>

        {/* ממי — או "לא ידוע ממי". */}
        <div className="fin-counter-from">
          <span className="field-label">{t.envelopeFromLabel}</span>

          {guest && (
            <div className="fin-picked">
              <GuestChip guest={guest} onRemove={() => setGuest(null)} />
              {shared.map((g) => (
                <GuestChip
                  key={g.id}
                  guest={g}
                  onRemove={() => setShared((prev) => prev.filter((x) => x.id !== g.id))}
                />
              ))}
              {!addingShared && (
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => {
                    setAddingShared(true)
                    // המתנה לרינדור שדה החיפוש לפני מיקוד בו.
                    setTimeout(() => searchRef.current?.focus(), 0)
                  }}
                >
                  {t.sharedAdd}
                </button>
              )}
            </div>
          )}

          {showSearch && (
            <>
              <input
                ref={searchRef}
                type="search"
                className="fin-search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  // Enter עם תוצאה יחידה בוחר אותה. עם כמה תוצאות הוא
                  // לא מנחש — ניחוש כאן משייך כסף למוזמן הלא נכון.
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    if (results.length === 1) pick(results[0])
                  }
                }}
                placeholder={t.envelopeSearchPlaceholder}
                autoComplete="off"
                aria-label={t.envelopeFromLabel}
              />

              {query.trim() && (
                <ul className="fin-results">
                  {results.length === 0 ? (
                    <li className="fin-results-empty">{t.envelopeSearchEmpty}</li>
                  ) : (
                    results.map((g) => (
                      <li key={g.id}>
                        <button type="button" className="fin-result" onClick={() => pick(g)}>
                          <span className="fin-result-name">{g.full_name}</span>
                          {/* כמה אנשים מיוצגים ברשומה — זה מה שמבדיל את
                              "משפחת כהן" מ"דני כהן" ברשימת התוצאות. */}
                          <span className="fin-result-meta">
                            {t.resultPartySize(g.party_size)}
                          </span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
              {!query.trim() && !guest && (
                <p className="fin-hint">{t.envelopeSearchHint}</p>
              )}
            </>
          )}
        </div>

        <label className="field fin-counter-note">
          <span className="field-label">{t.envelopeNote}</span>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
          />
        </label>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <div className="fin-counter-actions">
          <button type="submit" className="btn-primary" disabled={busy || !amount}>
            {busy ? t.envelopeSaving : t.envelopeSave}
          </button>
          {/* מסלול שווה-ערך, לא "ויתור". מעטפה בלי שם היא מעטפה מלאה
              לכל דבר — היא פשוט ממתינה לשיוך. */}
          <button
            type="button"
            className="btn-ghost"
            onClick={() => save(true)}
            disabled={busy || !amount}
          >
            {t.envelopeUnknown}
          </button>
        </div>
        <p className="fin-hint">{t.envelopeUnknownHint}</p>

        {/* ``aria-live`` כדי שקורא מסך יכריז על השמירה — בלי זה הזוג
            שמנווט במקלדת לא יודע שהמעטפה נתפסה. */}
        <p className="fin-saved" role="status" aria-live="polite">
          {lastSaved}
        </p>
      </form>
    </div>
  )
}

function GuestChip({ guest, onRemove }: { guest: Guest; onRemove: () => void }) {
  return (
    <span className="fin-guest-chip">
      {guest.full_name}
      <button type="button" onClick={onRemove} aria-label={t.sharedRemove}>
        ✕
      </button>
    </span>
  )
}

/** משווה טלפונים בלי מקפים/רווחים, כדי ש"050-1234567" יימצא גם כ"0501234567". */
function normalizePhone(value: string): string {
  return value.replace(/[\s-]/g, '')
}
