import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { User } from '../types'
import { adminSearch, type AdminMe, type SearchGroup, type SearchItem } from './adminApi'
import { navigate, routeHref, type AdminPageKey, type AdminRoute } from './route'

interface NavItem {
  key: AdminPageKey
  label: string
  permission: string
}

const NAV_GROUPS: { label: string | null; items: NavItem[] }[] = [
  { label: null, items: [{ key: 'home', label: 'ראשי', permission: 'dashboard.view' }] },
  {
    label: 'ניהול',
    items: [
      { key: 'people', label: 'משתמשים ואירועים', permission: 'users.view' },
      { key: 'venues', label: 'מאגר אולמות', permission: 'venues.view' },
      { key: 'rsvp', label: 'אישורי הגעה', permission: 'settings.view' },
      { key: 'calls', label: 'טלפנים', permission: 'calls.operate' },
      { key: 'postponements', label: 'בקשות דחייה', permission: 'postponements.review' },
    ],
  },
  {
    label: 'שליטה ב-VEYA',
    items: [
      { key: 'features', label: "פיצ'רים והרשאות", permission: 'settings.view' },
      { key: 'rules', label: 'כללי המערכת', permission: 'settings.view' },
    ],
  },
  {
    label: 'מסחר',
    items: [
      { key: 'plans', label: 'מסלולים ומחירים', permission: 'commerce.view' },
      { key: 'addons', label: 'תוספים', permission: 'commerce.view' },
      { key: 'fees', label: 'עמלות', permission: 'commerce.view' },
      { key: 'coupons', label: 'קופונים והטבות', permission: 'commerce.view' },
      { key: 'subscriptions', label: 'מנויים', permission: 'commerce.view' },
    ],
  },
  {
    label: 'מערכת',
    items: [
      { key: 'audit', label: 'יומן פעילות', permission: 'audit.view' },
      { key: 'settings', label: 'הגדרות Admin', permission: 'admins.manage' },
    ],
  },
]

export function navItemsFor(permissions: string[]) {
  return NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => permissions.includes(i.permission)),
  })).filter((g) => g.items.length > 0)
}

export function pageAllowed(page: AdminPageKey, permissions: string[]) {
  const item = NAV_GROUPS.flatMap((g) => g.items).find((i) => i.key === page)
  return !item || permissions.includes(item.permission)
}

