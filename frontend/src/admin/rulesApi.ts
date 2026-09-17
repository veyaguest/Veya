import { adminHttp } from './adminApi'

const { getJson, sendJson } = adminHttp

export type SettingValue = number | boolean | string

export interface SettingRow {
  key: string
  domain: string
  label: string
  help: string
  type: 'int' | 'bool' | 'choice' | 'text'
  min: number | null
  max: number | null
  choices: string[]
  unit: string
  live: boolean
  critical: boolean
  readonly_reason: string
  event_override: boolean
  default: SettingValue
  value: SettingValue
  source: 'code' | 'system' | 'event' | 'env'
  system_value: SettingValue
}

export interface RulesResponse {
  domains: Record<string, string>
  settings: SettingRow[]
  can_edit: boolean
  can_edit_critical: boolean
}

export interface EventOverridesResponse {
  event_id: number
  track_active: boolean
  settings: SettingRow[]
  features: { key: string; label: string; enabled: boolean; source: string; controllable: boolean }[]
  can_edit: boolean
}

export interface FeatureRuleRow {
  id: number
  scope_type: 'event' | 'user'
  scope_id: number
  scope_label: string
  enabled: boolean
  note: string
}

export interface FeatureRow {
  key: string
  label: string
  description: string
  builtin: boolean
  controllable: boolean
  reason: string
  rule_scopes: ('event' | 'user')[]
  status: 'active' | 'beta' | 'off'
  status_label: string
  source: 'admin' | 'env' | 'default'
  rules: FeatureRuleRow[]
  consumed: boolean
}

export const rules = {
  get: () => getJson<RulesResponse>('/admin/rules'),
  save: (changes: Record<string, SettingValue>, reason: string) =>
    sendJson<{ updated: number; settings: SettingRow[] }>('/admin/rules', 'PUT', { changes, reason }),
  event: (eventId: number) => getJson<EventOverridesResponse>(`/admin/rules/events/${eventId}`),
  saveEvent: (eventId: number, changes: Record<string, SettingValue | null>, reason: string) =>
    sendJson<EventOverridesResponse>(`/admin/rules/events/${eventId}`, 'PUT', { changes, reason }),
  features: () => getJson<{ features: FeatureRow[]; can_edit: boolean }>('/admin/features'),
  setStatus: (key: string, status: FeatureRow['status'], reason: string) =>
    sendJson<{ features: FeatureRow[] }>(`/admin/features/${key}`, 'PUT', { status, reason }),
  createFeature: (data: { key: string; label: string; description: string; status: FeatureRow['status'] }) =>
    sendJson<{ features: FeatureRow[] }>('/admin/features', 'POST', data),
  addRule: (key: string, data: { scope_type: 'event' | 'user'; scope_id: number; enabled: boolean; note: string }) =>
    sendJson<{ features: FeatureRow[] }>(`/admin/features/${key}/rules`, 'POST', data),
  deleteRule: (key: string, ruleId: number) =>
    sendJson<{ features: FeatureRow[] }>(`/admin/features/${key}/rules/${ruleId}`, 'DELETE'),
}

export function showValue(s: SettingRow, v: SettingValue): string {
  if (s.type === 'bool') return v ? 'כן' : 'לא'
  return `${v}${s.unit ? ` ${s.unit}` : ''}`
}
