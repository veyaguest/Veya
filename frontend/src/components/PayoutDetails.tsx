import { useRef, useState } from 'react'
import {
  fetchPayoutCertificate,
  savePayoutAccount,
  submitPayoutAccount,
} from '../api'
import type { PayoutAccount } from '../types'
import { strings } from '../strings/he'
import { payoutDisplayStatus, payoutStage, type PayoutStage } from '../payoutState'
import { BankMark, BankSelect } from './BankSelect'
import './PayoutDetails.css'

const t = strings.payout

/**
 * "פרטי קבלת מתנות" — **כרטיס אחד** שמחזיק גם את מצב האימות וגם את פרטי
 * החשבון עצמם.
 *
 * למה אחד ולא שניים: קודם היו כאן באנר סטטוס *וגם* כרטיס פרטים, ושניהם
 * דיברו על אותו דבר — כולל שני כפתורים מתחרים באותו מסך. איחוד לכרטיס
 * אחד הוא מה שמייצר את הכלל שהמסך בנוי עליו:
 *
 *     **פעולה ראשית אחת בכל מצב.**
 *
 * מה שאינו הפעולה של עכשיו יורד לקישור משני שקט (``payout-secondary``),
 * ומה שאין בו פעולה כלל — פשוט אין לו כפתור.
 *
 * שלושה מצבי תצוגה: **סטטוס בלבד** (אין עדיין פרטים), **סטטוס + פרטים
 * שמורים**, ו**עריכה** (הטופס). הזוג ממלא את זה פעם אחת, ולכן ברירת
 * המחדל היא תצוגה מכווצת ולא טופס פתוח בכל כניסה למסך.
 *
 * הרכיב **מבוקר**: הוא לא טוען את החשבון בעצמו אלא מקבל אותו, כדי שהמסך
 * כולו — סטטוס, סיכום ורשימה — יעבוד על אותה תשובה אחת מהשרת.
 *
 * **הולידציה כאן היא נוחות, לא אבטחה.** אותם כללים בדיוק נאכפים בשרת
 * (``backend/app/banks.py``), והוא מקור האמת. הבדיקות בדפדפן קיימות רק
 * כדי שהזוג יראה את השגיאה לפני שהוא לוחץ שמירה.
 *
 * מה שהמסך הזה **לא** עושה: הוא לא מעביר כסף ולא מדבר עם ספק סליקה.
 */

const MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024
const ACCEPTED = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/heic']

