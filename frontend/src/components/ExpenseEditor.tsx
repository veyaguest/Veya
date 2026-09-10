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

interface Props {
  categories: ExpenseCategory[]
  /** ``null`` = הוספה חדשה. אחרת עריכה של שורה קיימת. */
  expense: Expense | null
  /** נפתח מתוך קבוצה מסוימת ⇒ מציגים רק אותה. ``null`` = כל הקבוצות. */
  initialCategory?: string | null
  /** מספר המגיעים שהמערכת כבר יודעת — מוצג, לא נשאל. */
  attendees: number
  /** מספר המוזמנים שהמערכת כבר יודעת. */
  invited: number
  busy?: boolean
  error?: string | null
  /** ``prepaidAgorot`` — רק בהוספה: סכום שכבר שולם, נרשם כתשלום ראשון
   *  מיד אחרי היצירה. ``undefined`` = לא שולם עדיין כלום. */
  onSave: (input: ExpenseInput, prepaidAgorot?: number) => void
  /** נקרא כשיומן התשלומים שינה את השורה — כדי שהמסך שמאחור יתעדכן. */
  onPaymentsChanged: (expense: Expense) => void
  onDelete?: () => void
  onCancel: () => void
}

/**
 * הוספה ועריכה של שורת הוצאה.
 *
 * ## העיקרון: "מה קניתי ← כמה זה עולה ← VEYA עושה את השאר"
 *
 * זוג שמתכנן חתונה לא אמור לדעת מה ההבדל בין "לפי מספר המגיעים" לבין
 * "לפי מספר המוזמנים", ובוודאי לא להחליט ביניהם. הוא יודע דבר אחד: הוא
 * סגר DJ ב-12,000 ₪. לכן המסך הזה שואל **שתי שאלות** — מה, וכמה — וכל
 * השאר נגזר: הקבוצה מהפריט, שיטת החישוב מהקטלוג, והכמות מהאירוע.
 *
 * ## מה המסך לא שואל, ולמה
 *
 * | מה | מאיפה זה מגיע במקום |
 * |---|---|
 * | קבוצה | מהפריט. "DJ" יושב ב"מוזיקה והפקה" — זה metadata, לא החלטה |
 * | שם ההוצאה | מהקטלוג. הוא הכותרת של הדיאלוג, לא שדה למלא |
 * | שיטת חישוב | מהקטלוג, ומוצגת כמשפט ("12,000 ₪ · מחיר קבוע") |
 * | מספר המגיעים / המוזמנים | מהאירוע. VEYA כבר יודעת, ולא תשאל שוב |
 *
 * מה שכן נשאר שאלה: המחיר, ההתחייבות מול הספק (היא בחוזה — VEYA לא
 * יכולה לדעת אותה), וסטטוס התשלום.
 *
 * ## "כך זה יחושב" — משפט, לא מכפלה
 *
 * האזור הזה **אינו מציג סכום מחושב**, וזו החלטה ולא חיסרון. בשורת
 * האולם המכפלה הפשוטה שגויה — יש התחייבות ויש מינימום כספי — ומספר
 * שמחושב בדפדפן היה מסלול חישוב שני שיכול לסטות מהשרת. אותו כלל שכבר
 * נאכף במתנות (``app/gift.py``): הדפדפן מצייר כסף, השרת מחשב אותו.
 * לכן כאן נאמר **הכלל** במילים, והסכום מגיע מהשרת אחרי השמירה.
 *
 * ## הקטלוג: חיפוש למי שיודע, קבוצות למי שמסתכל
 *
 * בחתונה יש 80 פריטים. מי שיודע שהוא מחפש "מגנטים" מקליד ומוצא; מי
 * שבא לראות מה בכלל אפשר סורק את הקבוצות, שנפתחות עם מה שרוב האירועים
 * מהסוג הזה כוללים ו"עוד N אפשרויות" לשאר.
 *
 * ## הכסף נקלט בשקלים ונשלח באגורות
 *
 * ההמרה קורית **פעם אחת**, כאן, ב-``toAgorot``. אין מספר עשרוני שנוסע
 * ברשת ואין חישוב כספי במסך.
 */
