import { useState } from 'react'
import { createPayment, deletePayment, updatePayment } from '../api'
import type { Expense, Payment, PaymentInput, PaymentKind } from '../types'
import { strings } from '../strings/he'

const t = strings.finance

interface Props {
  expense: Expense
  /** נקרא אחרי כל שינוי, עם שורת ההוצאה **המחושבת מחדש מהשרת**. */
  onChanged: (expense: Expense) => void
}

/**
 * יומן התשלומים של שורת הוצאה אחת.
 *
 * ## למה יומן ולא מספר
 *
 * זוג משלם לאולם בשלוש פעימות, לצלם במקדמה ובתשלום, ולדיג'יי במזומן
 * בערב עצמו. מספר אחד ("שולם 5,000") לא עונה על "מתי שילמנו לצלם
 * ובכמה?", ובדיוק את השאלה הזו שואלים כשמגיעה חשבונית.
 *
 * ## שלושת המספרים בראש, ובסדר הזה
 *
 * עלות כוללת ← שולם עד עכשיו ← נשאר לשלם. **כולם מגיעים מהשרת**
 * (``paid_display`` / ``remaining_display``): חיבור התשלומים בדפדפן היה
 * מסלול חישוב שני שיכול לסטות מהסיכום שבכותרת המסך, ובמסך כספי זו
 * ההגדרה של באג שמתגלה מול חשבונית.
 *
 * ## כל פעולה מחזירה את השורה כולה
 *
 * הוספה, עריכה ומחיקה מחזירות ``Expense`` מלא ומעודכן. אין כאן עדכון
 * אופטימי ואין חישוב מקומי — התשובה של השרת **היא** המצב החדש.
 */
