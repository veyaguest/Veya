/*
 * Service Worker של VEYA — מינימלי בכוונה.
 * ============================================================================
 *
 * מה הוא עושה, וזה הכל:
 *   1. שומר עמוד אחד — /offline.html — ומציג אותו כשאין חיבור, במקום
 *      מסך השגיאה האפור של הדפדפן.
 *   2. עצם קיומו (עם fetch handler) הוא מה שגורם ל-Chrome באנדרואיד
 *      ובדסקטופ להציע "התקנה" בכלל. באייפון הוא לא נדרש להתקנה —
 *      "הוספה למסך הבית" עובדת גם בלעדיו.
 *
 * מה הוא **לא** עושה, ולמה:
 *   • לא שומר את מעטפת האפליקציה (app.html / JS / CSS). בכוונה: אילו
 *     שמר, משתמש היה עלול להיתקע אחרי דיפלוי על גרסה ישנה שמפנה
 *     לקבצים שכבר לא קיימים — כלומר מסך לבן. הקבצים של Vite ממילא
 *     מקבלים שם עם hash ונשמרים ב-HTTP cache של הדפדפן, שזה מהיר
 *     בדיוק באותה מידה ובלי הסיכון.
 *   • לא נוגע ב-API ולא בנתוני מוזמנים. הבקאנד של VEYA יושב בדומיין
 *     אחר (Render), ו-Service Worker כאן מסנן במפורש כל בקשה שאינה
 *     מאותו origin. אין שום מצב שבו תשובת שרת נשמרת, ולכן אין שום
 *     מצב שבו משתמש אחד רואה מידע של משתמש אחר.
 *   • לא נוגע בטוקן ההתחברות. הוא חי ב-localStorage, ש-Service Worker
 *     לא יכול לגשת אליו כלל.
 *
 * העלאת המספר ב-CACHE גורמת לניקוי הגרסה הקודמת בהתקנה הבאה.
 */

const CACHE = 'veya-shell-v1'
const OFFLINE_URL = '/offline.html'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add(new Request(OFFLINE_URL, { cache: 'reload' })))
      // נכשל להוריד את עמוד ה-offline? מתקינים בכל זאת — לכל היותר
      // המשתמש יראה את מסך השגיאה הרגיל של הדפדפן.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // ניווט מוקדם (navigation preload): הדפדפן מתחיל להביא את העמוד
      // במקביל להתעוררות ה-Service Worker, כך שהוא לא מוסיף השהיה.
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable().catch(() => undefined)
      }
      const names = await caches.keys()
      await Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
      await self.clients.claim()
    })(),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request

  // ---- כל מה שאיננו ניווט עובר כמו שהוא, בלי שום התערבות ----
  // קבצי JS/CSS/תמונות → ה-HTTP cache הרגיל של הדפדפן.
  // בקשות ל-API → דומיין אחר, לא נוגעים בהן בכלל.
  if (request.method !== 'GET') return
  if (request.mode !== 'navigate') return
  if (new URL(request.url).origin !== self.location.origin) return

  // ---- ניווט: קודם כל הרשת, תמיד ----
  // כך המשתמש תמיד מקבל את הגרסה העדכנית של VEYA. רק כשאין חיבור
  // בכלל — מציגים את עמוד ה-offline השמור.
  event.respondWith(
    (async () => {
      try {
        const preloaded = await event.preloadResponse
        if (preloaded) return preloaded
        return await fetch(request)
      } catch {
        const cached = await caches.match(OFFLINE_URL)
        if (cached) return cached
        throw new Error('offline')
      }
    })(),
  )
})
