/**
 * רכיבי בסיס של מרכז השליטה. מעט רכיבים, בשימוש חוזר בכל המסכים — כדי
 * שכל מסך ירגיש אותו דבר: אותו מצב טעינה, אותה שגיאה, אותו אישור מסוכן.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { ModuleState } from './adminApi'

// ── טעינת נתונים ───────────────────────────────────────────────────────
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)

  const run = useCallback(() => {
    const mine = ++seq.current
    setLoading(true)
    setError(null)
    load()
      .then((d) => {
        if (mine === seq.current) setData(d)
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setError(e instanceof Error ? e.message : 'הטעינה נכשלה')
      })
      .finally(() => {
        if (mine === seq.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  return { data, error, loading, reload: run, setData }
}

// ── מצבי מסך ───────────────────────────────────────────────────────────
export function Loading({ label = 'טוען…' }: { label?: string }) {
  return (
    <div className="adm-state" role="status" aria-live="polite">
      <span className="adm-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="adm-state adm-state-error" role="alert">
      <p className="adm-state-title">לא הצלחנו לטעון</p>
      <p className="adm-state-text">{message}</p>
      {onRetry && (
        <button type="button" className="adm-btn" onClick={onRetry}>
          נסו שוב
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  text,
  action,
}: {
  title: string
  text?: string
  action?: ReactNode
}) {
  return (
    <div className="adm-state">
      <p className="adm-state-title">{title}</p>
      {text && <p className="adm-state-text">{text}</p>}
      {action}
    </div>
  )
}

// ── מבנה עמוד ──────────────────────────────────────────────────────────
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="adm-page-head">
      <div>
        <h1 className="adm-page-title">{title}</h1>
        {subtitle && <p className="adm-page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="adm-page-actions">{actions}</div>}
    </header>
  )
}

export function Tabs<K extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: { key: K; label: string; count?: number | null }[]
  active: K
  onChange: (key: K) => void
  label: string
}) {
  return (
    <div className="adm-tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          className={`adm-tab${active === t.key ? ' is-active' : ''}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          {t.count != null && <span className="adm-tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Section({
  title,
  description,
  children,
  actions,
}: {
  title: string
  description?: ReactNode
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <section className="adm-section">
      <div className="adm-section-head">
        <div>
          <h2 className="adm-section-title">{title}</h2>
          {description && <p className="adm-section-desc">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

/** שכבה מתקדמת — סגורה כברירת מחדל. */
export function Advanced({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="adm-advanced">
      <summary>{title}</summary>
      <div className="adm-advanced-body">{children}</div>
    </details>
  )
}

// ── סטטוסים ────────────────────────────────────────────────────────────
const STATE_LABELS: Record<ModuleState, string> = {
  active: 'פעיל',
  beta: 'בטא',
  off: 'כבוי',
  mock: 'הדגמה',
  issue: 'תקלה',
}

export type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

const STATE_TONE: Record<ModuleState, Tone> = {
  active: 'ok',
  beta: 'info',
  off: 'neutral',
  mock: 'warn',
  issue: 'bad',
}

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`adm-pill adm-pill-${tone}`}>{children}</span>
}

export function ModulePill({ state }: { state: ModuleState }) {
  return <StatusPill tone={STATE_TONE[state]}>{STATE_LABELS[state]}</StatusPill>
}

/** מקור הערך: ברירת מחדל מול Override — תמיד גלוי. */
export function SourceTag({ source, fallback }: { source: string; fallback?: ReactNode }) {
  const labels: Record<string, string> = {
    code: 'ברירת מחדל',
    system: 'ברירת מערכת',
    plan: 'לפי מסלול',
    user: 'לפי משתמש',
    event: 'Override לאירוע',
  }
  const isOverride = source === 'event' || source === 'user' || source === 'plan'
  return (
    <span className={`adm-source${isOverride ? ' is-override' : ''}`}>
      {labels[source] ?? source}
      {fallback != null && <span className="adm-source-fallback"> · ברירת המערכת: {fallback}</span>}
    </span>
  )
}

