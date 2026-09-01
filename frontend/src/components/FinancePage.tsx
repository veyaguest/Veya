import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  applyExpenseTemplate,
  createExpense,
  deleteEnvelope,
  deleteExpense,
  getExpenseCategories,
  getFinance,
  getGiftCounting,
  getFinanceReport,
  getGiftsByGuest,
  updateExpense,
} from '../api'
import type {
  Commitment,
  Expense,
  ExpenseCategory,
  ExpenseInput,
  FinanceReport,
  FinanceSummary,
  GiftCounting,
  GiftEntry,
  GuestGiftRow,
} from '../types'
import { strings } from '../strings/he'
import { activeEventTerms } from '../strings/eventTypes'
import { ConfirmDialog } from './ConfirmDialog'
import { EnvelopeCounter } from './EnvelopeCounter'
import { ExpenseEditor } from './ExpenseEditor'
import './FinancePage.css'

const t = strings.finance

type Tab = 'cost' | 'counting' | 'summary'

/**
 * "כספי האירוע" — עלות האירוע, ספירת המתנות שאחריו, והתוצאה.
 *
 * ## למה זה מסך אחד עם שלוש לשוניות ולא שלושה מסכים
 *
 * זו שרשרת אחת: מוזמנים ← אישורי הגעה ← עלות ← מתנות ← תוצאה. פיצול
 * לשלושה פריטי ניווט היה מסתיר בדיוק את הקשר הזה, וגם היה מוסיף שלושה
 * פריטים לניווט של חמישה. הלשונית הפעילה נבחרת לפי מצב האירוע: לפני
 * האירוע נפתחים בעלות, מיום האירוע ואילך בספירת המתנות.
 *
 * ## המסך לא מחשב כסף
 *
 * כל מספר כאן מגיע מוכן מהשרת (``total_display``, ``next_attendee_display``
 * וכו'). אותו כלל שכבר נאכף במתנות (``app/gift.py``): שני מקורות חישוב
 * לאותו מספר הם ההגדרה של באג שמתגלה מול חשבונית. היוצא מן הכלל היחיד
 * הוא ייצוא הדוח, שמעצב מחדש מספרים שכבר חושבו.
 *
 * ## Event-first
 *
 * הכותרות נבנות מהלקסיקון (``activeEventTerms().eventNoun``) — "עלות
 * החתונה" בחתונה, "עלות הברית" בברית. אין כאן מילה חתונתית קשיחה.
 */
