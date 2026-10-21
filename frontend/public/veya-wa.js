/*
 * כפתור WhatsApp צף — אתר השיווק בלבד (דף הבית ודפי האתר הסטטיים).
 * לא בדף המוזמן (/confirm) ולא בתוך המערכת: שם WhatsApp הוא ערוץ של הזוג
 * מול המוזמנים, לא פנייה ל-VEYA.
 *
 * מיקום (החלטת הבעלים 2026-10-19): מעל כפתור הנגישות, באותה פינה (צד הסוף,
 * שמאל ב-RTL) — הצד הנגדי ל-CTA הצף של דף הבית. עולה מעל באנר ה-Cookies כמו
 * כפתור הנגישות. הקישור פותח צ'אט עם מספר ה-WhatsApp של VEYA; הפנייה נכנסת
 * לתיבת השירות באדמין (תשובה אוטומטית בשעות הפעילות).
 */
;(function () {
  'use strict'

  var NUMBER = '972552909070'
  var TEXT = 'היי, אשמח לשמוע על VEYA'

  var css =
    '.vwa-fab{position:fixed;z-index:90;inset-inline-end:clamp(12px,2vw,24px);' +
    'bottom:calc(clamp(12px,2vw,24px) + 50px + env(safe-area-inset-bottom,0px) + var(--vwa-lift,0px));' +
    'display:inline-flex;align-items:center;gap:6px;min-height:40px;padding:0 14px 0 12px;' +
    'border:1px solid rgba(228,201,107,.4);border-radius:999px;background:rgba(23,19,13,.9);color:#f5efe2;' +
    "font-family:'Heebo','Assistant',system-ui,-apple-system,sans-serif;font-size:13.5px;font-weight:600;" +
    'line-height:1;text-decoration:none;box-shadow:0 6px 18px -8px rgba(23,19,13,.55)}' +
    '.vwa-fab svg{color:#25d366;flex:none}' +
    '@media (hover:hover){.vwa-fab:hover{border-color:#e4c96b;background:#17130d}}' +
    '.vwa-fab:focus-visible{outline:2px solid #e4c96b!important;outline-offset:3px}' +
    '@media (max-width:600px){.vwa-fab{width:44px;height:44px;min-height:44px;padding:0;justify-content:center;' +
    'bottom:calc(clamp(12px,2vw,24px) + 54px + env(safe-area-inset-bottom,0px) + var(--vwa-lift,0px))}' +
    '.vwa-label{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}}' +
    '@media print{.vwa-fab{display:none}}'

  function mount() {
    if (document.querySelector('.vwa-fab')) return
    var style = document.createElement('style')
    style.textContent = css
    document.head.appendChild(style)

    var a = document.createElement('a')
    a.className = 'vwa-fab'
    a.href = 'https://wa.me/' + NUMBER + '?text=' + encodeURIComponent(TEXT)
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    a.setAttribute('aria-label', 'כתבו לנו ב-WhatsApp (נפתח בחלון חדש)')
    a.innerHTML =
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">' +
      '<path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.8 11.9 11.9 0 0 0 4.6 4c1.7.7 2.4.8 3.2.7a2.8 2.8 0 0 0 1.8-1.3 2.3 2.3 0 0 0 .2-1.3c-.1-.1-.2-.2-.5-.3Z"/></svg>' +
      '<span class="vwa-label">WhatsApp</span>'
    document.body.appendChild(a)

    // באנר ה-Cookies בתחתית המסך — הכפתור עולה מעליו (כמו כפתור הנגישות).
    function lift() {
      var b = document.querySelector('.cookie-banner-static, .cookie-banner')
      var h = b ? b.getBoundingClientRect().height : 0
      a.style.setProperty('--vwa-lift', (h > 0 ? Math.ceil(h) : 0) + 'px')
    }
    var watched = null
    function watchBanner() {
      var b = document.querySelector('.cookie-banner-static, .cookie-banner')
      if (b && b !== watched && window.MutationObserver) {
        watched = b
        new MutationObserver(lift).observe(b, { attributes: true, attributeFilter: ['style', 'hidden', 'class'] })
      }
      lift()
    }
    watchBanner()
    window.addEventListener('resize', lift)
    if (window.MutationObserver) new MutationObserver(watchBanner).observe(document.body, { childList: true })
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount)
  else mount()
})()
