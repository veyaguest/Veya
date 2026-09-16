/**
 * ניווט האדמין — hash בלבד (`#/admin/<page>/<id>?a=b`).
 *
 * למה hash ולא ספריית router: האפליקציה כולה בלי router, והאדמין הוא עולם
 * סגור. hash נותן קישור שאפשר להעתיק ("תסתכל על האירוע הזה") וכפתור "אחורה"
 * שעובד — בלי תלות חדשה ובלי לגעת בניתוב של בעלי האירועים.
 */
import { useEffect, useState } from 'react'

export type AdminPageKey =
  | 'home'
  | 'people'
  | 'venues'
  | 'rsvp'
  | 'calls'
  | 'postponements'
  | 'features'
  | 'rules'
  | 'plans'
  | 'addons'
  | 'fees'
  | 'coupons'
  | 'subscriptions'
  | 'audit'
  | 'settings'

export interface AdminRoute {
  page: AdminPageKey
  id: string | null
  params: URLSearchParams
}

const PAGES: AdminPageKey[] = [
  'home', 'people', 'venues', 'rsvp', 'calls', 'postponements', 'features', 'rules',
  'plans', 'addons', 'fees', 'coupons', 'subscriptions', 'audit', 'settings',
]

export function parseRoute(hash: string = window.location.hash): AdminRoute {
  const raw = hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  const parts = path.split('/').filter(Boolean)
  const pageRaw = parts[0] === 'admin' ? parts[1] : parts[0]
  const idRaw = parts[0] === 'admin' ? parts[2] : parts[1]
  const page = (PAGES as string[]).includes(pageRaw ?? '') ? (pageRaw as AdminPageKey) : 'home'
  return { page, id: idRaw ? decodeURIComponent(idRaw) : null, params: new URLSearchParams(query) }
}

export function routeHref(
  page: AdminPageKey,
  id?: string | number | null,
  params?: Record<string, string | number | null | undefined>,
): string {
  let href = `#/admin/${page}`
  if (id !== undefined && id !== null && id !== '') href += `/${encodeURIComponent(String(id))}`
  if (params) {
    const p = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
    }
    const s = p.toString()
    if (s) href += `?${s}`
  }
  return href
}

export function navigate(
  page: AdminPageKey,
  id?: string | number | null,
  params?: Record<string, string | number | null | undefined>,
  { replace = false }: { replace?: boolean } = {},
) {
  const href = routeHref(page, id, params)
  if (replace) {
    window.history.replaceState(null, '', href)
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  } else {
    window.location.hash = href.slice(1)
  }
}

export function useAdminRoute(): AdminRoute {
  const [route, setRoute] = useState<AdminRoute>(() => parseRoute())
  useEffect(() => {
    const onChange = () => setRoute(parseRoute())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