export function ExpenseEditor({
  categories,
  expense,
  initialCategory = null,
  attendees,
  invited,
  busy,
  error,
  onSave,
  onPaymentsChanged,
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
  const [reserve, setReserve] = useState(expense?.reserve_quantity?.toString() ?? '')
  const [note, setNote] = useState(expense?.note ?? '')
  const [vendor, setVendor] = useState(expense?.vendor ?? '')
  // ברירת המחדל היא הערכה: תקציב נבנה מהערכות, וסימון הכול כ"סוכם"
  // מלכתחילה מרוקן את ההבחנה מתוכן.
  const [isEstimated, setIsEstimated] = useState(expense?.is_estimated ?? true)
  // **רק בהוספה.** בעריכה יש יומן תשלומים מלא (``PaymentsPanel``), ושדה
  // בודד לצידו היה מקור שני לאותו מספר. כאן הוא קיצור דרך לזוג שמזין
  // הוצאה שכבר שילם עליה: הסכום נשמר כתשלום אחד מיד אחרי היצירה.
  const [prepaid, setPrepaid] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  // בעריכה מדלגים על שלב הבחירה. בהוספה הוא השלב הראשון.
  const [picking, setPicking] = useState(!editing)
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [onlyCategory, setOnlyCategory] = useState<string | null>(initialCategory)

  // ארבע שכבות שנפתחות לפי דרישה. ברירת המחדל של כולן סגורה: מי שבא
  // להזין DJ ב-12,000 לא צריך לראות אף אחת מהן.
  const [methodOpen, setMethodOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [contractOpen, setContractOpen] = useState(
    Boolean(expense?.min_total_agorot || expense?.reserve_quantity),
  )

  const amountRef = useRef<HTMLInputElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const labelRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // בבחירה — לחיפוש. בפרטים — למחיר, כי זה הדבר היחיד שנשאר להקליד.
    if (picking) searchRef.current?.focus()
    else amountRef.current?.focus()
  }, [picking])

  useEffect(() => {
    if (renaming) labelRef.current?.focus()
  }, [renaming])

  const category = useMemo(
    () => categories.find((c) => c.key === categoryKey) ?? null,
    [categories, categoryKey],
  )
  const catalogItem = category?.items.find((i) => i.key === itemKey) ?? null

  // שדה ההתחייבות נפתח לשורה שמחושבת לפי מגיעים — שם, ורק שם, יש חוזה
  // שנוקב בכמות מינימלית.
  const supportsCommitment = method === 'per_attendee'

  // ── חיפוש בקטלוג ──────────────────────────────────────────────────
  // כל מילה בשאילתה חייבת להימצא בשם הפריט או בשם הקבוצה, כך ש"צילום
  // מגנטים" מוצא גם כשהפריט נקרא "מגנטים" בלבד.
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
    // המוצעים קודם — הם מה שרוב האירועים מהסוג הזה כוללים.
    return hits
      .sort((a, b) => Number(b.item.is_default) - Number(a.item.is_default))
      .slice(0, 12)
  }, [query, categories])

  function pickItem(cat: ExpenseCategory, item: ExpenseCatalogItem | null, name = '') {
    setCategoryKey(cat.key)
    setItemKey(item?.key ?? '')
    setLabel(item?.label ?? name)
    // שיטת החישוב נגזרת מהפריט. הזוג לא בוחר אותה — הוא רואה אותה.
    setMethod(item?.calc_method ?? 'fixed')
    // כמות פתיחה מהתבנית (2 אלבומי הורים, 10% טיפים) — כדי שהשדה לא
    // ייפתח ריק כשיש ערך שכמעט תמיד נכון.
    setQuantity(item?.default_quantity != null ? String(item.default_quantity) : '')
    setMethodOpen(false)
    // שורה חופשית בלי שם מהחיפוש נפתחת עם שדה השם פתוח — אין קטלוג
    // לגזור ממנו שם, וטופס בלי שם לא ניתן לשמירה.
    setRenaming(item === null && !name)
    setQuery('')
    setPicking(false)
  }

  function submit() {
    const trimmed = label.trim()
    if (!trimmed) return
    onSave(
      {
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
        reserve_quantity: supportsCommitment ? toCount(reserve) || null : null,
        note: note.trim() || null,
        vendor: vendor.trim(),
        is_estimated: isEstimated,
        // ``is_paid`` ו-``paid_amount_agorot`` **לא נשלחים יותר**: מה ששולם
        // חי ביומן התשלומים, והשדות הישנים נשארו בשרת רק כמסלול נפילה
        // לשורות שטרם הומרו.
      },
      toAgorot(prepaid) || undefined,
    )
  }

  // ════════════════════════════════════════════════════════════════
  //  שלב 1 — מה ההוצאה?
  // ════════════════════════════════════════════════════════════════
  if (picking) {
    const searching = query.trim().length > 0
    const freeTextHome =
      categories.find((c) => c.key === onlyCategory) ?? categories[categories.length - 1]

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
            <input
              ref={searchRef}
              type="search"
              className="fin-search fin-catalog-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                // תוצאה יחידה + Enter = בחירה. עם כמה תוצאות אין ניחוש.
                if (e.key !== 'Enter') return
                e.preventDefault()
                if (searchResults.length === 1) {
                  pickItem(searchResults[0].category, searchResults[0].item)
                }
              }}
              placeholder={t.catalogSearchPlaceholder}
              aria-label={t.catalogSearchPlaceholder}
              autoComplete="off"
            />

            {searching ? (
              // ── תוצאות חיפוש: רשימה שטוחה, עם שם הקבוצה לצד כל פריט
              //    כדי שהבחירה תהיה מודעת ולא עיוורת.
              <>
                <ul className="fin-results">
                  {searchResults.length === 0 ? (
                    <li className="fin-results-empty">{t.catalogSearchEmpty}</li>
                  ) : (
                    searchResults.map(({ category: cat, item }) => (
                      <li key={`${cat.key}-${item.key}`}>
                        <button
                          type="button"
                          className="fin-result"
                          onClick={() => pickItem(cat, item)}
                        >
                          <span className="fin-result-name">{item.label}</span>
                          <span className="fin-result-meta">{cat.label}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
                {/* אין פריט מתאים ⇒ אפשר להוסיף את מה שהוקלד כשורה
                    חופשית, בלי לצאת מהחיפוש ולחפש קבוצה מתאימה. */}
                {freeTextHome && (
                  <button
                    type="button"
                    className="btn-link fin-catalog-more"
                    onClick={() => pickItem(freeTextHome, null, query.trim())}
                  >
                    {t.catalogAddFree(query.trim())}
                  </button>
                )}
              </>
            ) : (
              <>
                {onlyCategory && (
                  <button
                    type="button"
                    className="btn-link fin-catalog-all"
                    onClick={() => setOnlyCategory(null)}
                  >
                    {t.catalogAllGroups}
                  </button>
                )}

                {categories
                  .filter((cat) => !onlyCategory || cat.key === onlyCategory)
                  .map((cat) => {
                    const suggested = cat.items.filter((i) => i.is_default)
                    const more = cat.items.filter((i) => !i.is_default)
                    const open = expanded.has(cat.key) || suggested.length === 0

                    return (
                      <section key={cat.key} className="fin-catalog-group">
                        <h3 className="fin-catalog-title">{cat.label}</h3>
                        <div className="fin-catalog-items">
                          {suggested.map((item) => (
                            <button
                              key={item.key}
                              type="button"
                              className="fin-chip fin-chip-suggested"
                              onClick={() => pickItem(cat, item)}
                            >
                              {item.label}
                            </button>
                          ))}

                          {open &&
                            more.map((item) => (
                              <button
                                key={item.key}
                                type="button"
                                className="fin-chip"
                                onClick={() => pickItem(cat, item)}
                              >
                                {item.label}
                              </button>
                            ))}

                          {/* קיים בכל קבוצה ולא רק ב"הוצאות נוספות":
                              הזוג יודע לאיזו קבוצה ההוצאה שלו שייכת גם
                              כשהיא לא ברשימה. */}
                          {open && (
                            <button
                              type="button"
                              className="fin-chip fin-chip-custom"
                              onClick={() => pickItem(cat, null)}
                            >
                              {t.customItem}
                            </button>
                          )}
                        </div>

                        {!open && more.length > 0 && (
                          <button
                            type="button"
                            className="btn-link fin-catalog-more"
                            onClick={() =>
                              setExpanded((prev) => new Set(prev).add(cat.key))
                            }
                          >
                            {t.catalogMoreCount(more.length)}
                          </button>
                        )}
                      </section>
                    )
                  })}
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ════════════════════════════════════════════════════════════════
  //  שלב 2 — כמה זה עולה?
  // ════════════════════════════════════════════════════════════════
  return (
    <>
      <div className="overlay" onClick={onCancel}>
        <div className="dialog fin-editor" onClick={(e) => e.stopPropagation()}>
          <div className="dialog-head">
            {/* שם ההוצאה הוא הכותרת ולא שדה. הוא כבר נבחר, ושדה טקסט
                בראש הטופס אומר "מלא אותי" גם כשהוא מלא. */}
            <h2>{label || t.addExpense}</h2>
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
            {/* הקבוצה כ-metadata: מוצגת כדי שהבחירה תהיה שקופה, לא כדי
                שתתקבל שוב. "שינוי" מחזיר לקטלוג. */}
            <p className="fin-form-meta">
              <span className="fin-form-group">{category?.label ?? t.customItem}</span>
              {!editing && (
                <button type="button" className="btn-link" onClick={() => setPicking(true)}>
                  {t.changeItem}
                </button>
              )}
              {!renaming && (
                <button type="button" className="btn-link" onClick={() => setRenaming(true)}>
                  {t.renameExpense}
                </button>
              )}
            </p>

            {renaming && (
              <label className="field">
                <span className="field-label">{t.expenseNameLabel}</span>
                <input
                  ref={labelRef}
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder={t.expenseNamePlaceholder}
                  maxLength={120}
                  required
                />
              </label>
            )}

            {/* ── המחיר. השאלה היחידה שתמיד נשאלת ─────────────────── */}
            <div className="fin-row">
              <label className="field" hidden={method === 'percent'}>
                <span className="field-label">{priceLabel(method, catalogItem)}</span>
                {/* ``inputMode="numeric"`` פותח מקלדת ספרות בטלפון. */}
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

              {/* כמות נשאלת **רק** כשהמערכת לא יודעת אותה: יחידות שהזוג
                  קונה, ואחוז שהוא סיכם. מגיעים ומוזמנים לא נשאלים. */}
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

            {/* ── ההתחייבות: הדבר היחיד בחוזה ש-VEYA לא יכולה לדעת ─── */}
            {supportsCommitment && (
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
                <span className="field-hint">{t.commitmentHint}</span>
              </label>
            )}

            {/* ── "כך זה יחושב" — הכלל במילים, בלי מכפלה ──────────── */}
            <section className="fin-preview" aria-live="polite">
              <h3 className="fin-preview-title">{t.previewTitle}</h3>
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
              {!methodOpen && (
                <button
                  type="button"
                  className="btn-link fin-preview-change"
                  onClick={() => setMethodOpen(true)}
                >
                  {t.calcMethodChange}
                </button>
              )}
            </section>

            {methodOpen && (
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
            )}

            {/* ── תשלומים ─────────────────────────────────────────────
                בעריכה — יומן מלא, כי יש שורה קיימת לתלות עליה תשלומים.
                בהוספה — שדה אחד אופציונלי, כי אי אפשר לרשום תשלום על
                הוצאה שעוד לא נוצרה, וטופס יצירה עם טבלה ריקה בתוכו הוא
                טופס שנראה מסובך יותר ממה שהוא. */}
            {editing && expense ? (
              <>
                <h3 className="fin-subtitle">{t.paymentsTitle}</h3>
                <PaymentsPanel expense={expense} onChanged={onPaymentsChanged} />
              </>
            ) : (
              <label className="field">
                <span className="field-label">{t.prepaidLabel}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={prepaid}
                  onChange={(e) => setPrepaid(digitsOnly(e.target.value))}
                  placeholder="0"
                  dir="ltr"
                />
                <span className="field-hint">{t.prepaidHint}</span>
              </label>
            )}

            {/* ── מה שנשאר מקופל ──────────────────────────────────── */}
            {!detailsOpen ? (
              <button
                type="button"
                className="btn-link fin-more-details"
                onClick={() => setDetailsOpen(true)}
              >
                {t.moreDetails}
              </button>
            ) : (
              <div className="fin-more-block">
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

                {/* תיבת סימון ולא מתג: זו עובדה על המחיר, לא בורר בין
                    שני מצבים שווי-משקל. */}
                <label className="fin-check">
                  <input
                    type="checkbox"
                    checked={isEstimated}
                    onChange={(e) => setIsEstimated(e.target.checked)}
                  />
                  <span>{t.estimatedCheckbox}</span>
                </label>

                {/* המינימום הכספי רלוונטי לאחוז קטן מהחוזים, ולכן הוא
                    יושב שכבה אחת עמוק יותר — לא ליד ההתחייבות. */}
                {supportsCommitment &&
                  (contractOpen ? (
                    <>
                    <label className="field">
                      <span className="field-label">{t.reserveLabel}</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={reserve}
                        onChange={(e) => setReserve(digitsOnly(e.target.value))}
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
                        onChange={(e) => setMinTotal(digitsOnly(e.target.value))}
                        placeholder="0"
                        dir="ltr"
                      />
                      <span className="field-hint">{t.minTotalHint}</span>
                    </label>
                    </>
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

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            <div className="dialog-foot">
              <button type="submit" className="btn-primary" disabled={busy || !label.trim()}>
                {busy ? strings.common.saving : t.saveExpense}
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
