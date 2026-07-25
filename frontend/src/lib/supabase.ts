/**
 * לקוח Supabase — משמש רק לצורך OAuth של גוגל (התחברות).
 *
 * הלקוח נוצר בעצלות (lazy): אם אחד ממשתני הסביבה חסר, מחזיר null, וכפתור
 * "התחבר עם גוגל" ב-AuthPage לא יוצג. שאר האפליקציה (התחברות עם אימייל+סיסמה)
 * עובדת בלי תלות בזה — אין דרך שהעדר Supabase ישבור משהו קיים.
 *
 * ה-anon key הוא ציבורי במכוון (זה תפקידו) — הוא מזהה את הפרויקט של Supabase
 * ומאפשר קריאות אנונימיות דרך RLS. את ה-JWT Secret הרגיש נשמור רק ב-Backend.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

let _client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient | null {
  if (_client) return _client
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null
  _client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      // מפענח את ה-hash שגוגל מחזירה אליו בסוף ה-OAuth (#access_token=...)
      // ושומר session מיידית. חובה כדי שנוכל לקרוא getSession() ב-callback.
      detectSessionInUrl: true,
      flowType: 'implicit',
    },
  })
  return _client
}

/** האם התחברות עם גוגל מוגדרת במערכת (יש env vars). לשימוש ב-UI (הצגת הכפתור). */
export function isGoogleAuthConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY)
}