export function PaymentsPanel({ expense, onChanged }: Props) {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Payment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<Expense>) {
    setBusy(true)
    setError(null)
    try {
      onChanged(await action())
      setAdding(false)
      setEditing(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setBusy(false)
    }
  }

  const settled = expense.remaining_agorot === 0 && expense.paid_agorot > 0

  return (
    <section className="fin-payments">
      <div className="fin-payments-head">
        <Figure label={t.totalCostLabel} value={expense.total_display} />
        <Figure label={t.summaryPaidLabel} value={expense.paid_display} />
        <Figure
          label={t.summaryUnpaidLabel}
          value={expense.remaining_display}
          // הודגש רק כשבאמת נשאר משהו. "0 ₪ נשאר לשלם" בזהב היה מושך
          // את העין בדיוק למקום שאין בו מה לעשות.
          tone={settled ? 'done' : 'due'}
        />
      </div>

      {/* נרשמו תשלומים מעל עלות ההוצאה. מוסבר במקום להשאיר את הזוג מול
          שני מספרים שלא מסתדרים — היומן מציג 14,500 והסיכום 12,000. */}
      {expense.payments_total_agorot > expense.paid_agorot && (
        <p className="fin-hint fin-overpaid">
          {t.overpaidNote(expense.payments_total_display, expense.paid_display)}
        </p>
      )}

      {expense.payments.length === 0 ? (
        <p className="fin-hint">{t.paymentsEmpty}</p>
      ) : (
        <ul className="fin-payment-list">
          {expense.payments.map((p) => (
            <li key={p.id} className="fin-payment">
              <span className="fin-payment-kind">
                {p.kind === 'advance' ? t.paymentAdvance : t.paymentRegular}
              </span>
              <span className="fin-payment-amount">{p.amount_display}</span>
              {/* למי ומתי — שניהם אופציונליים, ושורה בלעדיהם היא עדיין
                  תשלום תקין. אין כאן מקף שממלא חלל ריק. */}
              <span className="fin-payment-meta">
                {[p.payee, p.paid_on_display].filter(Boolean).join(' · ')}
              </span>
              {p.note && <span className="fin-payment-note">{p.note}</span>}
              <span className="fin-payment-actions">
                <button
                  type="button"
                  className="btn-link"
                  onClick={() => setEditing(p)}
                  disabled={busy}
                >
                  {strings.common.edit}
                </button>
                <button
                  type="button"
                  className="btn-link fin-delete"
                  onClick={() => run(() => deletePayment(p.id))}
                  disabled={busy}
                >
                  {strings.common.delete}
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {adding || editing ? (
        <PaymentForm
          payment={editing}
          defaultPayee={expense.vendor ?? ''}
          busy={busy}
          onSave={(input) =>
            run(() =>
              editing
                ? updatePayment(editing.id, input)
                : createPayment(expense.id, input),
            )
          }
          onCancel={() => {
            setAdding(false)
            setEditing(null)
            setError(null)
          }}
        />
      ) : (
        <button
          type="button"
          className="btn-ghost btn-sm fin-payment-add"
          onClick={() => setAdding(true)}
        >
          {t.addPayment}
        </button>
      )}
    </section>
  )
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'due' | 'done'
}) {
  return (
    <div className={`fin-figure ${tone ? `fin-figure-${tone}` : ''}`}>
      <span className="fin-figure-label">{label}</span>
      <span className="fin-figure-value">{value}</span>
    </div>
  )
}

/**
 * טופס תשלום אחד.
 *
 * שדה אחד חובה — הסכום. "למי" מתמלא מהספק של השורה, "מתי" מהיום, ושניהם
 * ניתנים לשינוי. זוג שרושם תשלום שקרה עכשיו לא צריך להקליד כלום מעבר
 * למספר.
 */
function PaymentForm({
  payment,
  defaultPayee,
  busy,
  onSave,
  onCancel,
}: {
  payment: Payment | null
  defaultPayee: string
  busy: boolean
  onSave: (input: PaymentInput) => void
  onCancel: () => void
}) {
  const [amount, setAmount] = useState(
    payment ? String(Math.trunc(payment.amount_agorot / 100)) : '',
  )
  const [payee, setPayee] = useState(payment?.payee ?? defaultPayee)
  const [paidOn, setPaidOn] = useState(payment?.paid_on || today())
  const [kind, setKind] = useState<PaymentKind>(payment?.kind ?? 'payment')
  const [note, setNote] = useState(payment?.note ?? '')

  const shekels = parseInt(amount || '0', 10)

  return (
    <form
      className="fin-payment-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (!shekels) return
        onSave({
          amount_agorot: shekels * 100,
          payee: payee.trim(),
          paid_on: paidOn,
          kind,
          note: note.trim() || null,
        })
      }}
    >
      <div className="fin-row">
        <label className="field">
          <span className="field-label">{t.paymentAmountLabel}</span>
          <input
            type="text"
            inputMode="numeric"
            value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ''))}
            placeholder="0"
            dir="ltr"
            autoFocus
          />
        </label>
        <label className="field">
          <span className="field-label">{t.paymentDateLabel}</span>
          <input
            type="date"
            value={paidOn}
            onChange={(e) => setPaidOn(e.target.value)}
            dir="ltr"
          />
        </label>
      </div>

      <label className="field">
        <span className="field-label">{t.paymentPayeeLabel}</span>
        <input
          type="text"
          value={payee}
          onChange={(e) => setPayee(e.target.value)}
          placeholder={t.paymentPayeePlaceholder}
          maxLength={120}
        />
      </label>

      {/* מקדמה מול תשלום — שני צ'יפים, לא רשימה נפתחת. שתי אפשרויות
          בבורר נפתח הן שתי לחיצות במקום אחת. */}
      <div className="fin-payment-kinds">
        {(
          [
            ['advance', t.paymentAdvance],
            ['payment', t.paymentRegular],
          ] as [PaymentKind, string][]
        ).map(([value, text]) => (
          <label
            key={value}
            className={`fin-payment-option ${kind === value ? 'active' : ''}`}
          >
            <input
              type="radio"
              name={`payment-kind-${payment?.id ?? 'new'}`}
              value={value}
              checked={kind === value}
              onChange={() => setKind(value)}
            />
            <span>{text}</span>
          </label>
        ))}
      </div>

      <label className="field">
        <span className="field-label">{t.noteLabel}</span>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={t.paymentNotePlaceholder}
          maxLength={500}
        />
      </label>

      <div className="fin-payment-form-actions">
        <button type="submit" className="btn-primary btn-sm" disabled={busy || !shekels}>
          {busy ? strings.common.saving : t.savePayment}
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={onCancel} disabled={busy}>
          {strings.common.cancel}
        </button>
      </div>
    </form>
  )
}

/** היום, כ-``YYYY-MM-DD`` בשעון המקומי (לא UTC — תשלום נרשם ביום שבו
 *  הזוג נמצא, ו-``toISOString`` היה מקדים אותו בלילה). */
function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
