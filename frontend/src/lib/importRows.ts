/**
 * לוגיקה משותפת לטבלת סקירה לפני ייבוא (הדבקת רשימה / אנשי קשר) —
 * שורת עריכה מקומית, נרמול טלפון ובדיקת בעיות לכל שורה.
 */
import { strings } from '../strings/he'
import type { GroupType, Side } from '../types'

const t = strings.guests

// שורה בתצוגה המקדימה הניתנת לעריכה — עותק עבודה מקומי שהמשתמש יכול לשנות.
export interface EditRow {
  key: number
  full_name: string
  phone: string
  side: Side
  group_type: GroupType
  party_size: number
  duplicate: boolean
  include: boolean
}

/** נרמול טלפון ישראלי בצד הלקוח — תואם ללוגיקת השרת. מחזיר null אם לא תקין. */
export function normalizePhone(raw: string): string | null {
  let d = (raw || '').replace(/\D/g, '')
  if (d.startsWith('972')) d = '0' + d.slice(3)
  if (!d.startsWith('0')) return null
  if (d.length !== 9 && d.length !== 10) return null
  return d
}

// תגי אזהרה מחושבים חי לפי הערכים הנוכחיים (כדי שיתעדכנו תוך כדי עריכה).
export function rowIssues(r: EditRow): { canImport: boolean; badges: string[] } {
  const badges: string[] = []
  const hasName = r.full_name.trim().length > 0
  const phoneOk = normalizePhone(r.phone) !== null
  if (!hasName) badges.push(t.rowIssueNoName)
  if (!r.phone.trim()) badges.push(t.rowIssueNoPhone)
  else if (!phoneOk) badges.push(t.rowIssueBadPhone)
  if (r.duplicate) badges.push(t.rowIssueDuplicate)
  return { canImport: hasName && phoneOk, badges }
}
