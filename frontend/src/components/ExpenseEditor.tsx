import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  CalcMethod,
  Expense,
  ExpenseCatalogItem,
  ExpenseCategory,
  ExpenseInput,
} from '../types'
import { strings } from '../strings/he'
import { ConfirmDialog } from './ConfirmDialog'

const t = strings.finance

interface Props {
  categories: ExpenseCategory[]
  /** ``null`` = הוספה חדשה. אחרת עריכה של שורה קיימת. */
  expense: Expense | null
  busy?: boolean
  error?: string | null
  onSave: (input: ExpenseInput) => void
  onDelete?: () => void
  onCancel: () => void
}

/**
 * הוספה ועריכה של שורת הוצאה.
 *
 * ## שני שלבים בהוספה, שלב אחד בעריכה
 *
 * מסך ריק שמבקש מזוג להמציא את רשימת ההוצאות של אירוע הוא מסך שנשאר
 * ריק. לכן ההוספה מתחילה בבחירה מתוך הקטלוג (קטגוריה ← פריט), וממנה
 * נגזרים שם ההוצאה ושיטת החישוב **כברירת מחדל שאפשר לשנות**. הקטלוג
 * מציע; הוא לא כולא. "משהו אחר" פותח שורה חופשית לגמרי בכל קטגוריה.
 *
 * בעריכה אין שלב בחירה — הזוג כבר יודע במה מדובר, והוא בא לשנות מספר.
 *
 * ## הכסף נקלט בשקלים ונשלח באגורות
 *
 * ההמרה קורית **פעם אחת**, כאן, ב-``toAgorot``. אין מספר עשרוני שנוסע
 * ברשת ואין חישוב כספי במסך: אותו כלל שכבר נאכף במתנות
 * (``app/gift.py``) — הדפדפן מצייר כסף, השרת מחשב אותו.
 *
 * ## שדות ההתחייבות מופיעים רק כשיש להם משמעות
 *
 * "כמות שהתחייבתם עליה" נגזרת מהחוזה מול האולם, והיא רלוונטית רק
 * לשורה שמחושבת לפי מספר המגיעים. הצגתה על שורה קבועה הייתה מזמינה
 * את הזוג למלא שדה שלא ישפיע על כלום.
 */
