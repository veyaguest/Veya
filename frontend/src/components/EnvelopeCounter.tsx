import { useEffect, useMemo, useRef, useState } from 'react'
import { createEnvelope, getGiftsByGuest, listGuests } from '../api'
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
 * שעה וחצי. כאן יש **טופס אחד שנשאר פתוח**: ממי, כמה, שמירה — ומיד
 * המעטפה הבאה, באותו מקום, עם הפוקוס כבר בשדה החיפוש.
 *
 * ## למה החיפוש ראשון
 *
 * על המעטפה כתוב שם, לא סכום — הסכום מתגלה רק כשפותחים אותה. הסדר
 * "מי ואז כמה" הוא הסדר שבו הידיים באמת עובדות, והוא גם מה שמאפשר
 * ל-Enter לשרשר: Enter בחיפוש בוחר ומעביר לסכום, Enter בסכום שומר
 * ומחזיר לחיפוש. מעטפה שלמה בלי לגעת בעכבר.
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
  // §13 — נותן שאינו ברשימת המוזמנים. מסלול מקביל לחיפוש, לא במקומו.
  const [external, setExternal] = useState(false)
  const [externalName, setExternalName] = useState('')
  const [externalPhone, setExternalPhone] = useState('')

  const [guests, setGuests] = useState<Guest[]>([])
  const [counted, setCounted] = useState<Map<number, string>>(new Map())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** אישור קצר על המעטפה האחרונה — כדי שהזוג יראה שהשמירה תפסה בלי
   *  שהמסך יזוז או שיצטרך לעצור ולקרוא הודעה. */
  const [lastSaved, setLastSaved] = useState<string | null>(null)

  const amountRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let alive = true
    // **כל** המוזמנים נטענים לזיכרון, בדפים.
    //
    // ``limit`` נחתך בשרת ל-200 (``routers/guests.MAX_PAGE_LIMIT``), ולכן
    // בקשה אחת עם 2000 החזירה בשקט את 200 הראשונים בלבד — ובאירוע של
    // 260 מוזמנים 60 מהם פשוט לא נמצאו בחיפוש. חיפוש שמבטיח "כל
    // המוזמנים" ומחזיר חלק מהם הוא הבטחה שבורה, ובמסך שמשייך כסף היא
    // שולחת מעטפה לערימת "לא מזוהה" בלי סיבה.
    const PAGE = 200
    async function loadAll() {
      const all: Guest[] = []
      for (let offset = 0; ; offset += PAGE) {
        const page = await listGuests(undefined, PAGE, offset, 'name')
        all.push(...page.items)
        if (all.length >= page.total || page.items.length === 0) break
      }
      return all
    }
    loadAll()
      .then((items) => alive && setGuests(items))
      .catch(() => alive && setError(t.loadError))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  // מי שכבר נספרה לו מתנה — כדי שתוצאת החיפוש תגיד זאת **לפני** הבחירה.
  // זה מה שמונע רישום כפול של אותה מעטפה בשתי ידיים שסופרות במקביל.
  useEffect(() => {
    let alive = true
    getGiftsByGuest()
      .then((rows) => {
        if (!alive) return
        setCounted(
          new Map(
            rows
              .filter((r) => r.status !== 'not_counted')
              .map((r) => [r.guest_id, r.total_display]),
          ),
        )
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
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
    setExternal(false)
    setExternalName('')
    setExternalPhone('')
    searchRef.current?.focus()
  }

  function pick(picked: Guest) {
    if (addingShared) {
      setShared((prev) => [...prev, picked])
      setAddingShared(false)
    } else {
      setGuest(picked)
      // נבחר מוזמן ⇒ הדבר היחיד שנשאר הוא המספר.
      setTimeout(() => amountRef.current?.focus(), 0)
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
      guest_id: unknown || external ? null : (guest?.id ?? null),
      shared_guest_ids: unknown || external ? [] : shared.map((g) => g.id),
      // נותן חיצוני — שם במקום שיוך. לא נוצר מוזמן חדש.
      external_name: !unknown && external ? externalName.trim() : '',
      external_phone: !unknown && external ? externalPhone.trim() : '',
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

  const showSearch = !external && (addingShared || !guest)
  // שמירה אפשרית רק כשיש ממי — או "לא ידוע ממי", שהוא מסלול משלו.
  const externalReady = !external || externalName.trim().length > 0

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
                  className="btn-link"
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
                  // Enter עם תוצאה יחידה בוחר אותה ועובר לסכום. עם כמה
                  // תוצאות הוא לא מנחש — ניחוש כאן משייך כסף למוזמן הלא
                  // נכון. בשדה ריק הוא פשוט ממשיך הלאה, כדי שמעטפה בלי
                  // שם לא תדרוש עכבר.
                  if (e.key !== 'Enter') return
                  e.preventDefault()
                  if (results.length === 1) pick(results[0])
                  else if (!query.trim()) amountRef.current?.focus()
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
                          {/* כמה אנשים מיוצגים ברשומה (מבדיל את "משפחת
                              כהן" מ"דני כהן"), ולצידו סטטוס ההגעה — כדי
                              שהזוג יראה שבחר את האדם הנכון.

                              הסטטוס **מוצג ולא מסנן**: החיפוש רץ על כל
                              המוזמנים, כי מי שביטל הגעה או לא ענה יכול
                              בהחלט לשלוח מתנה. */}
                          <span className="fin-result-meta">
                            {t.resultPartySize(g.party_size)}
                            <span className={`fin-result-rsvp rsvp-${g.rsvp_status}`}>
                              {t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status}
                            </span>
                            {/* כבר נספרה לו מתנה — נאמר **לפני** הבחירה
                                ולא אחריה. זה מה שמונע רישום כפול של אותה
                                מעטפה כששתי ידיים סופרות במקביל. ואין כאן
                                חסימה: מוזמן בהחלט יכול לתת פעמיים. */}
                            {counted.has(g.id) && (
                              <span className="fin-result-counted">
                                {t.alreadyCounted(counted.get(g.id) ?? '')}
                              </span>
                            )}
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

              {/* §13 — הדלת למי שאינו ברשימה. מסלול מקביל לחיפוש ולא
                  במקומו: רוב המעטפות הן ממוזמנים, וזו האפשרות השנייה. */}
              {!addingShared && (
                <button
                  type="button"
                  className="btn-link fin-external-open"
                  onClick={() => {
                    setExternal(true)
                    setQuery('')
                    setExternalName(query.trim())
                  }}
                >
                  {t.externalAdd}
                </button>
              )}
            </>
          )}

          {/* נותן שאינו ברשימת המוזמנים — שם, וטלפון אם יש. */}
          {external && (
            <div className="fin-external">
              <p className="fin-external-title">{t.externalTitle}</p>
              <div className="fin-row">
                <label className="field">
                  <span className="field-label">{t.externalNameLabel}</span>
                  <input
                    type="text"
                    value={externalName}
                    onChange={(e) => setExternalName(e.target.value)}
                    placeholder={t.externalNamePlaceholder}
                    maxLength={120}
                    autoFocus
                  />
                </label>
                <label className="field">
                  <span className="field-label">
                    {t.externalPhoneLabel}
                    <span className="fin-optional"> · {t.externalPhoneOptional}</span>
                  </span>
                  <input
                    type="tel"
                    value={externalPhone}
                    onChange={(e) => setExternalPhone(e.target.value)}
                    maxLength={40}
                    dir="ltr"
                  />
                </label>
              </div>
              <p className="fin-hint">{t.externalHint}</p>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setExternal(false)
                  setExternalName('')
                  setExternalPhone('')
                }}
              >
                {t.externalBack}
              </button>
            </div>
          )}
        </div>

        {/* הסכום — הצעד השני, אחרי שידוע ממי. גדול, כי זה המספר
            היחיד שמקלידים כאן. */}
        <label className="fin-counter-amount">
          <span className="field-label">{t.envelopeAmountLabel}</span>
          <div className="fin-amount-input">
            <input
              ref={amountRef}
              type="text"
              inputMode="numeric"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ''))}
              placeholder="0"
              dir="ltr"
              autoComplete="off"
            />
            <span className="fin-amount-currency" aria-hidden="true">
              ₪
            </span>
          </div>
        </label>

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
          <button
            type="submit"
            className="btn-primary"
            disabled={busy || !amount || !externalReady}
          >
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
