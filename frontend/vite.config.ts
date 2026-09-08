import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// שני עמודי כניסה:
//  - index.html  → דף הנחיתה השיווקי הסטטי (ציבורי, לאינדוקס בגוגל)
//  - app.html    → מעטפת אפליקציית ה-React (פרטית, noindex) — מוגשת תחת /app
// בייצור (Vercel) יש rewrite מפורש ("/app/(.*)" → "/app.html", ראו vercel.json)
// שגורם לנתיבים מקוננים כמו /app/verify-email או /app/reset-password להגיש
// את app.html. שרת הפיתוח של Vite לא מכיר את vercel.json כלל — בלעדיו כל
// נתיב מקונן תחת /app נופל ל-SPA fallback הרגיל (index.html, דף הנחיתה),
// ולא לאפליקציה. הפלאגין הקטן הזה משחזר את אותו rewrite גם בפיתוח מקומי.
function devAppRewrite(): Plugin {
  return {
    name: 'veya-dev-app-rewrite',
    configureServer(server) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      server.middlewares.use((req: any, _res: any, next: () => void) => {
        // /confirm/{token} הוא עמוד המוזמן (Guest Hub) — גם הוא נטען מתוך
        // app.html, וגם לו יש rewrite ב-vercel.json. בלי השורה הזו הוא היה
        // נופל בפיתוח לדף הנחיתה, ואי אפשר היה לבדוק אותו מקומית בכלל.
        if (req.url && /^\/(app|confirm)(\/|$|\?)/.test(req.url) && !req.url.startsWith('/app.html')) {
          req.url = '/app.html'
        }
        next()
      })
    },
  }
}

// עמודי האתר הסטטיים (/guides/…, /calculators/…, /features/…, /events/…)
// יושבים ב-public/ כתיקיות עם index.html. Vercel מגיש תיקייה כזו אוטומטית
// בכתובת עם / בסוף; שרת הפיתוח של Vite לא — הוא נופל ל-SPA fallback ומגיש
// את דף הבית, כך שאי אפשר היה לבדוק אף עמוד פנימי מקומית. הפלאגין הזה
// משחזר בפיתוח את התנהגות הייצור.
function devStaticIndexRewrite(): Plugin {
  return {
    name: 'veya-dev-static-index',
    configureServer(server) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      server.middlewares.use((req: any, _res: any, next: () => void) => {
        if (!req.url) return next()
        const [pathname, query = ''] = req.url.split('?')
        if (/^\/(guides|calculators|features|events)(\/|$)/.test(pathname) && !pathname.endsWith('.html')) {
          const clean = pathname.replace(/\/$/, '')
          req.url = `${clean}/index.html${query ? '?' + query : ''}`
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), devAppRewrite(), devStaticIndexRewrite()],
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        app: 'app.html',
      },
    },
  },
})