export function FinancePage() {
  const terms = activeEventTerms()

  const [data, setData] = useState<FinanceSummary | null>(null)
  const [categories, setCategories] = useState<ExpenseCategory[]>([])
  const [counting, setCounting] = useState<GiftCounting | null>(null)
  const [byGuest, setByGuest] = useState<GuestGiftRow[] | null>(null)

  const [tab, setTab] = useState<Tab | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const [editing, setEditing] = useState<Expense | null | undefined>(undefined)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [countingNow, setCountingNow] = useState(false)
  const [deletingEnvelope, setDeletingEnvelope] = useState<GiftEntry | null>(null)

  // מסלול טעינה אחד בלבד, עם אותו ניקוי — בדיוק כמו ב-GiftsPage. כפתור
  // "ניסיון חוזר" מגדיל את המונה וה-effect רץ מחדש.
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    Promise.all([getFinance(), getExpenseCategories(), getGiftCounting()])
      .then(([summary, cats, count]) => {
        if (!alive) return
        setData(summary)
        setCategories(cats)
        setCounting(count)
        // הלשונית הראשונה נבחרת פעם אחת בלבד, לפי מצב האירוע — ואחר כך
        // בחירת המשתמש מנצחת ולא נדרסת בכל רענון.
        setTab((prev) => prev ?? (count.counting_open ? 'counting' : 'cost'))
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : t.loadError))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [attempt])

  /** רענון אחרי כל שינוי — מהשרת, כדי שהסיכום והשורות לא יסטו זה מזה. */
  const refresh = useCallback(() => {
    Promise.all([getFinance(), getGiftCounting()])
      .then(([summary, count]) => {
        setData(summary)
        setCounting(count)
      })
      .catch(() => undefined)
    // "לפי מוזמן" נטען רק אם הוא כבר פתוח — אין טעם למשוך רשימה של 500
    // שורות שאיש לא מסתכל עליה.
    if (byGuest !== null) getGiftsByGuest().then(setByGuest).catch(() => undefined)
  }, [byGuest])

  async function handleSaveExpense(input: ExpenseInput) {
    setSaving(true)
    setSaveError(null)
    try {
      if (editing) await updateExpense(editing.id, input)
      else await createExpense(input)
      setEditing(undefined)
      refresh()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteExpense() {
    if (!editing) return
    setSaving(true)
    try {
      await deleteExpense(editing.id)
      setEditing(undefined)
      refresh()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t.saveError)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="load-text">{strings.common.loading}</p>
  if (error) {
    return (
      <div className="fin-page">
        <p className="form-error" role="alert">{error}</p>
        <div className="empty-actions">
          <button type="button" className="btn-ghost" onClick={() => setAttempt((n) => n + 1)}>
            {strings.common.retry}
          </button>
        </div>
      </div>
    )
  }
  if (!data || !counting) return null

  return (
    <div className="fin-page">
      {/* גיבור אחד בכל רגע. בלשונית הספירה הגיבור הוא סכום המתנות
          (בתוך הלשונית עצמה), ובסיכום הוא התוצאה — שני מספרי-ענק זה
          מעל זה הם היררכיה שבורה, לא צפיפות מידע. */}
      {tab === 'cost' && <FinanceHero data={data} />}

      <nav className="fin-tabs" aria-label={t.navTitle(terms.eventNoun)}>
        <TabButton current={tab} value="cost" onSelect={setTab}>
          {t.costTitle(terms.eventNoun)}
        </TabButton>
        <TabButton current={tab} value="counting" onSelect={setTab}>
          {t.countingTitle}
        </TabButton>
        <TabButton current={tab} value="summary" onSelect={setTab}>
          {t.summaryTitle(terms.eventNoun)}
        </TabButton>
      </nav>

      {tab === 'cost' && (
        <CostTab
          data={data}
          terms={terms}
          onAdd={() => setEditing(null)}
          onEdit={setEditing}
          onTemplateApplied={refresh}
        />
      )}

      {tab === 'counting' && (
        <CountingTab
          counting={counting}
          byGuest={byGuest}
          countingNow={countingNow}
          onStart={() => setCountingNow(true)}
          onStop={() => {
            setCountingNow(false)
            refresh()
          }}
          onSaved={refresh}
          onLoadByGuest={() => getGiftsByGuest().then(setByGuest).catch(() => setByGuest([]))}
          onDeleteEntry={setDeletingEnvelope}
        />
      )}

      {tab === 'summary' && <SummaryTab data={data} terms={terms} />}

      {editing !== undefined && (
        <ExpenseEditor
          categories={categories}
          expense={editing}
          busy={saving}
          error={saveError}
          onSave={handleSaveExpense}
          onDelete={editing ? handleDeleteExpense : undefined}
          onCancel={() => {
            setEditing(undefined)
            setSaveError(null)
          }}
        />
      )}

      {deletingEnvelope && (
        <ConfirmDialog
          title={t.deleteEnvelopeTitle}
          message={t.deleteEnvelopeBody(
            deletingEnvelope.envelope_number ?? 0,
            deletingEnvelope.amount_display,
          )}
          confirmLabel={strings.common.delete}
          danger
          onConfirm={async () => {
            await deleteEnvelope(deletingEnvelope.id).catch(() => undefined)
            setDeletingEnvelope(null)
            refresh()
          }}
          onCancel={() => setDeletingEnvelope(null)}
        />
      )}
    </div>
  )
}

function TabButton({
  current,
  value,
  onSelect,
  children,
}: {
  current: Tab | null
  value: Tab
  onSelect: (t: Tab) => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className={`fin-tab ${current === value ? 'active' : ''}`}
      aria-current={current === value ? 'page' : undefined}
      onClick={() => onSelect(value)}
    >
      {children}
    </button>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  הכותרת — העובדה הגדולה
// ════════════════════════════════════════════════════════════════════════

/**
 * סה״כ העלות, ולצידה מספר המגיעים והעלות הממוצעת.
 *
 * **אזור ולא כרטיס** — אותה החלטה כמו במסך המתנות באשראי: זו העובדה
 * היחידה שראויה לגודל, ומסגרת סביבה רק הייתה מקטינה אותה.
 */
function FinanceHero({ data }: { data: FinanceSummary }) {
  return (
    <section className="fin-hero" aria-label={t.totalCostLabel}>
      <p className="fin-hero-label">{t.totalCostLabel}</p>
      <p className="fin-hero-value">{data.cost.total_display}</p>
      <div className="fin-hero-facts">
        <Fact label={t.attendeesLabel} value={String(data.cost.attendees)} />
        <Fact
          label={t.perPersonLabel}
          // אין מגיעים ⇒ אין ממוצע. "0 ₪ לאדם" הוא מספר מומצא, והמשפט
          // שבמקומו אומר בדיוק מתי הוא יופיע.
          value={data.cost.cost_per_attendee_display || t.perPersonEmpty}
        />
        <Fact label={t.fixedLabel} value={data.cost.fixed_display} />
        <Fact label={t.variableLabel} value={data.cost.variable_display} />
        {/* מוצג רק כשבאמת שולם משהו: "0 ₪ שולם" בתחילת התכנון הוא
            מספר נכון שלא אומר כלום, והוא רק מוסיף רעש. */}
        {data.cost.paid_agorot > 0 && (
          <>
            <Fact label={t.paidSummary} value={data.cost.paid_display} />
            <Fact label={t.unpaidSummary} value={data.cost.unpaid_display} />
          </>
        )}
      </div>
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fin-fact">
      <span className="fin-fact-label">{label}</span>
      <span className="fin-fact-value">{value}</span>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  לשונית "עלות האירוע"
// ════════════════════════════════════════════════════════════════════════

function CostTab({
  data,
  terms,
  onAdd,
  onEdit,
  onTemplateApplied,
}: {
  data: FinanceSummary
  terms: ReturnType<typeof activeEventTerms>
  onAdd: () => void
  onEdit: (e: Expense) => void
  onTemplateApplied: () => void
}) {
  const { cost } = data
  const grouped = useMemo(() => groupByCategory(data.expenses), [data.expenses])
  const [applying, setApplying] = useState(false)

  return (
    <>
      {cost.commitments.map((c) => (
        <CommitmentCard key={c.expense_id} commitment={c} />
      ))}

      {data.expenses.length > 0 && <NextPersonCard cost={cost} />}

      <section className="fin-section">
        <div className="fin-section-head">
          <h2 className="fin-section-title">{t.expensesTitle}</h2>
          <button type="button" className="btn-primary btn-sm" onClick={onAdd}>
            {t.addExpense}
          </button>
        </div>

        {data.expenses.length === 0 ? (
          // מסך ריק שמבקש מזוג להמציא רשימת הוצאות של אירוע הוא מסך
          // שנשאר ריק. התבנית של סוג האירוע נותנת נקודת פתיחה — בסכום
          // 0, כי VEYA יודעת **מה** משלמים ולא **כמה**.
          <div className="fin-card fin-card-empty">
            <div className="empty">
              <p className="empty-title">{t.expensesEmptyTitle}</p>
              <p className="empty-desc">{t.expensesEmptyBody}</p>
              <div className="empty-actions">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={applying}
                  onClick={() => {
                    setApplying(true)
                    applyExpenseTemplate()
                      .then(onTemplateApplied)
                      .catch(() => undefined)
                      .finally(() => setApplying(false))
                  }}
                >
                  {applying ? t.templateApplying : t.templateCta(terms.celebration)}
                </button>
                <button type="button" className="btn-ghost" onClick={onAdd}>
                  {t.addExpense}
                </button>
              </div>
              <p className="fin-hint">{t.templateHint}</p>
            </div>
          </div>
        ) : (
          <div className="fin-card">
            {grouped.map(([label, rows]) => (
              <div key={label} className="fin-group">
                <h3 className="fin-group-title">{label}</h3>
                <ul className="fin-expense-list">
                  {rows.map((e) => (
                    <ExpenseRow key={e.id} expense={e} onEdit={() => onEdit(e)} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {cost.scenarios.length > 0 && data.expenses.length > 0 && (
        <ScenariosCard data={data} />
      )}
    </>
  )
}

/**
 * ההתחייבות מול הספק — האזור החשוב ביותר במסך לפני האירוע.
 *
 * שלושה מספרים זה מול זה, כי זו בדיוק השאלה שהזוג שואל בשבועיים
 * האחרונים: על כמה התחייבנו, כמה מגיעים, ועל כמה אנחנו משלמים.
 * המשפט מתחת אומר את זה במילים, בלי סימן קריאה ובלי "שימו לב" — זו
 * עובדה חשבונאית, לא אזהרה.
 */
function CommitmentCard({ commitment: c }: { commitment: Commitment }) {
  return (
    <section className="fin-card fin-commitment">
      <h2 className="fin-card-title">
        {t.commitmentTitle} · {c.label}
      </h2>

      <div className="fin-commitment-grid">
        <Fact label={t.committedLabel} value={String(c.committed_quantity)} />
        <Fact label={t.attendingNowLabel} value={String(c.attendees)} />
        {c.unused_quantity > 0 && (
          <Fact label={t.unusedLabel} value={String(c.unused_quantity)} />
        )}
        <Fact label={t.billedLabel} value={String(c.billed_quantity)} />
        <Fact label={t.totalCostLabel} value={c.total_display} />
      </div>

      <p className="fin-commitment-note">
        {c.unused_quantity > 0
          ? t.underCommitment(c.committed_quantity, c.attendees)
          : c.over_commitment > 0
            ? t.overCommitment(c.attendees, c.over_commitment)
            : t.exactCommitment}
      </p>

      {c.min_total_applied && <p className="fin-hint">{t.minTotalApplied}</p>}
    </section>
  )
}

/**
 * "כמה מוסיף כל אדם נוסף?"
 *
 * המספר מגיע מהשרת כהפרש בין שני מצבים, ולכן הוא נכון בשתי המדרגות:
 * ₪0 כשעדיין מתחת לכמות ההתחייבות (כבר משלמים על האדם הזה), ומחיר מלא
 * מעליה. זו הנקודה שבה המסך הזה שווה משהו — מחשבון שמכפיל במחיר מנה
 * היה נותן כאן תשובה שגויה.
 */
function NextPersonCard({ cost }: { cost: FinanceSummary['cost'] }) {
  const free = cost.next_attendee_agorot === 0
  const commitment = cost.commitments[0]

  return (
    <section className="fin-card fin-next">
      <h2 className="fin-card-title">{t.nextPersonTitle}</h2>

      {free && commitment ? (
        <>
          <p className="fin-next-value">{t.nextPersonFreeTitle}</p>
          <p className="fin-hint">
            {t.nextPersonFreeBody(commitment.committed_quantity, commitment.label)}
          </p>
        </>
      ) : (
        <>
          <p className="fin-next-value">{cost.next_attendee_display}</p>
          {/* המספר לבדו לא מספיק כשיש התחייבות ברקע: "35 ₪" נראה כמו
              טעות למי שיודע שמנה עולה 320. המשפט הזה אומר למה. */}
          {commitment && commitment.unused_quantity > 0 && (
            <p className="fin-hint">
              {t.nextPersonPartialBody(commitment.committed_quantity, commitment.label)}
            </p>
          )}
          {commitment && commitment.over_commitment > 0 && (
            <p className="fin-hint">
              {t.nextPersonOverBody(commitment.committed_quantity)}
            </p>
          )}
        </>
      )}

      <p className="fin-next-intro">{t.stepsIntro}</p>
      <ul className="fin-steps">
        {cost.steps.map((s) => (
          <li key={s.guests}>
            <span className="fin-step-label">{t.stepLabel(s.guests)}</span>
            <span className="fin-step-value">{s.added_display}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ExpenseRow({ expense, onEdit }: { expense: Expense; onEdit: () => void }) {
  return (
    <li className="fin-expense">
      <button type="button" className="fin-expense-btn" onClick={onEdit}>
        <span className="fin-expense-name">
          {expense.label}
          {/* הספק, ואחריו שני המצבים. "שולם" בירוק כי זו בשורה טובה;
              "הערכה" באפור כי זו עובדה ניטרלית ולא חוסר. */}
          {expense.vendor && <span className="fin-expense-note">{expense.vendor}</span>}
          {expense.is_paid && <span className="fin-badge fin-badge-paid">{t.paidLabel}</span>}
          {expense.is_estimated && (
            <span className="fin-badge">{t.estimatedLabel}</span>
          )}
          {expense.note && <span className="fin-expense-note">{expense.note}</span>}
        </span>
        <span className="fin-expense-calc">{describeCalc(expense)}</span>
        <span className="fin-expense-total">{expense.total_display}</span>
      </button>
    </li>
  )
}

function ScenariosCard({ data }: { data: FinanceSummary }) {
  return (
    <section className="fin-card fin-scenarios">
      <h2 className="fin-card-title">{t.scenariosTitle}</h2>
      <ul className="fin-scenario-list">
        {data.cost.scenarios.map((s) => (
          <li
            key={s.attendees}
            className={`fin-scenario ${s.is_current ? 'current' : ''} ${
              s.is_commitment ? 'commitment' : ''
            }`}
          >
            <span className="fin-scenario-people">
              {t.scenarioPeople(s.attendees)}
              {/* שני התגים האלה הם מה שהופך לוח מספרים עגולים ללוח
                  שימושי: הם מסמנים איפה האירוע עומד ואיפה המחיר זז. */}
              {s.is_current && <em className="fin-tag">{t.scenarioCurrent}</em>}
              {s.is_commitment && !s.is_current && (
                <em className="fin-tag fin-tag-quiet">{t.scenarioCommitment}</em>
              )}
            </span>
            <span className="fin-scenario-total">{s.total_display}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  לשונית "ספירת מתנות"
// ════════════════════════════════════════════════════════════════════════

function CountingTab({
  counting,
  byGuest,
  countingNow,
  onStart,
  onStop,
  onSaved,
  onLoadByGuest,
  onDeleteEntry,
}: {
  counting: GiftCounting
  byGuest: GuestGiftRow[] | null
  countingNow: boolean
  onStart: () => void
  onStop: () => void
  onSaved: () => void
  onLoadByGuest: () => void
  onDeleteEntry: (e: GiftEntry) => void
}) {
  // הספירה נפתחת מיום האירוע ואילך. הנעילה **מסבירה את עצמה** ואומרת
  // מתי היא נפתחת — מסך נעול בלי הסבר הוא מסך שבור מבחינת המשתמש.
  if (!counting.counting_open) {
    return (
      <section className="fin-card fin-locked">
        <div className="empty">
          <p className="empty-title">{t.countingLockedTitle}</p>
          {counting.days_until_open !== null && (
            <p className="empty-desc">{t.countingLockedBody(counting.days_until_open)}</p>
          )}
        </div>
      </section>
    )
  }

  const { income } = counting

  return (
    <>
      <section className="fin-hero fin-hero-inner" aria-label={t.countingTotalLabel}>
        <p className="fin-hero-label">{t.countingTotalLabel}</p>
        <p className="fin-hero-value">
          {income.total_display || income.envelopes_display}
        </p>
        <div className="fin-hero-facts">
          <Fact label={t.envelopesLabel} value={income.envelopes_display} />
          {counting.credit_service_active && (
            <Fact
              label={t.creditLabel}
              // הסכום חסום ⇒ מוצג המניין ולא "0 ₪". אפס היה אומר "לא
              // התקבלו מתנות באשראי", וזו טענה אחרת לגמרי.
              value={income.credit_display || String(income.credit_count)}
            />
          )}
        </div>
        {income.total_agorot === null && <p className="fin-hint">{t.totalPartialNote}</p>}
        {income.credit_count > 0 && !counting.credit_amounts_visible && (
          <p className="fin-hint">{t.creditLockedNote}</p>
        )}
        {income.unidentified_count > 0 && (
          <p className="fin-hint fin-unidentified">
            {t.unidentifiedSummary(income.unidentified_count, income.unidentified_display)}
          </p>
        )}
      </section>

      {countingNow ? (
        <EnvelopeCounter
          startNumber={counting.next_envelope_number}
          onSaved={onSaved}
          onClose={onStop}
        />
      ) : (
        <div className="fin-counter-cta">
          <button type="button" className="btn-primary" onClick={onStart}>
            {t.startCounting}
          </button>
        </div>
      )}

      <section className="fin-section">
        <h2 className="fin-section-title">{t.giftsLogTitle}</h2>
        {counting.entries.length === 0 ? (
          <div className="fin-card fin-card-empty">
            <div className="empty">
              <p className="empty-title">{t.giftsEmptyTitle}</p>
              <p className="empty-desc">{t.giftsEmptyBody}</p>
            </div>
          </div>
        ) : (
          <div className="fin-card">
            <ul className="fin-gift-list">
              {counting.entries.map((e) => (
                <GiftRow key={`${e.source}-${e.id}`} entry={e} onDelete={onDeleteEntry} />
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="fin-section">
        <div className="fin-section-head">
          <h2 className="fin-section-title">{t.byGuestTitle}</h2>
          {byGuest === null && (
            <button type="button" className="btn-ghost btn-sm" onClick={onLoadByGuest}>
              {t.byGuestLoad}
            </button>
          )}
        </div>
        {byGuest !== null && <ByGuestList rows={byGuest} />}
      </section>
    </>
  )
}

function GiftRow({
  entry,
  onDelete,
}: {
  entry: GiftEntry
  onDelete: (e: GiftEntry) => void
}) {
  return (
    <li className="fin-gift">
      <span className="fin-gift-who">
        {/* מעטפה בלי שיוך מוצגת כ"לא מזוהה" ולא כשורה ריקה: זה מצב
            מתועד שאפשר לחזור אליו, לא נתון חסר. */}
        {entry.guest_name || <em className="fin-unknown">{t.envelopeUnknownBadge}</em>}
        {entry.shared_names.length > 0 && (
          <span className="fin-gift-shared">{t.sharedWith(entry.shared_names)}</span>
        )}
      </span>
      <span className="fin-gift-amount">{entry.amount_display || '•••'}</span>
      <span className="fin-gift-source">
        {entry.source === 'envelope'
          ? `${t.sourceEnvelope} #${entry.envelope_number}`
          : t.sourceCredit}
      </span>
      {/* מתנה באשראי אינה ניתנת למחיקה כאן — היא עסקת סליקה שנוצרה
          במסלול הציבורי, ולא רישום ידני של הזוג. */}
      {entry.source === 'envelope' && (
        <button
          type="button"
          className="link-btn fin-gift-delete"
          onClick={() => onDelete(entry)}
        >
          {strings.common.delete}
        </button>
      )}
    </li>
  )
}

/**
 * מצב המתנה לכל מוזמן.
 *
 * **ההבחנה שאסור לטשטש:** "עדיין לא נספרה" אינו "לא נתן". מוזמן בלי
 * שורת מתנה הוא מוזמן שהמעטפה שלו עוד לא הגיעה לערימה, ולא מישהו
 * שהחליט לא להעניק. המשפט מתחת לרשימה אומר את זה במפורש, כי הרשימה
 * לבדה מזמינה בדיוק את הפרשנות השגויה.
 */
function ByGuestList({ rows }: { rows: GuestGiftRow[] }) {
  const [filter, setFilter] = useState<'all' | 'counted' | 'not_counted'>('all')

  const shown = rows.filter((r) => {
    if (filter === 'all') return true
    if (filter === 'counted') return r.status !== 'not_counted'
    return r.status === 'not_counted'
  })

  return (
    <div className="fin-card">
      <div className="fin-filters">
        {(
          [
            ['all', t.filterAll],
            ['counted', t.filterCounted],
            ['not_counted', t.filterNotCounted],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`fin-filter ${filter === value ? 'active' : ''}`}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <ul className="fin-guest-list">
        {shown.map((r) => (
          <li key={r.guest_id} className="fin-guest-row">
            <span className="fin-guest-name">{r.full_name}</span>
            <span className="fin-guest-amount">{r.total_display}</span>
            <span className={`fin-guest-status fin-status-${r.status}`}>
              {t.statusLabels[r.status]}
            </span>
            {r.gift_count > 1 && (
              // כמה מתנות לאותו מוזמן מצטברות ולא דורסות זו את זו —
              // שתי מעטפות מדוד לוי הן ₪1,000, לא ₪500.
              <span className="fin-guest-count">{t.giftCountBadge(r.gift_count)}</span>
            )}
          </li>
        ))}
      </ul>

      <p className="fin-hint">{t.notCountedHint}</p>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
//  לשונית "סיכום"
// ════════════════════════════════════════════════════════════════════════

function SummaryTab({
  data,
  terms,
}: {
  data: FinanceSummary
  terms: ReturnType<typeof activeEventTerms>
}) {
  const bottom = data.bottom_line_agorot

  // הדוח המלא נטען לפי דרישה, לא עם המסך: הוא מכיל שורה לכל מוזמן
  // (מאות שורות באירוע טיפוסי), ואיש לא מסתכל עליו רוב הזמן.
  const [report, setReport] = useState<FinanceReport | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  function loadReport() {
    setLoadingReport(true)
    setReportError(null)
    getFinanceReport()
      .then(setReport)
      .catch((e) => setReportError(e instanceof Error ? e.message : t.reportError))
      .finally(() => setLoadingReport(false))
  }

  return (
    <>
      <section className="fin-card fin-summary">
        <div className="fin-summary-row">
          <span>{t.incomeLabel}</span>
          <strong>{data.income.total_display || '—'}</strong>
        </div>
        <div className="fin-summary-row">
          <span>{t.expensesLabel}</span>
          <strong>{data.cost.total_display}</strong>
        </div>

        <div className="fin-summary-bottom">
          {bottom === null ? (
            // צד ההכנסות חסום חלקית ⇒ אין תוצאה. מספר שמוצג כ"התוצאה
            // הכספית של האירוע" ומחושב מנתון חלקי הוא הטעיה, לא קירוב.
            <p className="fin-hint">{t.bottomLineLocked}</p>
          ) : (
            <>
              <span className="fin-summary-bottom-label">
                {bottom > 0 ? t.surplus : bottom < 0 ? t.deficit : t.balanced}
              </span>
              <span
                className={`fin-summary-bottom-value ${bottom < 0 ? 'negative' : ''}`}
              >
                {/* הסכום המוחלט: הסימן כבר נאמר במילים ("נשאר לכם" /
                    "חסר"), ומינוס לצידו היה אומר את אותו דבר פעמיים. */}
                {stripSign(data.bottom_line_display)}
              </span>
            </>
          )}
        </div>

        {/* השורה שמונעת את השאלה "רגע, כמה ירד לנו?". */}
        <p className="fin-hint">{t.noFeeNote}</p>
      </section>

      {/* הפער בין הגעה למתנות — שני מספרים זה לצד זה שדוח כספי רגיל
          לא מציג בכלל. */}
      <section className="fin-card">
        <h2 className="fin-card-title">{t.breakdownTitle}</h2>
        <div className="fin-hero-facts">
          <Fact label={t.fromAttendees} value={data.breakdown.from_attendees_display} />
          <Fact
            label={t.fromNonAttendees}
            value={data.breakdown.from_non_attendees_display}
          />
          {data.breakdown.unattributed_agorot > 0 && (
            <Fact
              label={t.unattributedLabel}
              value={data.breakdown.unattributed_display}
            />
          )}
          <Fact label={t.guestsCounted} value={String(data.breakdown.guests_counted)} />
          <Fact
            label={t.guestsNotCounted}
            value={String(data.breakdown.guests_not_counted)}
          />
        </div>
      </section>

      <section className="fin-card">
        <h2 className="fin-card-title">{t.rsvpTitle}</h2>
        <div className="fin-hero-facts">
          <Fact label={t.rsvpGuests} value={String(data.rsvp.total_guests)} />
          <Fact label={t.rsvpConfirmed} value={String(data.rsvp.confirmed_people)} />
          <Fact label={t.rsvpDeclined} value={String(data.rsvp.declined_guests)} />
          <Fact label={t.rsvpPending} value={String(data.rsvp.pending_guests)} />
        </div>
      </section>

      {/* ── הדוח המלא ────────────────────────────────────────────── */}
      <section className="fin-section">
        <div className="fin-section-head">
          <h2 className="fin-section-title">{t.reportTitle}</h2>
          {!report && (
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={loadReport}
              disabled={loadingReport}
            >
              {loadingReport ? t.reportLoading : t.byGuestLoad}
            </button>
          )}
        </div>
        <p className="fin-hint">{t.reportIntro}</p>

        {reportError && (
          <p className="form-error" role="alert">
            {reportError}
          </p>
        )}

        {report && (
          <>
            <div className="fin-card fin-report-card">
              <ReportTable report={report} />
            </div>
            <div className="fin-download">
              <button
                type="button"
                className="btn-primary"
                onClick={() => downloadReport(report, terms.eventNoun)}
              >
                {t.downloadReport}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => printReport(report, terms.eventNoun)}
              >
                {t.printReport}
              </button>
            </div>
          </>
        )}
      </section>
    </>
  )
}

/**
 * טבלת הדוח — **שורה אחת מלאה לכל מוזמן.**
 *
 * שתי עמודות המפתח, "סטטוס הגעה" ו"סה״כ מתנה", יושבות זו לצד זו ואינן
 * נגזרות זו מזו: מוזמן שביטל הגעה ונתן ₪1,000 מופיע בדיוק כך. זה כל
 * הרעיון של הדוח — לא לחבר מידע משלושה מסכים.
 *
 * **תא "טרם נספרה" אינו "0 ₪".** מעטפה שנספרה בסכום אפס מוצגת כ-"0 ₪";
 * מוזמן שעדיין לא נספר מוצג כ"טרם נספרה". שני מצבים שונים, שתי מחרוזות.
 *
 * בטלפון הטבלה נגללת אופקית בתוך המכל שלה (``overflow-x``) ולא שוברת את
 * העמוד — עמודות שנדחסות לרוחב מסך טלפון הופכות ל-9 מילים שבורות.
 */
function ReportTable({ report }: { report: FinanceReport }) {
  const [onlyGifts, setOnlyGifts] = useState(false)
  const rows = onlyGifts ? report.guests.filter((g) => g.gift_count > 0) : report.guests

  return (
    <>
      <div className="fin-filters">
        <button
          type="button"
          className={`fin-filter ${!onlyGifts ? 'active' : ''}`}
          onClick={() => setOnlyGifts(false)}
        >
          {t.filterAll}
        </button>
        <button
          type="button"
          className={`fin-filter ${onlyGifts ? 'active' : ''}`}
          onClick={() => setOnlyGifts(true)}
        >
          {t.filterCounted}
        </button>
      </div>

      <div className="fin-table-scroll">
        <table className="fin-table">
          <thead>
            <tr>
              <th>{t.colGuest}</th>
              <th>{t.colPhone}</th>
              <th>{t.colRsvp}</th>
              <th>{t.colInvited}</th>
              <th>{t.colAttended}</th>
              <th>{t.colCredit}</th>
              <th>{t.colEnvelope}</th>
              <th>{t.colTotal}</th>
              <th>{t.colNotes}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.guest_id}>
                <td>{g.full_name}</td>
                <td className="fin-num">{g.phone}</td>
                <td>
                  <span className={`fin-guest-status rsvp-${g.rsvp_status}`}>
                    {t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status}
                  </span>
                </td>
                <td className="fin-num">{g.party_size}</td>
                <td className="fin-num">{g.attended_count}</td>
                <td className="fin-num">{g.credit_display || '—'}</td>
                <td className="fin-num">{g.envelope_display || '—'}</td>
                <td className="fin-num fin-strong">
                  {g.status === 'not_counted' ? (
                    <span className="fin-muted">{t.cellNotCounted}</span>
                  ) : (
                    g.total_display
                  )}
                </td>
                <td className="fin-note-cell">{g.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* מעטפות בלי שיוך לא נעלמות מהדוח — אחרת הסכום הכולל לא מסתדר
          עם סכום השורות שמעליו. */}
      {report.unidentified.length > 0 && (
        <p className="fin-hint fin-unidentified">
          {t.unidentifiedSummary(
            report.income.unidentified_count,
            report.income.unidentified_display,
          )}
        </p>
      )}
    </>
  )
}

// ── עזרים ────────────────────────────────────────────────────────────

function groupByCategory(expenses: Expense[]): [string, Expense[]][] {
  const map = new Map<string, Expense[]>()
  for (const e of expenses) {
    const key = e.category_label || e.category
    const list = map.get(key)
    if (list) list.push(e)
    else map.set(key, [e])
  }
  return [...map.entries()]
}

/** "₪320 × 500" — שורה אחת שמסבירה מאיפה הסכום הגיע. */
function describeCalc(e: Expense): string {
  if (e.calc_method === 'fixed') return ''
  const price = Math.trunc(e.amount_agorot / 100).toLocaleString('he-IL')
  if (e.billed_quantity === null) return ''
  return `${price} ₪ × ${e.billed_quantity}`
}

/** מסיר מינוס מוביל מסכום מעוצב — ראו ההסבר במקום השימוש. */
function stripSign(display: string): string {
  return display.replace(/^-/, '')
}

/**
 * שורות הדוח — **מקור אחד לשלושת הפלטים**: המסך, ה-Excel וההדפסה.
 *
 * בלי הפונקציה הזו היו שלוש רשימות עמודות שצריך לזכור לעדכן יחד, ובדוח
 * כספי זה בדיוק המקום שבו קובץ הייצוא מתחיל לספר סיפור אחר מהמסך.
 *
 * **כל המספרים כאן כבר חושבו בשרת** — הפונקציה מסדרת אותם, לא מחשבת.
 */
function reportRows(report: FinanceReport): { head: string[]; body: string[][] } {
  const head = [
    t.colGuest, t.colPhone, t.colRsvp, t.colInvited, t.colAttended,
    t.colCredit, t.colEnvelope, t.colTotal, t.colNotes,
  ]
  const body = report.guests.map((g) => [
    g.full_name,
    g.phone,
    t.rsvpLabels[g.rsvp_status] ?? g.rsvp_status,
    String(g.party_size),
    String(g.attended_count),
    g.credit_display || '',
    g.envelope_display || '',
    // "טרם נספרה" ולא "0 ₪": אפס הוא טענה שאין לה כיסוי כשלא נספר כלום.
    g.status === 'not_counted' ? t.cellNotCounted : g.total_display,
    g.note,
  ])
  return { head, body }
}

/** שורות הסיכום שמתלוות לדוח בכל פלט. */
function summaryRows(report: FinanceReport): string[][] {
  const { rsvp, cost, income, breakdown } = report
  return [
    [t.rsvpTitle, ''],
    [t.rsvpGuests, String(rsvp.total_guests)],
    [t.rsvpConfirmed, String(rsvp.confirmed_people)],
    [t.rsvpDeclined, String(rsvp.declined_guests)],
    [t.rsvpPending, String(rsvp.pending_guests)],
    ['', ''],
    [t.countingTitle, ''],
    [t.envelopesLabel, income.envelopes_display],
    [t.creditLabel, income.credit_display],
    [t.incomeLabel, income.total_display],
    [t.fromAttendees, breakdown.from_attendees_display],
    [t.fromNonAttendees, breakdown.from_non_attendees_display],
    [t.guestsCounted, String(breakdown.guests_counted)],
    [t.guestsNotCounted, String(breakdown.guests_not_counted)],
    ['', ''],
    [t.expensesTitle, ''],
    ...report.expenses.map((e) => [e.label, e.total_display]),
    [t.fixedLabel, cost.fixed_display],
    [t.variableLabel, cost.variable_display],
    [t.totalCostLabel, cost.total_display],
    [t.perPersonLabel, cost.cost_per_attendee_display],
    ['', ''],
    [t.bottomLineLabel, report.bottom_line_display],
  ]
}

/**
 * ייצוא ל-Excel (CSV).
 *
 * ה-BOM בתחילת הקובץ אינו קישוט: בלעדיו Excel בעברית פותח UTF-8
 * כג'יבריש, וזה הפורמט שבו רוב הזוגות יפתחו את הקובץ הזה.
 *
 * ``sep=,`` בשורה הראשונה אומר ל-Excel במפורש מה המפריד — בלעדיו,
 * גרסאות Excel בהגדרות אזור ישראליות שמות את כל השורה בתא אחד.
 */
function downloadReport(report: FinanceReport, eventNoun: string): void {
  const { head, body } = reportRows(report)
  const rows = [head, ...body, ['', ''], ...summaryRows(report), ['', ''], [t.noFeeNote]]
  const csv = ['sep=,', ...rows.map((r) => r.map(csvCell).join(','))].join('\r\n')

  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = t.reportFileName(eventNoun)
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * גרסת הדפסה — ומכאן גם PDF, דרך "שמירה כ-PDF" של הדפדפן.
 *
 * **בלי ספריית PDF.** ספריית PDF בדפדפן שוקלת מאות קילובייטים, ורובן
 * שוברות עברית ו-RTL בדיוק במסמך שכולו עברית. חלון הדפסה עם ``dir="rtl"``
 * נותן פלט נכון בכל דפדפן, במשקל אפס, והמשתמש בוחר מדפסת או PDF באותו
 * דיאלוג.
 *
 * הטבלה נבנית מאותו ``reportRows`` כמו המסך וה-Excel — שלושה פלטים,
 * מקור אחד.
 */
function printReport(report: FinanceReport, eventNoun: string): void {
  const { head, body } = reportRows(report)
  const esc = (v: string) =>
    (v ?? '').replace(/[&<>"]/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string,
    )

  const html = `<!doctype html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>${esc(t.navTitle(eventNoun))} — ${esc(report.event_title)}</title>
<style>
  @page { size: A4 landscape; margin: 12mm; }
  body { font-family: 'Heebo', Arial, sans-serif; color: #2b2620; font-size: 11px; }
  h1 { font-size: 18px; margin: 0 0 2px; }
  .meta { color: #787064; font-size: 11px; margin-bottom: 14px; }
  h2 { font-size: 13px; margin: 18px 0 6px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border-bottom: 1px solid #e5dec9; padding: 5px 6px; text-align: right; }
  th { background: #fbf6ee; font-weight: 600; }
  /* השורות לא נשברות באמצע בין עמודים — שורת מוזמן חצויה בדוח של
     מאות שורות היא בדיוק מה שהופך אותו ללא-קריא. */
  tr { break-inside: avoid; }
  thead { display: table-header-group; }
  .num { font-variant-numeric: tabular-nums; }
  .muted { color: #787064; }
  .sum { width: auto; margin-top: 4px; }
  .sum td:last-child { font-weight: 600; }
  .note { color: #787064; font-size: 10px; margin-top: 14px; }
</style></head><body>
<h1>${esc(t.navTitle(eventNoun))} — ${esc(report.event_title)}</h1>
<div class="meta">${esc([report.venue_name, report.event_date].filter(Boolean).join(' · '))}</div>
<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead>
<tbody>${body
    .map(
      (r) =>
        `<tr>${r
          .map((c, i) => {
            const cls = i >= 3 && i <= 7 ? 'num' : ''
            const muted = c === t.cellNotCounted ? ' muted' : ''
            return `<td class="${cls}${muted}">${esc(c)}</td>`
          })
          .join('')}</tr>`,
    )
    .join('')}</tbody></table>
<h2>${esc(t.summaryTitle(eventNoun))}</h2>
<table class="sum"><tbody>${summaryRows(report)
    .map((r) => `<tr><td>${esc(r[0])}</td><td class="num">${esc(r[1] ?? '')}</td></tr>`)
    .join('')}</tbody></table>
<p class="note">${esc(t.noFeeNote)}</p>
</body></html>`

  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(html)
  win.document.close()
  // ההמתנה נותנת לדפדפן לפרוס את הטבלה לפני שדיאלוג ההדפסה נפתח;
  // בלעדיה דפדפנים מסוימים מדפיסים עמוד ריק.
  win.onload = () => win.print()
  setTimeout(() => win.print(), 400)
}

function csvCell(value: string): string {
  const text = value ?? ''
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