export function ExpenseEditor({
  categories,
  expense,
  busy,
  error,
  onSave,
  onDelete,
  onCancel,
}: Props) {
  const editing = expense !== null

  const [categoryKey, setCategoryKey] = useState(expense?.category ?? '')
  const [itemKey, setItemKey] = useState(expense?.item_key ?? '')
  const [label, setLabel] = useState(expense?.label ?? '')
  const [method, setMethod] = useState<CalcMethod>(expense?.calc_method ?? 'fixed')
  const [amount, setAmount] = useState(toShekelInput(expense?.amount_agorot))
  const [quantity, setQuantity] = useState(expense?.quantity?.toString() ?? '')
  const [committed, setCommitted] = useState(expense?.committed_quantity?.toString() ?? '')
  const [minTotal, setMinTotal] = useState(toShekelInput(expense?.min_total_agorot ?? null))
  const [note, setNote] = useState(expense?.note ?? '')
  const [vendor, setVendor] = useState(expense?.vendor ?? '')
  // ברירת המחדל היא הערכה: תקציב נבנה מהערכות, וסימון הכול כ"סוכם"
  // מלכתחילה מרוקן את ההבחנה מתוכן.
  const [isEstimated, setIsEstimated] = useState(expense?.is_estimated ?? true)
  const [isPaid, setIsPaid] = useState(expense?.is_paid ?? false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // בעריכה מדלגים על שלב הבחירה. בהוספה הוא השלב הראשון, וממנו נגזרות
  // ברירות המחדל.
  const [picking, setPicking] = useState(!editing)

  const amountRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    // אחרי בחירת פריט מהקטלוג הדבר היחיד שנשאר הוא המספר — ולכן הפוקוס
    // קופץ ישר אליו. זה ההבדל בין טופס שממלאים לטופס שעוברים דרכו.
    if (!picking) amountRef.current?.focus()
  }, [picking])

  const category = useMemo(
    () => categories.find((c) => c.key === categoryKey) ?? null,
    [categories, categoryKey],
  )

  const supportsCommitment = method === 'per_attendee'
  const catalogItem = category?.items.find((i) => i.key === itemKey) ?? null

  function pickItem(cat: ExpenseCategory, item: ExpenseCatalogItem | null) {
    setCategoryKey(cat.key)
    setItemKey(item?.key ?? '')
    setLabel(item?.label ?? '')
    // ברירת מחדל חכמה, לא כלל: הזוג רשאי לשנות את השיטה מיד אחר כך.
    setMethod(item?.calc_method ?? 'fixed')
    // כמות פתיחה מהתבנית (2 אלבומי הורים, 10% טיפים) — כדי שהשדה לא
    // ייפתח ריק כשיש ערך שכמעט תמיד נכון.
    setQuantity(item?.default_quantity != null ? String(item.default_quantity) : '')
    setPicking(false)
  }

  function submit() {
    const trimmed = label.trim()
    if (!trimmed) return
    onSave({
      category: categoryKey || 'other',
      item_key: itemKey,
      label: trimmed,
      calc_method: method,
      amount_agorot: toAgorot(amount),
      // ``quantity`` משרת שתי שיטות: יחידות ב-per_unit, ואחוזים שלמים
      // ב-percent. בשאר השיטות הוא נמחק, כדי שערך רדום לא יחזור לחיים
      // בעריכה הבאה.
      quantity:
        method === 'per_unit' || method === 'percent' ? toCount(quantity) : null,
      committed_quantity: supportsCommitment ? toCount(committed) || null : null,
      min_total_agorot: toAgorot(minTotal) || null,
      note: note.trim() || null,
      vendor: vendor.trim(),
      is_estimated: isEstimated,
      is_paid: isPaid,
    })
  }

  // ── שלב הבחירה ────────────────────────────────────────────────────
  if (picking) {
    return (
      <div className="overlay" onClick={onCancel}>
        <div className="dialog fin-editor" onClick={(e) => e.stopPropagation()}>
          <div className="dialog-head">
            <h2>{t.addExpense}</h2>
            <button className="x" onClick={onCancel} aria-label={strings.common.cancel}>
              ✕
            </button>
          </div>

          <div className="dialog-body fin-catalog">
            {categories.map((cat) => (
              <section key={cat.key} className="fin-catalog-group">
                <h3 className="fin-catalog-title">{cat.label}</h3>
                <div className="fin-catalog-items">
                  {/* ברירות המחדל של סוג האירוע קודם, ומודגשות: הקטלוג
                      עשיר (עשרות פריטים), ובלי הסדר הזה הזוג היה סורק
                      רשימה ארוכה כדי למצוא את מה שרוב האירועים כוללים. */}
                  {[...cat.items]
                    .sort((a, b) => Number(b.is_default) - Number(a.is_default))
                    .map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`fin-chip ${item.is_default ? 'fin-chip-suggested' : ''}`}
                      onClick={() => pickItem(cat, item)}
                    >
                      {item.label}
                    </button>
                  ))}
                  {/* קיים בכל קטגוריה ולא רק ב"הוצאות נוספות": הזוג יודע
                      לאיזו קטגוריה ההוצאה שלו שייכת גם כשהיא לא ברשימה. */}
                  <button
                    type="button"
                    className="fin-chip fin-chip-custom"
                    onClick={() => pickItem(cat, null)}
                  >
                    {t.customItem}
                  </button>
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // ── שלב הפרטים ────────────────────────────────────────────────────
  return (
    <>
      <div className="overlay" onClick={onCancel}>
        <div className="dialog fin-editor" onClick={(e) => e.stopPropagation()}>
          <div className="dialog-head">
            <h2>{editing ? t.editExpense : t.addExpense}</h2>
            <button className="x" onClick={onCancel} aria-label={strings.common.cancel}>
              ✕
            </button>
          </div>

          <form
            className="dialog-body fin-form"
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            <label className="field">
              <span className="field-label">{t.expenseNameLabel}</span>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={t.expenseNamePlaceholder}
                maxLength={120}
                required
              />
            </label>

            <fieldset className="fin-method">
              <legend className="field-label">{t.calcMethodLabel}</legend>
              <div className="fin-method-options">
                {(
                  ['fixed', 'per_attendee', 'per_guest', 'per_unit', 'percent'] as CalcMethod[]
                ).map(
                  (m) => (
                    <label
                      key={m}
                      className={`fin-method-option ${method === m ? 'active' : ''}`}
                    >
                      <input
                        type="radio"
                        name="calc-method"
                        value={m}
                        checked={method === m}
                        onChange={() => setMethod(m)}
                      />
                      <span className="fin-method-name">{t.calcMethods[m]}</span>
                      <span className="fin-method-hint">{t.calcMethodHints[m]}</span>
                    </label>
                  ),
                )}
              </div>
            </fieldset>

            <div className="fin-row">
              {/* שורת אחוז אינה נושאת מחיר — הסכום שלה נגזר משאר
                  ההוצאות. שדה מחיר כאן היה שדה שאין לו שום השפעה. */}
              <label className="field" hidden={method === 'percent'}>
                <span className="field-label">
                  {method === 'fixed'
                    ? t.amountLabel
                    : method === 'per_unit'
                      ? t.unitPriceLabel
                      : t.perPersonPriceLabel}
                </span>
                {/* ``inputMode="numeric"`` פותח מקלדת ספרות בטלפון. זה
                    ההבדל בין להקליד 12 סכומים ברצף לבין להילחם במקלדת. */}
                <input
                  ref={amountRef}
                  type="text"
                  inputMode="numeric"
                  value={amount}
                  onChange={(e) => setAmount(digitsOnly(e.target.value))}
                  placeholder="0"
                  dir="ltr"
                />
              </label>

              {(method === 'per_unit' || method === 'percent') && (
                <label className="field">
                  <span className="field-label">
                    {method === 'percent' ? t.percentLabel : t.quantityLabel}
                  </span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={quantity}
                    onChange={(e) => setQuantity(digitsOnly(e.target.value))}
                    placeholder={method === 'percent' ? '10' : '1'}
                    dir="ltr"
                  />
                </label>
              )}
            </div>

            {/* ההתחייבות מוצגת רק כשהיא משנה משהו — ראו הסבר בראש הקובץ.
                מודגשת ויזואלית כי זה הנתון שקובע כמה באמת משלמים. */}
            {supportsCommitment && (
              <section className="fin-commitment-fields">
                <h3 className="fin-subtitle">{t.commitmentSectionTitle}</h3>
                <p className="fin-hint">{t.commitmentHint}</p>
                <div className="fin-row">
                  <label className="field">
                    <span className="field-label">{t.committedQuantityLabel}</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={committed}
                      onChange={(e) => setCommitted(digitsOnly(e.target.value))}
                      placeholder={t.committedQuantityPlaceholder}
                      dir="ltr"
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">{t.minTotalLabel}</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={minTotal}
                      onChange={(e) => setMinTotal(digitsOnly(e.target.value))}
                      placeholder="0"
                      dir="ltr"
                    />
                    <span className="field-hint">{t.minTotalHint}</span>
                  </label>
                </div>
              </section>
            )}

            <label className="field">
              <span className="field-label">{t.vendorLabel}</span>
              <input
                type="text"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                placeholder={t.vendorPlaceholder}
                maxLength={120}
              />
            </label>

            {/* שני מתגים נפרדים ובכוונה לא מקושרים: אפשר לשלם מקדמה על
                סכום שעדיין לא סופי, ואפשר לסכם מחיר ולא לשלם עדיין. */}
            <div className="fin-toggles">
              <button
                type="button"
                className={`fin-toggle ${!isEstimated ? 'on' : ''}`}
                aria-pressed={!isEstimated}
                onClick={() => setIsEstimated((v) => !v)}
              >
                {isEstimated ? t.estimatedLabel : t.agreedLabel}
              </button>
              <button
                type="button"
                className={`fin-toggle ${isPaid ? 'on' : ''}`}
                aria-pressed={isPaid}
                onClick={() => setIsPaid((v) => !v)}
              >
                {isPaid ? t.paidLabel : t.unpaidLabel}
              </button>
            </div>
            <p className="fin-hint">{t.estimatedHint}</p>

            <label className="field">
              <span className="field-label">{t.noteLabel}</span>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t.notePlaceholder}
                maxLength={500}
              />
            </label>

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            <div className="dialog-foot">
              <button type="submit" className="btn-primary" disabled={busy || !label.trim()}>
                {busy ? strings.common.saving : strings.common.save}
              </button>
              <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
                {strings.common.cancel}
              </button>
              {editing && onDelete && (
                <button
                  type="button"
                  className="btn-ghost fin-delete"
                  onClick={() => setConfirmDelete(true)}
                  disabled={busy}
                >
                  {strings.common.delete}
                </button>
              )}
            </div>

            {/* מוצג רק אחרי בחירה מהקטלוג, כדי שהזוג יראה מאיפה השורה
                הגיעה — ויוכל לחזור ולבחור אחרת בלי לסגור הכול. */}
            {!editing && (
              <button type="button" className="link-btn" onClick={() => setPicking(true)}>
                {catalogItem ? `${category?.label} · ${catalogItem.label}` : category?.label}
              </button>
            )}
          </form>
        </div>
      </div>

      {confirmDelete && onDelete && (
        <ConfirmDialog
          title={t.deleteExpenseTitle}
          message={t.deleteExpenseBody(expense?.label ?? '')}
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

// ── המרות ────────────────────────────────────────────────────────────
//
// **נקודת ההמרה היחידה בין שקלים לאגורות בכל המסך.** הזוג מקליד שקלים
// שלמים; השרת מקבל ומחזיר אגורות. כל חישוב כספי קורה בשרת, ולכן אין
// כאן שום פעולת כסף מעבר לכפל/חילוק ב-100.

function digitsOnly(value: string): string {
  return value.replace(/[^\d]/g, '')
}

function toAgorot(shekels: string): number {
  const n = parseInt(shekels || '0', 10)
  return Number.isFinite(n) ? n * 100 : 0
}

function toCount(value: string): number {
  const n = parseInt(value || '0', 10)
  return Number.isFinite(n) ? n : 0
}

function toShekelInput(agorot: number | null | undefined): string {
  if (!agorot) return ''
  return String(Math.trunc(agorot / 100))
}
