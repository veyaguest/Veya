import { useBackToClose } from '../lib/backToClose'
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
import { PaymentsPanel } from './PaymentsPanel'

const t = strings.finance

const e = t.editor

/** מה קורה אחרי שמירה: לסגור, לפתוח טופס ריק להוצאה נוספת, או לעבור
 *  להוצאה הבאה שעדיין בלי סכום. */
export type AfterSave = 'close' | 'another' | 'next'

/** "כבר שילמתם?" בהוספה — נרשם כתשלום ראשון מיד אחרי יצירת ההוצאה. */
export interface Prepaid {
  amount_agorot: number
  paid_on: string
}

interface Props {
  categories: ExpenseCategory[]
  /** ``null`` = הוספה חדשה. אחרת עריכה של שורה קיימת. */
  expense: Expense | null
  /** נפתח מתוך קבוצה מסוימת ⇒ מציגים את הפריטים שלה ראשונים. */
  initialCategory?: string | null
  /** מספר המגיעים שהמערכת כבר יודעת — מוצג, לא נשאל. */
  attendees: number
  /** מספר המוזמנים שהמערכת כבר יודעת. */
  invited: number
  busy?: boolean
  error?: string | null
  /**
   * כמה הוצאות **נוספות** מחכות לסכום אחרי זו. מעל 0 — הטופס במצב
   * "מילוי ברצף" (מתוך "מה נשאר לעשות"), והכפתור הראשי מעביר לבאה.
   */
  queueRemaining?: number
  onSave: (input: ExpenseInput, prepaid: Prepaid | undefined, after: AfterSave) => void
  /** נקרא כשיומן התשלומים שינה את השורה — כדי שהמסך שמאחור יתעדכן. */
  onPaymentsChanged: (expense: Expense) => void
  onDelete?: () => void
  onCancel: () => void
  /** ההוצאות שכבר ברשימה — פריט שכבר יש לו שורה לא נוצר פעמיים. */
  existing?: Expense[]
  /** פתיחת שורה קיימת לעריכה (במקום ליצור כפולה). */
  onOpenExisting?: (expense: Expense) => void
}

/**
 * הוספה ועריכה של שורת הוצאה — **חלון אחד, ארבע שאלות בסדר קבוע.**
 *
 * 1. **על מה?** — כפתורים לפריטים שרוב האירועים מהסוג הזה כוללים (מהקטלוג
 *    של סוג האירוע, ``is_default``), ו"עוד אפשרויות" שפותח חיפוש וכל הקבוצות
 *    **באותו חלון**. עד 2026-09-30 זה היה מסך נפרד שהתחלף במסך המחיר, והזוג
 *    לא ראה "טופס אחד".
 * 2. **כמה?** — השדה המרכזי: גדול, עם ₪ קבוע לידו ומקלדת ספרות בטלפון.
 * 3. **פרטים נוספים — לא חובה** — ספק, הערה, "כבר שילמתם?" (סכום ותאריך),
 *    הערכה, אופן החישוב ומינימום החוזה. מקופל.
 * 4. **שמירה** — ובהוספה גם "שמירה והוספת עוד"; במילוי ברצף — "שמירה
 *    ומעבר להוצאה הבאה".
 *
 * ## מה המסך לא שואל, ולמה
 *
 * קבוצה (נגזרת מהפריט), שיטת חישוב (מהקטלוג, מוצגת כמשפט), ומספר המגיעים
 * או המוזמנים (VEYA כבר יודעת). **אין "תאריך הוצאה"** — אין כזה במודל, ותאריך
 * יש רק לתשלום (החלטת מייסד 2026-09-30).
 *
 * ## הסכום חובה — בטופס
 *
 * השגיאה מופיעה ליד השדה ("הוסיפו סכום להוצאה"), לא בראש החלון. שורות בלי
 * סכום ממשיכות להיווצר רק מהתבנית — השרת לא השתנה.
 *
 * ## "כך זה יחושב" — משפט, לא מכפלה
 *
 * בשורת האולם המכפלה הפשוטה שגויה (יש התחייבות ומינימום), ומספר שמחושב
 * בדפדפן היה מסלול חישוב שני שיכול לסטות מהשרת. הכלל נאמר במילים, והסכום
 * מגיע מהשרת אחרי השמירה.
 *
 * ## הכסף נקלט בשקלים ונשלח באגורות
 *
 * ההמרה קורית **פעם אחת**, כאן, ב-``toAgorot``.
 */
