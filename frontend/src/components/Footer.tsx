import { strings } from '../strings/he'

/**
 * פוטר משפטי קבוע — מוצג בכל מסכי האפליקציה (לא רק בדף הנחיתה), כדי שקישור
 * לתנאי שימוש/פרטיות/Cookies/נגישות יהיה זמין תמיד, לא רק לפני התחברות.
 * העמודים עצמם הם HTML סטטי שנוצר מ-legal/*.md (ראו scripts/build-legal-pages.mjs),
 * ולא חלק מה-SPA — לכן קישור רגיל (לא ניווט פנימי) שנפתח בלשונית נפרדת.
 */
export function Footer() {
  return (
    <footer className="app-footer" dir="rtl">
      <nav className="app-footer-links" aria-label={strings.legal.footerLinksLabel}>
        <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
          {strings.legal.footerTerms}
        </a>
        <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
          {strings.legal.footerPrivacy}
        </a>
        <a href="/legal/cookies.html" target="_blank" rel="noopener noreferrer">
          {strings.legal.footerCookies}
        </a>
        <a href="/legal/accessibility.html" target="_blank" rel="noopener noreferrer">
          {strings.legal.footerAccessibility}
        </a>
        <a href="/legal/about.html#contact" target="_blank" rel="noopener noreferrer">
          {strings.legal.footerContact}
        </a>
      </nav>
      <span className="app-footer-copy">{strings.legal.footerCopy}</span>
    </footer>
  )
}
