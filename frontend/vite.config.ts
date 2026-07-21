import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// שני עמודי כניסה:
//  - index.html  → דף הנחיתה השיווקי הסטטי (ציבורי, לאינדוקס בגוגל)
//  - app.html    → מעטפת אפליקציית ה-React (פרטית, noindex) — מוגשת תחת /app
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        app: 'app.html',
      },
    },
  },
})
