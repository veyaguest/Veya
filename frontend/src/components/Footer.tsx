/**
 * פוטר משפטי קבוע — מוצג בכל מסכי האפליקציה (לא רק בדף הנחיתה), כדי שקישור
 * לתנאי שימוש/פרטיות/Cookies/נגישות יהיה זמין תמיד, לא רק לפני התחברות.
 * העמודים עצמם הם HTML סטטי שנוצר מ-legal/*.md (ראו scripts/build-legal-pages.mjs),
 * ולא חלק מה-SPA — לכן קישור רגיל (לא ניווט פנימי) שנפתח בלשונית נפרדת.
 */
export function Footer() {
  return (
    <footer className="app-footer" dir="rtl">
      <nav className="app-footer-links" aria-label="קישורים משפטיים">
        <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
          תנאי שימוש
        </a>
        <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
          מדיניות פרטיות
        </a>
        <a href="/legal/cookies.html" target="_blank" rel="noopener noreferrer">
          מדיניות Cookies
        </a>
        <a href="/legal/accessibility.html" target="_blank" rel="noopener noreferrer">
          הצהרת נגישות
        </a>
        <a href="/legal/about.html#contact" target="_blank" rel="noopener noreferrer">
          יצירת קשר
        </a>
      </nav>
      <span className="app-footer-copy">© VEYA · מערכת לניהול אירועים</span>
    </footer>
  )
}