// ── Drawer ─────────────────────────────────────────────────────────────
export function Drawer({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide = false,
}: {
  open: boolean
  title: string
  subtitle?: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const titleId = useId()
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="adm-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside
        className={`adm-drawer${wide ? ' is-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="adm-drawer-head">
          <div>
            <h2 id={titleId} className="adm-drawer-title">{title}</h2>
            {subtitle && <div className="adm-drawer-sub">{subtitle}</div>}
          </div>
          <button type="button" className="adm-icon-btn" onClick={onClose} aria-label="סגירה">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </header>
        <div className="adm-drawer-body">{children}</div>
        {footer && <footer className="adm-drawer-foot">{footer}</footer>}
      </aside>
    </div>
  )
}

// ── אישור פעולה רגישה ──────────────────────────────────────────────────
export function ConfirmAction({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  typeToConfirm,
  requireReason = false,
  busy = false,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  body: ReactNode
  confirmLabel: string
  danger?: boolean
  /** טקסט שחייבים להקליד כדי לאשר (לפעולות הרסניות). */
  typeToConfirm?: string
  requireReason?: boolean
  busy?: boolean
  error?: string | null
  onConfirm: (reason: string) => void
  onCancel: () => void
}) {
  const [typed, setTyped] = useState('')
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) {
      setTyped('')
      setReason('')
    }
  }, [open])
  if (!open) return null
  const typedOk = !typeToConfirm || typed.trim() === typeToConfirm
  const reasonOk = !requireReason || reason.trim().length >= 3
  return (
    <div className="adm-overlay is-center" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div className="adm-dialog" role="alertdialog" aria-modal="true" aria-label={title}>
        <h2 className="adm-dialog-title">{title}</h2>
        <div className="adm-dialog-body">{body}</div>
        {requireReason && (
          <label className="adm-formfield">
            <span className="adm-label">סיבה (נשמרת ביומן)</span>
            <textarea
              className="adm-input"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        )}
        {typeToConfirm && (
          <label className="adm-formfield">
            <span className="adm-label">
              להמשך, הקלידו <strong className="adm-mono">{typeToConfirm}</strong>
            </span>
            <input
              className="adm-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </label>
        )}
        {error && <p className="adm-inline-error" role="alert">{error}</p>}
        <div className="adm-dialog-actions">
          <button type="button" className="adm-btn" onClick={onCancel} disabled={busy}>
            ביטול
          </button>
          <button
            type="button"
            className={`adm-btn ${danger ? 'adm-btn-danger' : 'adm-btn-primary'}`}
            disabled={busy || !typedOk || !reasonOk}
            onClick={() => onConfirm(reason.trim())}
          >
            {busy ? 'מבצע…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── הודעות הצלחה ───────────────────────────────────────────────────────
type ToastMsg = { id: number; text: string; tone: 'ok' | 'bad' }
const ToastContext = createContext<(text: string, tone?: 'ok' | 'bad') => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMsg[]>([])
  const push = useCallback((text: string, tone: 'ok' | 'bad' = 'ok') => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, text, tone }])
    window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 3800)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="adm-toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`adm-toast adm-toast-${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)

// ── הרשאות ב-UI ────────────────────────────────────────────────────────
export const PermissionContext = createContext<string[]>([])
export function useCan() {
  const perms = useContext(PermissionContext)
  return useCallback((p: string) => perms.includes(p), [perms])
}

// ── פורמט ──────────────────────────────────────────────────────────────
export function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = iso.slice(0, 10).split('-')
  return d.length === 3 ? `${d[2]}.${d[1]}.${d[0]}` : iso
}

/** זמן מהשרת (UTC נאיבי) → שעון ישראל. */
export function fmtDateTime(iso?: string | null): string {
  if (!iso) return '—'
  const withZone = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`
  const d = new Date(withZone)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('he-IL', {
    timeZone: 'Asia/Jerusalem',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(d)
    .replace(/\//g, '.')
    .replace(',', '')
}

export function fmtNumber(n: number | null | undefined): string {
  return n == null ? '—' : new Intl.NumberFormat('he-IL').format(n)
}