type Errors = Partial<Record<'bank' | 'branch' | 'account' | 'certificate' | 'form', string>>

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  const kb = bytes / 1024
  // רצפה של 1KB: קובץ קטן מ-512 בייט היה מתעגל ל-"0 KB", שנקרא כמו קובץ
  // פגום. עדיף לעגל כלפי מעלה מאשר להציג אפס על קובץ שקיים.
  if (kb < 1024) return `${Math.max(1, Math.round(kb))} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

/** משאיר ספרות בלבד — כך שדות המספרים לא מקבלים תווים לא רלוונטיים כבר בהקלדה. */
function digitsOnly(value: string): string {
  return value.replace(/\D/g, '')
}

/** סיבת הדחייה הרלוונטית למצב — של VEYA או של חברת הסליקה, לא שתיהן. */
function rejectionReason(stage: PayoutStage, account: PayoutAccount | null): string | null {
  if (stage === 'rejected') return account?.rejection_reason ?? null
  if (stage === 'providerRejected') return account?.provider_rejection_reason ?? null
  return null
}

export function PayoutDetails({
  account,
  onChange,
}: {
  account: PayoutAccount | null
  /** מדווח על חשבון מעודכן — המסך כולו נשען עליו. */
  onChange: (account: PayoutAccount) => void
}) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [errors, setErrors] = useState<Errors>({})

  const [bankCode, setBankCode] = useState<number | null>(null)
  const [branch, setBranch] = useState('')
  const [accountNumber, setAccountNumber] = useState('')
  const [certificate, setCertificate] = useState<string | null>(null)
  const [certificateName, setCertificateName] = useState<string | null>(null)

  const fileRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  function startEdit() {
    setErrors({})
    setNote(null)
    // מספר החשבון לא חוזר מהשרת במלואו (במכוון), ולכן שדה החשבון מתחיל ריק
    // גם בעריכה — מי שמעדכן מקליד אותו מחדש. הבנק והסניף כן נטענים.
    setBankCode(account?.bank_code ?? null)
    setBranch(account?.branch_number ?? '')
    setAccountNumber('')
    setCertificate(null)
    setCertificateName(null)
    setEditing(true)
  }

  function pickFile(file: File | undefined) {
    if (!file) return
    setErrors((e) => ({ ...e, certificate: undefined }))
    if (!ACCEPTED.includes(file.type)) {
      setErrors((e) => ({ ...e, certificate: t.errors.certificateType }))
      return
    }
    if (file.size > MAX_CERTIFICATE_BYTES) {
      setErrors((e) => ({ ...e, certificate: t.errors.certificateSize }))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setCertificate(String(reader.result))
      setCertificateName(file.name)
    }
    reader.onerror = () => setErrors((e) => ({ ...e, certificate: t.errors.fileRead }))
    reader.readAsDataURL(file)
  }

  function validate(): Errors {
    const next: Errors = {}
    if (bankCode == null) next.bank = t.errors.bankMissing
    if (!branch) next.branch = t.errors.branchMissing
    else if (branch.length > 3 || Number(branch) === 0) next.branch = t.errors.branchLength
    if (!accountNumber) next.account = t.errors.accountMissing
    else if (accountNumber.length < 4 || accountNumber.length > 13 || Number(accountNumber) === 0) {
      next.account = t.errors.accountLength
    }
    // בעדכון של חשבון קיים אפשר להשאיר את האישור שכבר הועלה.
    if (!certificate && !account?.certificate) next.certificate = t.errors.certificateMissing
    return next
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setNote(null)
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length) {
      // מעביר מיקוד לשדה הראשון שנפסל — אחרת בטופס ארוך במובייל השגיאה
      // יכולה להיות מחוץ למסך והכפתור פשוט "לא עובד".
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
      return
    }
    setSaving(true)
    try {
      const saved = await savePayoutAccount({
        bank_code: bankCode as number,
        branch_number: branch,
        account_number: accountNumber,
        certificate,
      })
      onChange(saved)
      setEditing(false)
      setNote(t.saved)
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : t.errors.saveFailed })
    } finally {
      setSaving(false)
    }
  }

  /** הגשה לבדיקה. הכלל מי-רשאי-להגיש נאכף בשרת; כאן רק הפעולה. */
  async function submitForReview() {
    setNote(null)
    setErrors({})
    setSubmitting(true)
    try {
      onChange(await submitPayoutAccount())
      setNote(t.submitted)
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : t.submitError })
    } finally {
      setSubmitting(false)
    }
  }

  async function openCertificate() {
    // הלשונית נפתחת **מיד**, בתוך אירוע הלחיצה עצמו, ורק אחר כך מקבלת את
    // הכתובת. פתיחה אחרי ה-await הייתה מאבדת את הקשר לפעולת המשתמש, ורוב
    // הדפדפנים חוסמים אותה כחלון קופץ — כלומר הכפתור פשוט "לא היה עובד".
    const tab = window.open('', '_blank')
    try {
      const blob = await fetchPayoutCertificate()
      const url = URL.createObjectURL(blob)
      if (tab) {
        tab.location.href = url
      } else {
        // הלשונית נחסמה בכל זאת — נופלים להורדה רגילה, שאינה חלון קופץ.
        const a = document.createElement('a')
        a.href = url
        a.download = account?.certificate?.filename || 'certificate'
        a.click()
      }
      // משחררים את הכתובת הזמנית אחרי שהיעד הספיק לטעון ממנה.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      tab?.close()
      setErrors((e) => ({ ...e, form: t.errors.openFailed }))
    }
  }

  const stage = payoutStage(account)
  // מה שמוצג לזוג: ארבעה מצבים בלבד. ההבחנה בין שתי הבדיקות נשארת בשרת.
  const display = payoutDisplayStatus(stage)
  const reason = rejectionReason(stage, account)
  const configured = !!account?.configured
  // הנעילה מגיעה **מהשרת** ואינה נגזרת כאן מהסטטוס: השרת הוא שאוכף
  // אותה בפועל, וחישוב מקביל בדפדפן היה רק הזדמנות לשתי האמיתות לסטות.
  const locked = !!account?.locked
  const needsFix = display === 'fix'
  const inReview = display === 'review' && !locked

  return (
    <section className="payout-card" aria-labelledby="payout-title">
      {/* ── ראש הכרטיס: מה המצב ──────────────────────────────────────
          כותרת + תווית מצב שקטה. התווית נושאת צבע, אבל **לעולם לא לבדה**
          — לצידה תמיד יש משפט שאומר את אותו דבר במילים. */}
      <header className="payout-head">
        <h2 className="payout-title" id="payout-title">{t.title}</h2>
        <span className={`payout-pill payout-pill-${display}`}>
          {t.status.pill[display]}
        </span>
      </header>
      <p className="payout-line">{t.status.line[display]}</p>

      {reason && (
        <p className="payout-reason">
          <span className="payout-reason-label">{t.status.reasonLabel}:</span> {reason}
        </p>
      )}

      {note && <p className="payout-note" role="status">{note}</p>}
      {errors.form && !editing && <p className="payout-error" role="alert">{errors.form}</p>}

      {/* ── גוף הכרטיס: הפרטים השמורים ────────────────────────────────
          שורות על אותו משטח, בלי תיבה מקוננת. הכרטיס הזה כבר משטח אחד —
          משטח שני בתוכו רק היה מוסיף מסגרת בלי להוסיף מידע. */}
      {!editing && configured && account && (
        <dl className="payout-facts">
          <div className="payout-fact payout-fact-bank">
            <dt>{t.bankLabel}</dt>
            <dd>
              <BankMark code={account.bank_code as number} size="sm" />
              <span>{account.bank_name}</span>
            </dd>
          </div>
          <div className="payout-fact">
            <dt>{t.branchLabel}</dt>
            <dd className="payout-num">{account.branch_number}</dd>
          </div>
          <div className="payout-fact">
            <dt>{t.accountLabel}</dt>
            <dd className="payout-num" title={t.savedAccountNote}>
              {account.account_number_masked}
            </dd>
          </div>
          <div className="payout-fact">
            <dt>{t.certificateLabel}</dt>
            <dd>
              {account.certificate ? (
                <button type="button" className="payout-link" onClick={openCertificate}>
                  {t.viewFile}
                </button>
              ) : (
                <span className="payout-fact-missing">{t.certificateMissingShort}</span>
              )}
            </dd>
          </div>
        </dl>
      )}

      {/* ── רגל הכרטיס: פעולה אחת ─────────────────────────────────────
          בכל מצב יש **כפתור ראשי אחד לכל היותר**, ומה שמסביבו הוא קישור
          משני שקט. הסדר קבוע: פעולה, ואז ההסבר שמתחתיה. */}
      {!editing && (
        <div className="payout-foot">
          <div className="payout-foot-actions">
          {!configured && (
            <button type="button" className="payout-cta" onClick={startEdit}>
              {t.addCta}
            </button>
          )}

          {configured && needsFix && (
            <button type="button" className="payout-cta" onClick={startEdit}>
              {t.fixCta}
            </button>
          )}

          {/* השרת הוא שמחליט אם אפשר לשלוח (יש אישור, והסטטוס מאפשר) —
              המסך רק מציית ל-``can_submit``. */}
          {configured && !needsFix && account?.can_submit && (
            <button type="button" className="payout-cta" onClick={submitForReview}
                    disabled={submitting}>
              {submitting ? t.submitting : t.submitCta}
            </button>
          )}

          {/* עריכה: משנית כשכבר יש פרטים, כי הפעולה של "עכשיו" היא אף
              פעם לא לערוך מחדש מה שכבר מלא — **ולא קיימת כלל אחרי
              אישור.** ההסתרה כאן היא נוחות; האכיפה היא בשרת
              (``payout_service.assert_unlocked``). */}
          {configured && !needsFix && !locked && (
            <button type="button" className="payout-secondary" onClick={startEdit}>
              {t.editCta}
            </button>
          )}
          </div>

          {configured && !needsFix && account?.can_submit && (
            <p className="payout-foot-note">{t.submitHint}</p>
          )}
          {/* עריכה **לפני** אישור אינה חסומה — חסימה הייתה לוכדת זוג
              שהקליד ספרה שגויה עד שנדחה. במקום זה נאמר מראש מה יקרה. */}
          {inReview && <p className="payout-foot-note">{t.editDuringReviewNote}</p>}
          {/* ואחרי אישור מסבירים למה אין כפתור, לפני שמחפשים אותו. */}
          {locked && <p className="payout-foot-note">{t.status.lockedNote}</p>}
          {configured && !account?.certificate && !inReview && !locked && (
            <p className="payout-foot-note">{t.certificateHint}</p>
          )}
        </div>
      )}

      {editing && (
        <form className="payout-form" onSubmit={submit} noValidate ref={formRef}>
          <div className="payout-field">
            <label className="payout-label" id="payout-bank-label">{t.bankLabel}</label>
            <BankSelect
              value={bankCode}
              onChange={(code) => { setBankCode(code); setErrors((e) => ({ ...e, bank: undefined })) }}
              invalid={!!errors.bank}
              describedBy={errors.bank ? 'payout-bank-err' : undefined}
            />
            {errors.bank && <p className="payout-field-error" id="payout-bank-err" role="alert">{errors.bank}</p>}
          </div>

          <div className="payout-row">
            <div className="payout-field">
              <label className="payout-label" htmlFor="payout-branch">{t.branchLabel}</label>
              <input
                id="payout-branch"
                className={`payout-input payout-input-num${errors.branch ? ' payout-input-invalid' : ''}`}
                value={branch}
                onChange={(e) => { setBranch(digitsOnly(e.target.value).slice(0, 3)); setErrors((x) => ({ ...x, branch: undefined })) }}
                /* inputMode=numeric פותח מקלדת ספרות במובייל; type=text כדי
                   שאפסים מובילים לא ייעלמו ושלא יופיעו חצי הגדלה/הקטנה. */
                type="text"
                inputMode="numeric"
                autoComplete="off"
                maxLength={3}
                placeholder="045"
                aria-invalid={!!errors.branch}
                aria-describedby={errors.branch ? 'payout-branch-err' : 'payout-branch-hint'}
              />
              {errors.branch
                ? <p className="payout-field-error" id="payout-branch-err" role="alert">{errors.branch}</p>
                : <p className="payout-hint" id="payout-branch-hint">{t.branchHint}</p>}
            </div>

            <div className="payout-field">
              <label className="payout-label" htmlFor="payout-account">{t.accountLabel}</label>
              <input
                id="payout-account"
                className={`payout-input payout-input-num${errors.account ? ' payout-input-invalid' : ''}`}
                value={accountNumber}
                onChange={(e) => { setAccountNumber(digitsOnly(e.target.value).slice(0, 13)); setErrors((x) => ({ ...x, account: undefined })) }}
                type="text"
                inputMode="numeric"
                autoComplete="off"
                maxLength={13}
                placeholder="123456"
                aria-invalid={!!errors.account}
                aria-describedby={errors.account ? 'payout-account-err' : 'payout-account-hint'}
              />
              {errors.account
                ? <p className="payout-field-error" id="payout-account-err" role="alert">{errors.account}</p>
                : <p className="payout-hint" id="payout-account-hint">{t.accountHint}</p>}
            </div>
          </div>

          <div className="payout-field">
            <label className="payout-label" htmlFor="payout-file">{t.certificateLabel}</label>
            <p className="payout-hint payout-hint-why">{t.certificateWhy}</p>
            <input
              id="payout-file"
              ref={fileRef}
              type="file"
              className="payout-file-input"
              accept=".pdf,image/png,image/jpeg,image/webp,image/heic,application/pdf"
              onChange={(e) => pickFile(e.target.files?.[0])}
              aria-invalid={!!errors.certificate}
              aria-describedby={errors.certificate ? 'payout-file-err' : 'payout-file-hint'}
            />
            <div className="payout-file-row">
              <button type="button" className="payout-file-btn" onClick={() => fileRef.current?.click()}>
                {certificate || account?.certificate ? t.replaceFile : t.chooseFile}
              </button>
              <span className="payout-file-name">
                {certificateName
                  ? `${certificateName} · ${t.fileReady}`
                  : account?.certificate
                    ? [account.certificate.filename, formatSize(account.certificate.size)]
                        .filter(Boolean).join(' · ')
                    : ''}
              </span>
            </div>
            {errors.certificate
              ? <p className="payout-field-error" id="payout-file-err" role="alert">{errors.certificate}</p>
              : <p className="payout-hint" id="payout-file-hint">{t.certificateHint}</p>}
          </div>

          {errors.form && <p className="payout-error" role="alert">{errors.form}</p>}

          <div className="payout-actions">
            <button type="submit" className="payout-submit" disabled={saving}>
              {saving ? strings.common.saving : t.saveCta}
            </button>
            <button type="button" className="payout-cancel" onClick={() => { setEditing(false); setErrors({}) }} disabled={saving}>
              {t.cancelCta}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
