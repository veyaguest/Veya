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
        if (req.url && /^\/app(\/|$|\?)/.test(req.url) && !req.url.startsWith('/app.html')) {
          req.url = '/app.html'
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), devAppRewrite()],
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        app: 'app.html',
      },
    },
  },
})