export function ExpenseEditor({
  categories,
  expense,
  initialCategory = null,
  attendees,
  invited,
  busy,
  error,
  queueRemaining = 0,
  onSave,
  onPaymentsChanged,
  onDelete,
  onCancel,
  existing = [],
  onOpenExisting,
}: Props) {
  const editing = expense !== null
  const queued = queueRemaining > 0

  const [categoryKey, setCategoryKey] = useState(expense?.category ?? '')
  const [itemKey, setItemKey] = useState(expense?.item_key ?? '')
  const [label, setLabel] = useState(expense?.label ?? '')
  const [method, setMethod] = useState<CalcMethod>(expense?.calc_method ?? 'fixed')
  const [amount, setAmount] = useState(toShekelInput(expense?.amount_agorot))
  const [quantity, setQuantity] = useState(expense?.quantity?.toString() ?? '')
  const [committed, setCommitted] = useState(expense?.committed_quantity?.toString() ?? '')
  const [minTotal, setMinTotal] = useState(toShekelInput(expense?.min_total_agorot ?? null))
  const [reserve, setReserve] = useState(expense?.reserve_quantity?.toString() ?? '')
  const [note, setNote] = useState(expense?.note ?? '')
  const [vendor, setVendor] = useState(expense?.vendor ?? '')
  // ברירת המחדל היא הערכה: תקציב נבנה מהערכות, וסימון הכול כ"סוכם"
  // מלכתחילה מרוקן את ההבחנה מתוכן.
  const [isEstimated, setIsEstimated] = useState(expense?.is_estimated ?? true)
  // **רק בהוספה.** בעריכה יש יומן תשלומים מלא (``PaymentsPanel``).
  const [prepaid, setPrepaid] = useState('')
  const [prepaidOn, setPrepaidOn] = useState(todayIso())

  // "על מה?" פתוח לבחירה עד שנבחר פריט. בעריכה — כבר נבחר.
  const chosen = Boolean(label.trim()) || Boolean(itemKey)
  const [choosing, setChoosing] = useState(!editing)
  const [catalogOpen, setCatalogOpen] = useState(Boolean(initialCategory))
  const [query, setQuery] = useState('')
  const [renaming, setRenaming] = useState(false)

  const [detailsOpen, setDetailsOpen] = useState(false)
  const [methodOpen, setMethodOpen] = useState(false)
  const [contractOpen, setContractOpen] = useState(
    Boolean(expense?.min_total_agorot || expense?.reserve_quantity),
  )
  const [paymentsOpen, setPaymentsOpen] = useState(false)

  // שגיאות שדה — מוצגות רק אחרי ניסיון שמירה, וליד השדה שלהן.
  const [tried, setTried] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  const amountRef = useRef<HTMLInputElement>(null)
  const quantityRef = useRef<HTMLInputElement>(null)
  const labelRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // מה הוזן כשהחלון נפתח — כדי לדעת אם יש מה לאבד ביציאה.
  const initial = useRef(snapshot())
  function snapshot(): string {
    return JSON.stringify([
      categoryKey, itemKey, label, method, amount, quantity, committed,
      minTotal, reserve, note, vendor, isEstimated, prepaid,
    ])
  }
  const dirty = snapshot() !== initial.current

  /** ✕, רקע, Escape ו"חזור" — כולם עוברים כאן: יש מה לאבד ⇒ שואלים. */
  function requestClose() {
    if (busy) return
    if (dirty) setConfirmLeave(true)
    else onCancel()
  }
  // "חזור" בטלפון סוגר את החלון במקום לנווט אחורה (lib/backToClose).
  useBackToClose(true, requestClose)

  useEffect(() => {
    function onKey(ev: KeyboardEvent) {
      if (ev.key === 'Escape' && !confirmLeave && !confirmDelete) requestClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // אחרי בחירת "על מה" — ישר ל"כמה?". דרך effect ולא requestAnimationFrame:
  // השדה נוצר רק ברינדור שאחרי הבחירה, וה-effect רץ בדיוק אחריו.
  const [focusAmount, setFocusAmount] = useState(0)
  useEffect(() => {
    if (!focusAmount) return
    ;(method === 'percent' ? quantityRef : amountRef).current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusAmount])

  // במילוי ברצף הדבר היחיד שנשאר הוא הסכום — ישר אליו.
  useEffect(() => {
    if (queued) amountRef.current?.focus()
  }, [queued])

  useEffect(() => {
    if (renaming) labelRef.current?.focus()
  }, [renaming])

  useEffect(() => {
    if (catalogOpen && choosing) searchRef.current?.focus()
  }, [catalogOpen, choosing])

  const category = useMemo(
    () => categories.find((c) => c.key === categoryKey) ?? null,
    [categories, categoryKey],
  )
  const catalogItem = category?.items.find((i) => i.key === itemKey) ?? null

  const supportsCommitment = method === 'per_attendee'
  const showPreview =
    method !== 'fixed' && (method === 'percent' ? toCount(quantity) > 0 : toAgorot(amount) > 0)

  // ── "על מה?" — הפריטים שרוב האירועים מהסוג הזה כוללים ─────────────
  // נפתח מתוך קבוצה ("הוספה לצילום") ⇒ הפריטים שלה ראשונים.
  const quickPicks = useMemo(() => {
    const picks: { category: ExpenseCategory; item: ExpenseCatalogItem }[] = []
    const ordered = initialCategory
      ? [
          ...categories.filter((c) => c.key === initialCategory),
          ...categories.filter((c) => c.key !== initialCategory),
        ]
      : categories
    for (const cat of ordered) {
      for (const item of cat.items) {
        if (item.is_default || cat.key === initialCategory) picks.push({ category: cat, item })
      }
    }
    return picks
  }, [categories, initialCategory])

  // חיפוש: כל מילה חייבת להימצא בשם הפריט או בשם הקבוצה.
  const searchResults = useMemo(() => {
    const q = query.trim()
    if (!q) return []
    const words = q.split(/\s+/).filter(Boolean)
    const hits: { category: ExpenseCategory; item: ExpenseCatalogItem }[] = []
    for (const cat of categories) {
      for (const item of cat.items) {
        const haystack = `${item.label} ${cat.label}`
        if (words.every((w) => haystack.includes(w))) hits.push({ category: cat, item })
      }
    }
    return hits
      .sort((a, b) => Number(b.item.is_default) - Number(a.item.is_default))
      .slice(0, 12)
  }, [query, categories])

  const listedByItem = useMemo(() => {
    const map = new Map<string, Expense>()
    for (const x of existing) if (x.item_key) map.set(`${x.category}:${x.item_key}`, x)
    return map
  }, [existing])

  const otherCategory =
    categories.find((c) => c.key === 'other') ?? categories[categories.length - 1]

  function pickItem(cat: ExpenseCategory, item: ExpenseCatalogItem | null, name = '') {
    const listed = item ? listedByItem.get(`${cat.key}:${item.key}`) : undefined
    if (listed && onOpenExisting) {
      onOpenExisting(listed)
      return
    }
    setCategoryKey(cat.key)
    setItemKey(item?.key ?? '')
    setLabel(item?.label ?? name)
    // שיטת החישוב נגזרת מהפריט. הזוג לא בוחר אותה — הוא רואה אותה.
    setMethod(item?.calc_method ?? 'fixed')
    setQuantity(item?.default_quantity != null ? String(item.default_quantity) : '')
    setMethodOpen(false)
    // שורה חופשית בלי שם נפתחת עם שדה השם — טופס בלי שם לא נשמר.
    const needsName = item === null && !name
    setRenaming(needsName)
    setQuery('')
    setChoosing(false)
    setCatalogOpen(false)
    // השאלה הבאה היא "כמה?" — ישר אליה (אחרי שהשדה מופיע).
    if (!needsName) setFocusAmount((n) => n + 1)
  }

  // ── בדיקות — ליד השדה, בשפה של הזוג ──────────────────────────────
  const whatError = !chosen ? e.whatError : null
  const nameError = chosen && !label.trim() ? e.nameError : null
  const amountError =
    method === 'percent'
      ? toCount(quantity) > 0
        ? null
        : e.percentError
      : toAgorot(amount) > 0
        ? null
        : e.amountError
  const quantityError = method === 'per_unit' && toCount(quantity) <= 0 ? e.quantityError : null
  const valid = !whatError && !nameError && !amountError && !quantityError

  function submit(after: AfterSave) {
    setTried(true)
    if (!valid) {
      // לשדה הראשון שחסר — כדי שהזוג יראה מה עוד צריך.
      if (nameError) labelRef.current?.focus()
      else if (amountError) (method === 'percent' ? quantityRef : amountRef).current?.focus()
      else if (quantityError) quantityRef.current?.focus()
      return
    }
    const prepaidAgorot = toAgorot(prepaid)
    onSave(
      {
        category: categoryKey || 'other',
        item_key: itemKey,
        label: label.trim(),
        calc_method: method,
        amount_agorot: toAgorot(amount),
        // ``quantity`` משרת שתי שיטות: יחידות ב-per_unit, ואחוזים ב-percent.
        quantity:
          method === 'per_unit' || method === 'percent' ? toCount(quantity) : null,
        committed_quantity: supportsCommitment ? toCount(committed) || null : null,
        min_total_agorot: toAgorot(minTotal) || null,
        reserve_quantity: supportsCommitment ? toCount(reserve) || null : null,
        note: note.trim() || null,
        vendor: vendor.trim(),
        is_estimated: isEstimated,
      },
      !editing && prepaidAgorot ? { amount_agorot: prepaidAgorot, paid_on: prepaidOn } : undefined,
      after,
    )
  }

  const primaryAfter: AfterSave = queued ? 'next' : 'close'
  const primaryLabel = busy
    ? strings.common.saving
    : queued
      ? e.saveAndNext
      : editing
        ? e.saveChanges
        : e.save

  return (
    <>
      <div className="overlay fin-editor-overlay" onClick={requestClose}>
        <div
          className="dialog fin-editor"
          role="dialog"
          aria-modal="true"
          aria-labelledby="fin-editor-title"
          onClick={(ev) => ev.stopPropagation()}
        >
          <div className="dialog-head">
            <h2 id="fin-editor-title">{editing ? e.editTitle : e.addTitle}</h2>
            <button type="button" className="x" onClick={requestClose} aria-label={strings.common.cancel}>
              ✕
            </button>
          </div>

          <form
            className="dialog-body fin-form"
            noValidate
            onSubmit={(ev) => {
              ev.preventDefault()
              submit(primaryAfter)
            }}
          >
            {queued && <p className="fin-queue-note">{e.queueLeft(queueRemaining)}</p>}

            {/* ── 1. על מה? ─────────────────────────────────────────── */}
            <fieldset className="fin-step">
              <legend className="fin-step-title">{e.whatTitle}</legend>

              {chosen && !choosing ? (
                <div className="fin-chosen">
                  <span className="fin-chosen-name">{label || t.customItem}</span>
                  {category && <span className="fin-chosen-group">{category.label}</span>}
                  <span className="fin-chosen-actions">
                    {!editing && (
                      <button type="button" className="btn-link" onClick={() => setChoosing(true)}>
                        {t.changeItem}
                      </button>
                    )}
                    {!renaming && (
                      <button type="button" className="btn-link" onClick={() => setRenaming(true)}>
                        {t.renameExpense}
                      </button>
                    )}
                  </span>
                </div>
              ) : (
                <div className="fin-choose">
                  <div className="fin-catalog-items">
                    {quickPicks.map(({ category: cat, item }) => (
                      <button
                        key={`${cat.key}-${item.key}`}
                        type="button"
                        className="fin-chip"
                        onClick={() => pickItem(cat, item)}
                      >
                        {item.label}
                        {listedByItem.has(`${cat.key}:${item.key}`) && (
                          <span className="fin-chip-listed"> · {t.alreadyListed}</span>
                        )}
                      </button>
                    ))}
                    {otherCategory && (
                      <button
                        type="button"
                        className="fin-chip fin-chip-custom"
                        onClick={() => pickItem(otherCategory, null)}
                      >
                        {t.customItem}
                      </button>
                    )}
                  </div>

                  <button
                    type="button"
                    className="btn-link fin-catalog-more"
                    aria-expanded={catalogOpen}
                    onClick={() => setCatalogOpen((v) => !v)}
                  >
                    {catalogOpen ? e.fewerOptions : e.moreOptions}
                  </button>

                  {catalogOpen && (
                    <Catalog
                      categories={categories}
                      query={query}
                      onQuery={setQuery}
                      searchRef={searchRef}
                      results={searchResults}
                      listed={listedByItem}
                      onPick={pickItem}
                      onPickFree={(name) => otherCategory && pickItem(otherCategory, null, name)}
                    />
                  )}
                </div>
              )}

              {renaming && (
                <label className="field">
                  <span className="field-label">{t.expenseNameLabel}</span>
                  <input
                    ref={labelRef}
                    type="text"
                    value={label}
                    onChange={(ev) => setLabel(ev.target.value)}
                    placeholder={t.expenseNamePlaceholder}
                    maxLength={120}
                    aria-invalid={tried && !!nameError}
                    aria-describedby={tried && nameError ? 'fin-name-error' : undefined}
                  />
                  {tried && nameError && (
                    <span id="fin-name-error" className="fin-field-error">{nameError}</span>
                  )}
                </label>
              )}

              {tried && whatError && <p className="fin-field-error">{whatError}</p>}
            </fieldset>

            {/* ── 2. כמה? — אחרי שנבחר "על מה" ──────────────────────── */}
            {chosen && !choosing && (
              <>
                <div className="fin-step">
                  <label className="fin-step-title" htmlFor={method === 'percent' ? 'fin-quantity' : 'fin-amount'}>
                    {e.howMuchTitle}
                    {method !== 'fixed' && (
                      <span className="fin-step-sub">
                        {method === 'percent' ? t.percentLabel : priceLabel(method, catalogItem)}
                      </span>
                    )}
                  </label>

                  <div className="fin-money-row">
                    {method !== 'percent' && (
                      <div className={`fin-money ${tried && amountError ? 'is-invalid' : ''}`}>
                        {/* ``inputMode="numeric"`` — מקלדת ספרות בטלפון. ה-₪ קבוע
                            ליד השדה: לא מקלידים סימן מטבע. */}
                        <input
                          id="fin-amount"
                          ref={amountRef}
                          type="text"
                          inputMode="numeric"
                          autoComplete="off"
                          value={amount ? Number(amount).toLocaleString('he-IL') : ''}
                          onChange={(ev) => setAmount(digitsOnly(ev.target.value))}
                          placeholder="0"
                          dir="ltr"
                          aria-invalid={tried && !!amountError}
                          aria-describedby={tried && amountError ? 'fin-amount-error' : undefined}
                        />
                        <span className="fin-money-cur" aria-hidden="true">₪</span>
                      </div>
                    )}

                    {/* כמות נשאלת **רק** כשהמערכת לא יודעת אותה. */}
                    {(method === 'per_unit' || method === 'percent') && (
                      <label className="field fin-qty">
                        {method === 'per_unit' && (
                          <span className="field-label">{t.quantityLabel}</span>
                        )}
                        <input
                          id="fin-quantity"
                          ref={quantityRef}
                          type="text"
                          inputMode="numeric"
                          value={quantity}
                          onChange={(ev) => setQuantity(digitsOnly(ev.target.value))}
                          placeholder={method === 'percent' ? '10' : '1'}
                          dir="ltr"
                          aria-invalid={tried && !!(method === 'percent' ? amountError : quantityError)}
                        />
                      </label>
                    )}
                  </div>
                  {tried && amountError && (
                    <span id="fin-amount-error" className="fin-field-error">{amountError}</span>
                  )}
                  {tried && !amountError && quantityError && (
                    <span className="fin-field-error">{quantityError}</span>
                  )}

                  {/* ההתחייבות — הדבר היחיד בחוזה ש-VEYA לא יכולה לדעת. */}
                  {supportsCommitment && (
                    <label className="field">
                      <span className="field-label">{t.committedQuantityLabel}</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={committed}
                        onChange={(ev) => setCommitted(digitsOnly(ev.target.value))}
                        placeholder={t.committedQuantityPlaceholder}
                        dir="ltr"
                      />
                      <span className="field-hint">{t.commitmentHint}</span>
                    </label>
                  )}

                  {showPreview && (
                    <section className="fin-preview" aria-live="polite">
                      <p className="fin-preview-line">
                        {describePreview({
                          method,
                          amount,
                          quantity,
                          committed: supportsCommitment ? toCount(committed) : 0,
                          attendees,
                          invited,
                        })}
                      </p>
                      {supportsCommitment && toCount(committed) > 0 && (
                        <p className="fin-preview-note">
                          {t.previewCommitment(toCount(committed), attendees)}
                        </p>
                      )}
                      {toAgorot(minTotal) > 0 && (
                        <p className="fin-preview-note">
                          {t.previewMinTotal(shekels(toAgorot(minTotal)))}
                        </p>
                      )}
                    </section>
                  )}
                </div>

                {/* ── 3. פרטים נוספים — לא חובה ──────────────────────── */}
                <button
                  type="button"
                  className="btn-link fin-more-details"
                  aria-expanded={detailsOpen}
                  onClick={() => setDetailsOpen((v) => !v)}
                >
                  {detailsOpen ? e.detailsClose : e.detailsToggle}
                </button>

                {detailsOpen && (
                  <div className="fin-more-block">
                    {!editing && (
                      <div className="fin-row">
                        <label className="field">
                          <span className="field-label">{t.prepaidLabel}</span>
                          <input
                            type="text"
                            inputMode="numeric"
                            value={prepaid}
                            onChange={(ev) => setPrepaid(digitsOnly(ev.target.value))}
                            placeholder="0"
                            dir="ltr"
                          />
                        </label>
                        {toAgorot(prepaid) > 0 && (
                          <label className="field">
                            <span className="field-label">{e.prepaidDateLabel}</span>
                            <input
                              type="date"
                              value={prepaidOn}
                              onChange={(ev) => setPrepaidOn(ev.target.value)}
                              max={todayIso()}
                            />
                          </label>
                        )}
                      </div>
                    )}

                    <label className="field">
                      <span className="field-label">{t.vendorLabel}</span>
                      <input
                        type="text"
                        value={vendor}
                        onChange={(ev) => setVendor(ev.target.value)}
                        placeholder={t.vendorPlaceholder}
                        maxLength={120}
                      />
                    </label>

                    <label className="field">
                      <span className="field-label">{t.noteLabel}</span>
                      <input
                        type="text"
                        value={note}
                        onChange={(ev) => setNote(ev.target.value)}
                        placeholder={t.notePlaceholder}
                        maxLength={500}
                      />
                    </label>

                    <label className="fin-check">
                      <input
                        type="checkbox"
                        checked={isEstimated}
                        onChange={(ev) => setIsEstimated(ev.target.checked)}
                      />
                      <span>{t.estimatedCheckbox}</span>
                    </label>

                    {methodOpen ? (
                      <fieldset className="fin-method">
                        <legend className="field-label">{t.calcMethodLabel}</legend>
                        <div className="fin-method-options">
                          {(
                            ['fixed', 'per_attendee', 'per_guest', 'per_unit', 'percent'] as CalcMethod[]
                          ).map((m) => (
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
                          ))}
                        </div>
                      </fieldset>
                    ) : (
                      <button
                        type="button"
                        className="btn-link fin-preview-change"
                        onClick={() => setMethodOpen(true)}
                      >
                        {t.calcMethodChange}
                      </button>
                    )}

                    {supportsCommitment &&
                      (contractOpen ? (
                        <div className="fin-row">
                          <label className="field">
                            <span className="field-label">{t.reserveLabel}</span>
                            <input
                              type="text"
                              inputMode="numeric"
                              value={reserve}
                              onChange={(ev) => setReserve(digitsOnly(ev.target.value))}
                              placeholder="0"
                              dir="ltr"
                            />
                            <span className="field-hint">{t.reserveHint}</span>
                          </label>
                          <label className="field">
                            <span className="field-label">{t.minTotalLabel}</span>
                            <input
                              type="text"
                              inputMode="numeric"
                              value={minTotal}
                              onChange={(ev) => setMinTotal(digitsOnly(ev.target.value))}
                              placeholder="0"
                              dir="ltr"
                            />
                            <span className="field-hint">{t.minTotalHint}</span>
                          </label>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn-link"
                          onClick={() => setContractOpen(true)}
                        >
                          {t.contractMore}
                        </button>
                      ))}
                  </div>
                )}

                {/* ── תשלומים (בעריכה) — אזור נפרד ומקופל ────────────────
                    כל פעולה ביומן נשמרת מיד בשרת, בלי קשר לכפתור השמירה של
                    הטופס. לכן הוא לא חלק מהשאלות שמעל אלא אזור משלו. */}
                {editing && expense && (
                  <div className="fin-payments-block">
                    <button
                      type="button"
                      className="btn-link fin-more-details"
                      aria-expanded={paymentsOpen}
                      onClick={() => setPaymentsOpen((v) => !v)}
                    >
                      {t.paymentsTitle}
                      {expense.total_agorot > 0 && (
                        <span className="fin-payments-summary">
                          {e.paymentsSummary(expense.paid_display, expense.remaining_display)}
                        </span>
                      )}
                    </button>
                    {paymentsOpen && (
                      <PaymentsPanel expense={expense} onChanged={onPaymentsChanged} />
                    )}
                  </div>
                )}
              </>
            )}

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            {/* ── 4. שמירה — צמודה לתחתית החלון, גם כשהמקלדת פתוחה ─── */}
            <div className="dialog-foot fin-editor-foot">
              <button type="submit" className="btn-primary" disabled={busy}>
                {primaryLabel}
              </button>
              {!editing && (
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={busy}
                  onClick={() => submit('another')}
                >
                  {e.saveAndAnother}
                </button>
              )}
              {queued && (
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={busy}
                  onClick={() => submit('close')}
                >
                  {e.saveAndFinish}
                </button>
              )}
            </div>

            {/* מחיקה — קיימת, אבל לא בולטת יותר מהשמירה. */}
            {editing && onDelete && (
              <button
                type="button"
                className="btn-link fin-delete-link"
                onClick={() => setConfirmDelete(true)}
                disabled={busy}
              >
                {t.deleteExpenseButton}
              </button>
            )}
          </form>
        </div>
      </div>

      {confirmDelete && onDelete && (
        <ConfirmDialog
          title={t.deleteExpenseTitle}
          message={t.deleteExpenseBody(expense?.label ?? '', expense?.payments.length ?? 0)}
          confirmLabel={t.deleteExpenseButton}
          danger
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      {confirmLeave && (
        <ConfirmDialog
          title={e.leaveTitle}
          message={e.leaveBody}
          confirmLabel={e.leaveConfirm}
          onConfirm={onCancel}
          onCancel={() => setConfirmLeave(false)}
        />
      )}
    </>
  )
}

/**
 * "עוד אפשרויות" — חיפוש וכל הקבוצות, **באותו חלון** מתחת לכפתורים המהירים.
 * מי שיודע מה הוא מחפש מקליד; מי שבא לראות מה אפשר — סורק את הקבוצות.
 */
function Catalog({
  categories,
  query,
  onQuery,
  searchRef,
  results,
  listed,
  onPick,
  onPickFree,
}: {
  categories: ExpenseCategory[]
  query: string
  onQuery: (q: string) => void
  searchRef: React.RefObject<HTMLInputElement | null>
  results: { category: ExpenseCategory; item: ExpenseCatalogItem }[]
  listed: Map<string, Expense>
  onPick: (cat: ExpenseCategory, item: ExpenseCatalogItem | null, name?: string) => void
  onPickFree: (name: string) => void
}) {
  const searching = query.trim().length > 0
  return (
    <div className="fin-catalog">
      <input
        ref={searchRef}
        type="search"
        className="fin-search fin-catalog-search"
        value={query}
        onChange={(ev) => onQuery(ev.target.value)}
        onKeyDown={(ev) => {
          // תוצאה יחידה + Enter = בחירה. עם כמה תוצאות אין ניחוש.
          if (ev.key !== 'Enter') return
          ev.preventDefault()
          if (results.length === 1) onPick(results[0].category, results[0].item)
        }}
        placeholder={t.catalogSearchPlaceholder}
        aria-label={t.catalogSearchPlaceholder}
        autoComplete="off"
      />

      {searching ? (
        <>
          <ul className="fin-results">
            {results.length === 0 ? (
              <li className="fin-results-empty">{t.catalogSearchEmpty}</li>
            ) : (
              results.map(({ category: cat, item }) => (
                <li key={`${cat.key}-${item.key}`}>
                  <button type="button" className="fin-result" onClick={() => onPick(cat, item)}>
                    <span className="fin-result-name">{item.label}</span>
                    <span className="fin-result-meta">
                      {listed.has(`${cat.key}:${item.key}`)
                        ? `${cat.label} · ${t.alreadyListed}`
                        : cat.label}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
          <button
            type="button"
            className="btn-link fin-catalog-more"
            onClick={() => onPickFree(query.trim())}
          >
            {t.catalogAddFree(query.trim())}
          </button>
        </>
      ) : (
        categories.map((cat) => (
          <section key={cat.key} className="fin-catalog-group">
            <h3 className="fin-catalog-title">{cat.label}</h3>
            <div className="fin-catalog-items">
              {cat.items.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className="fin-chip"
                  onClick={() => onPick(cat, item)}
                >
                  {item.label}
                  {listed.has(`${cat.key}:${item.key}`) && (
                    <span className="fin-chip-listed"> · {t.alreadyListed}</span>
                  )}
                </button>
              ))}
              <button
                type="button"
                className="fin-chip fin-chip-custom"
                onClick={() => onPick(cat, null)}
              >
                {t.customItem}
              </button>
            </div>
          </section>
        ))
      )}
    </div>
  )
}

/** היום, ``YYYY-MM-DD`` בשעון המכשיר — ברירת המחדל ל"מתי שילמתם?". */
function todayIso(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// ── תיאור החישוב ─────────────────────────────────────────────────────

/**
 * "כך זה יחושב" — **משפט שמתאר את הכלל, לא מספר שמחושב כאן.**
 *
 * ראו ההסבר המלא בראש הקובץ: מכפלה בדפדפן הייתה מסלול חישוב שני, והיא
 * גם הייתה שגויה בשורה החשובה ביותר (האולם, שבו יש התחייבות ומינימום).
 */
function describePreview({
  method,
  amount,
  quantity,
  committed,
  attendees,
  invited,
}: {
  method: CalcMethod
  amount: string
  quantity: string
  committed: number
  attendees: number
  invited: number
}): string {
  if (method === 'percent') {
    const pct = toCount(quantity)
    return pct ? t.previewPercent(pct) : t.previewEmpty
  }

  const agorot = toAgorot(amount)
  if (!agorot) return t.previewEmpty
  const price = shekels(agorot)

  switch (method) {
    case 'per_attendee':
      // יש התחייבות ⇒ הכמות עוד לא הוכרעה כאן, והמשפט שמתחת אומר
      // עליה את הדבר הנכון. מכפלה ב"מגיעים" הייתה סותרת אותו.
      return committed > 0
        ? t.previewPerPortion(price)
        : t.previewPerAttendee(price, attendees)
    case 'per_guest':
      return t.previewPerGuest(price, invited)
    case 'per_unit':
      return t.previewPerUnit(price, toCount(quantity))
    default:
      return t.previewFixed(price)
  }
}

/** תווית שדה המחיר, בשפה של הפריט שנבחר. */
function priceLabel(method: CalcMethod, item: ExpenseCatalogItem | null): string {
  if (method === 'per_unit') return t.unitPriceLabel
  // שורה שנמכרת בהתחייבות היא שורת מנה — "מחיר למנה", לא "מחיר לאדם".
  if (method === 'per_attendee') {
    return item?.supports_commitment ? t.mealPriceLabel : t.perPersonPriceLabel
  }
  if (method === 'per_guest') return t.perGuestPriceLabel
  return t.amountLabel
}

// ── המרות ────────────────────────────────────────────────────────────
//
// **נקודת ההמרה היחידה בין שקלים לאגורות בכל המסך.** הזוג מקליד שקלים
// שלמים; השרת מקבל ומחזיר אגורות. כל חישוב כספי קורה בשרת, ולכן אין
// כאן שום פעולת כסף מעבר לכפל/חילוק ב-100.

function digitsOnly(value: string): string {
  return value.replace(/[^\d]/g, '')
}

function toAgorot(shekelInput: string): number {
  const n = parseInt(shekelInput || '0', 10)
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

/** עיצוב סכום לתיאור החישוב בלבד — הצגה, לא חישוב. */
function shekels(agorot: number): string {
  return `${Math.trunc(agorot / 100).toLocaleString('he-IL')} ₪`
}
