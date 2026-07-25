/**
 * לקוח Supabase + Google — משמש לזרימת ID-token flow:
 * גוגל (בפרונט) → id_token → supabase.auth.signInWithIdToken → session →
 * /auth/google/exchange בבקאנד → טוקן פנימי שלנו.
 *
 * הלקוח נוצר בעצלות (lazy): אם אחד ממשתני הסביבה חסר, מחזיר null, וכפתור
 * הגוגל ב-AuthPage לא יוצג. שאר האפליקציה (אימייל+סיסמה) עובדת בלי תלות בזה.
 *
 * שים לב: מעברנו מ-OAuth redirect flow ל-ID-token flow — לכן:
 *   - persistSession=false: אין טעם לשמור session של Supabase; ברגע שקיבלנו
 *     ממנה את הטוקן והמרנו אותו לטוקן פנימי, לא נחזור אליה עד להתחברות הבאה.
 *   - detectSessionInUrl=false: אין יותר callback עם hash — הכל בפרונט ישירות.
 *   - flowType מיותר (רלוונטי רק ל-redirect flow).
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as
  | string
  | undefined

let _client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient | null {
  if (_client) return _client
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null
  _client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  })
  return _client
}

/** האם התחברות עם גוגל מוגדרת במלואה (Supabase + Google Client ID).
 * צריך את כל השלושה — Google Client ID לפרונט לרנדר את הכפתור,
 * ו-Supabase לאימות ה-id_token. */
export function isGoogleAuthConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY && GOOGLE_CLIENT_ID)
}
