import { useEffect, useRef, useState } from 'react'
import { fetchPayoutCertificate, getPayoutAccount, savePayoutAccount } from '../api'
import type { PayoutAccount } from '../types'
import { strings } from '../strings/he'
import { BankMark, BankSelect } from './BankSelect'
import './PayoutDetails.css'

const t = strings.payout

/**
 * "פרטי קבלת מתנות" — חשבון הבנק של בעלי האירוע.
 *
 * שני מצבים: **תצוגה** (מה שמור, מספר חשבון מוסתר) ו**עריכה** (הטופס).
 * הזוג ממלא את זה פעם אחת, ולכן ברירת המחדל היא תצוגה מכווצת ולא טופס
 * פתוח שתופס חצי מסך בכל כניסה למתנות.
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

/** "24.08.26" — אותו טיפול ב-UTC נאיבי כמו בשאר המסכים. */
function formatDate(iso: string | null): string {
  if (!iso) return ''
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (isNaN(d.getTime())) return ''
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getFullYear()).slice(-2)}`
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  const kb = bytes / 1024
  return kb < 1024 ? `${Math.round(kb)} KB` : `${(kb / 1024).toFixed(1)} MB`
}

/** משאיר ספרות בלבד — כך שדות המספרים לא מקבלים תווים לא רלוונטיים כבר בהקלדה. */
function digitsOnly(value: string): string {
  return value.replace(/\D/g, '')
}

export function PayoutDetails() {
  const [account, setAccount] = useState<PayoutAccount | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [errors, setErrors] = useState<Errors>({})

  const [bankCode, setBankCode] = useState<number | null>(null)
  const [branch, setBranch] = useState('')
  const [accountNumber, setAccountNumber] = useState('')
  const [certificate, setCertificate] = useState<string | null>(null)
  const [certificateName, setCertificateName] = useState<string | null>(null)

  const fileRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    let alive = true
    getPayoutAccount()
      .then((d) => alive && setAccount(d))
      .catch(() => alive && setErrors({ form: t.errors.loadFailed }))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

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
      setAccount(saved)
      setEditing(false)
      setNote(t.saved)
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : t.errors.saveFailed })
    } finally {
      setSaving(false)
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

  if (loading) return <div className="payout-state">{strings.common.loading}</div>

  return (
    <section className="payout-card" aria-labelledby="payout-title">
      <header className="payout-head">
        <div>
          <h2 className="payout-title" id="payout-title">{t.title}</h2>
          <p className="payout-subtitle">{t.subtitle}</p>
        </div>
        {!editing && (
          <button type="button" className="payout-action" onClick={startEdit}>
            {account?.configured ? t.editCta : t.addCta}
          </button>
        )}
      </header>

      {note && <p className="payout-note" role="status">{note}</p>}
      {errors.form && !editing && <p className="payout-error" role="alert">{errors.form}</p>}

      {!editing && !account?.configured && (
        <div className="payout-empty">
          <p className="payout-empty-title">{t.emptyTitle}</p>
          <p>{t.emptyBody}</p>
        </div>
      )}

      {!editing && account?.configured && (
        <dl className="payout-summary">
          <div className="payout-summary-bank">
            <dt>{t.bankLabel}</dt>
            <dd>
              <BankMark code={account.bank_code as number} size="sm" />
              <span>{account.bank_name}</span>
            </dd>
          </div>
          <div>
            <dt>{t.branchLabel}</dt>
            <dd className="payout-num">{account.branch_number}</dd>
          </div>
          <div>
            <dt>{t.accountLabel}</dt>
            <dd className="payout-num" title={t.savedAccountNote}>{account.account_number_masked}</dd>
          </div>
          <div className="payout-summary-file">
            <dt>{t.certificateLabel}</dt>
            <dd>
              {account.certificate ? (
                <button type="button" className="payout-link" onClick={openCertificate}>
                  {t.viewFile}
                </button>
              ) : '—'}
            </dd>
          </div>
          {account.updated_at && (
            <p className="payout-updated">{t.updatedAt(formatDate(account.updated_at))}</p>
          )}
        </dl>
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
                    ? `${account.certificate.filename ?? ''} ${formatSize(account.certificate.size)}`.trim()
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