export function AdminShell({
  user,
  me,
  route,
  attentionCount,
  onLogout,
  children,
}: {
  user: User
  me: AdminMe
  route: AdminRoute
  attentionCount: number
  onLogout: () => void
  children: ReactNode
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const groups = useMemo(() => navItemsFor(me.permissions), [me.permissions])

  useEffect(() => {
    setMenuOpen(false)
  }, [route.page, route.id])

  const nav = (
    <nav className="adm-nav" aria-label="ניווט ניהול">
      {groups.map((g, gi) => (
        <div key={gi} className="adm-nav-group">
          {g.label && <div className="adm-nav-label">{g.label}</div>}
          {g.items.map((item) => (
            <a
              key={item.key}
              href={routeHref(item.key)}
              className={`adm-nav-item${route.page === item.key ? ' is-active' : ''}`}
              aria-current={route.page === item.key ? 'page' : undefined}
            >
              <span>{item.label}</span>
              {item.key === 'home' && attentionCount > 0 && (
                <span className="adm-nav-badge" aria-label={`${attentionCount} דורשים תשומת לב`}>
                  {attentionCount}
                </span>
              )}
            </a>
          ))}
        </div>
      ))}
    </nav>
  )

  return (
    <div className="adm-root" dir="rtl">
      <aside className="adm-sidebar">
        <div className="adm-brand">
          <span className="adm-brand-name" dir="ltr">VEYA</span>
          <span className="adm-brand-tag">ניהול</span>
        </div>
        {nav}
        <SidebarFoot user={user} me={me} onLogout={onLogout} />
      </aside>

      {menuOpen && (
        <div className="adm-overlay" onMouseDown={(e) => e.target === e.currentTarget && setMenuOpen(false)}>
          <aside className="adm-mobile-nav" aria-label="תפריט">
            <div className="adm-brand">
              <span className="adm-brand-name" dir="ltr">VEYA</span>
              <span className="adm-brand-tag">ניהול</span>
            </div>
            {nav}
            <SidebarFoot user={user} me={me} onLogout={onLogout} />
          </aside>
        </div>
      )}

      <div className="adm-main">
        <div className="adm-topbar">
          <button
            type="button"
            className="adm-icon-btn adm-menu-btn"
            onClick={() => setMenuOpen(true)}
            aria-label="פתיחת תפריט"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <GlobalSearch canSearch={me.permissions.includes('search.use')} />
        </div>
        <main className="adm-content">{children}</main>
      </div>
    </div>
  )
}

function SidebarFoot({ user, me, onLogout }: { user: User; me: AdminMe; onLogout: () => void }) {
  return (
    <div className="adm-sidebar-foot">
      <div className="adm-me">
        <span className="adm-me-name">{user.display_name || user.email}</span>
        <span className="adm-me-role">{me.role_label}</span>
      </div>
      <button type="button" className="adm-link-btn" onClick={onLogout}>
        יציאה
      </button>
    </div>
  )
}

function targetFor(type: SearchGroup['type'], item: SearchItem): [AdminPageKey, string | null, Record<string, string>?] {
  switch (type) {
    case 'user':
      return ['people', `u${item.id}`]
    case 'event':
      return ['people', `e${item.id}`]
    case 'guest':
      return ['calls', null, { guest: String(item.id) }]
    case 'venue':
      return ['venues', String(item.id)]
    case 'audit':
      return ['audit', null, { q: item.title.slice(0, 60) }]
    case 'feature':
      return ['features', String(item.id)]
    case 'plan':
      return ['plans', String(item.id)]
  }
}

function GlobalSearch({ canSearch }: { canSearch: boolean }) {
  const [q, setQ] = useState('')
  const [groups, setGroups] = useState<SearchGroup[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  const flat = useMemo(
    () => (groups ?? []).flatMap((g) => g.items.map((item) => ({ type: g.type, item }))),
    [groups],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) {
      setGroups(null)
      return
    }
    setBusy(true)
    const t = window.setTimeout(() => {
      adminSearch(term)
        .then((r) => {
          setGroups(r.groups)
          setCursor(0)
        })
        .catch(() => setGroups([]))
        .finally(() => setBusy(false))
    }, 220)
    return () => window.clearTimeout(t)
  }, [q])

  if (!canSearch) return <div className="adm-gsearch-spacer" />

  function go(index: number) {
    const hit = flat[index]
    if (!hit) return
    const [page, id, params] = targetFor(hit.type, hit.item)
    navigate(page, id, params)
    setOpen(false)
    setQ('')
    inputRef.current?.blur()
  }

  let running = -1
  return (
    <div className="adm-gsearch" ref={boxRef}>
      <input
        ref={inputRef}
        type="search"
        className="adm-gsearch-input"
        placeholder="חיפוש משתמש, אירוע, מוזמן, אולם…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setCursor((c) => Math.min(c + 1, Math.max(flat.length - 1, 0)))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setCursor((c) => Math.max(c - 1, 0))
          } else if (e.key === 'Enter') {
            e.preventDefault()
            go(cursor)
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
        aria-label="חיפוש גלובלי"
        aria-expanded={open}
        role="combobox"
        aria-controls="adm-gsearch-results"
      />
      <kbd className="adm-kbd" aria-hidden="true">/</kbd>
      {open && q.trim().length >= 2 && (
        <div className="adm-gsearch-results" id="adm-gsearch-results" role="listbox">
          {busy && !groups && <div className="adm-gsearch-empty">מחפש…</div>}
          {groups && groups.length === 0 && <div className="adm-gsearch-empty">לא נמצאו תוצאות</div>}
          {groups?.map((g) => (
            <div key={g.type} className="adm-gsearch-group">
              <div className="adm-gsearch-group-label">{g.label}</div>
              {g.items.map((item) => {
                running += 1
                const idx = running
                return (
                  <button
                    key={`${g.type}-${item.id}`}
                    type="button"
                    role="option"
                    aria-selected={idx === cursor}
                    className={`adm-gsearch-hit${idx === cursor ? ' is-active' : ''}`}
                    onMouseEnter={() => setCursor(idx)}
                    onClick={() => go(idx)}
                  >
                    <span className="adm-gsearch-hit-title">{item.title}</span>
                    {item.subtitle && <span className="adm-gsearch-hit-sub">{item.subtitle}</span>}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
