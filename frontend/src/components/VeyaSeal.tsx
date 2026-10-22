/**
 * חותם VEYA — קובץ המותג הרשמי ``/logo_nobg.png`` (טבעת כפולה, יהלום בשעה 12, V).
 * מחליף את השחזור הקודם ב-CSS (טבעות ב-::before/::after + V בגופן), כדי שבכל
 * מקום יופיע אותו לוגו בדיוק. הגודל נקבע ע"י העוטף (``.auth-monogram``):
 * בקובץ הטבעת תופסת 75% מהרוחב, ולכן התמונה מוגדלת ל-133.7% כדי שהטבעת
 * תמלא את העוטף כמו קודם (ראו ``.auth-monogram > .veya-seal`` ב-App.css).
 */
export function VeyaSeal() {
  return <img className="veya-seal" src="/logo_nobg.png" alt="" aria-hidden="true" draggable={false} />
}
