/* ═══════════════════════════════════════════════════════════════════════
   VEYA — תפריט נגישות (הגדרות תצוגה)
   ═══════════════════════════════════════════════════════════════════════

   קובץ אחד, בלי ספריות, לכל המשטחים: האפליקציה, דף המוזמן, האתר
   והדפים המשפטיים. נטען **סינכרונית ב-<head>** (לא defer): ההגדרות
   השמורות חלות על <html> לפני הציור הראשון, כדי שמי שבחר טקסט גדול
   לא יראה קודם את הדף בגודל רגיל ואז "קפיצה".

   איך פותחים: כל אלמנט עם ``data-veya-a11y-open`` (כפתור בסרגל
   האפליקציה, בפוטר, בכותרת האתר, בדף המוזמן). אין כפתור צף — הכפתורים
   משולבים במבנה של כל משטח.

   מה זה **לא**: תחליף לנגישות שבקוד (מקלדת, קורא מסך, תוויות, ניגודיות
   בסיסית). אלה קיימים בכל מקרה; כאן רק העדפות תצוגה אישיות.

   הטקסטים כאן ולא ב-strings/he.ts: הקובץ רץ גם בעמודים סטטיים שאין להם
   גישה לקוד ה-React. זה המקום היחיד שבו הם כתובים.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict'

  var KEY = 'veya-a11y'
  var DEFAULTS = { text: 0, contrast: false, links: false, font: false, motion: false }

  var T = {
    title: 'הגדרות נגישות',
    sub: 'ההגדרות נשמרות בדפדפן הזה ויחולו בכל העמודים של VEYA.',
    close: 'סגירה',
    sizeLabel: 'גודל טקסט',
    sizes: ['רגיל', 'גדול', 'גדול מאוד'],
    on: 'פעיל',
    off: 'כבוי',
    toggles: [
      { key: 'contrast', name: 'ניגודיות גבוהה', hint: 'טקסט כהה יותר וקווים ברורים יותר' },
      { key: 'links', name: 'הדגשת קישורים', hint: 'קו תחתון לכל קישור' },
      { key: 'font', name: 'גופן פשוט', hint: 'בלי גופן מעוטר ובלי כתב נטוי' },
      { key: 'motion', name: 'עצירת אנימציות', hint: 'בלי תנועה ומעברים על המסך' },
    ],
    reset: 'איפוס ההגדרות',
    statement: 'הצהרת הנגישות',
    resetDone: 'ההגדרות חזרו לברירת המחדל',
  }

  // ── שמירה וטעינה — localStorage עלול להיות חסום (גלישה פרטית) ──
  function load() {
    var s = {}
    for (var k in DEFAULTS) s[k] = DEFAULTS[k]
    try {
      var raw = JSON.parse(window.localStorage.getItem(KEY) || '{}')
      if (raw && typeof raw === 'object') {
        if (raw.text === 1 || raw.text === 2) s.text = raw.text
        for (var j = 0; j < T.toggles.length; j++) {
          var key = T.toggles[j].key
          s[key] = raw[key] === true
        }
      }
    } catch (e) {
      /* ברירת מחדל */
    }
    return s
  }
  function save(s) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(s))
    } catch (e) {
      /* לא נשמר — עדיין חל בעמוד הנוכחי */
    }
  }

  function apply(s) {
    var h = document.documentElement
    if (s.text) h.setAttribute('data-a11y-text', String(s.text))
    else h.removeAttribute('data-a11y-text')
    for (var j = 0; j < T.toggles.length; j++) {
      var key = T.toggles[j].key
      if (s[key]) h.setAttribute('data-a11y-' + key, '')
      else h.removeAttribute('data-a11y-' + key)
    }
    try {
      document.dispatchEvent(new CustomEvent('veya-a11y-change', { detail: s }))
    } catch (e) {
      /* דפדפן ישן */
    }
  }

  var state = load()
  apply(state)

  // ── אזור הכרזה לקורא מסך (משותף עם lib/announce.ts באפליקציה) ──
  function announce(text) {
    var el = document.getElementById('veya-announcer')
    if (!el) {
      el = document.createElement('div')
      el.id = 'veya-announcer'
      el.setAttribute('role', 'status')
      el.setAttribute('aria-live', 'polite')
      el.setAttribute('aria-atomic', 'true')
      el.style.cssText =
        'position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;border:0'
      document.body.appendChild(el)
    }
    el.textContent = ''
    setTimeout(function () {
      el.textContent = text
    }, 60)
  }

  // ── החלון ──
  var panel = null
  var backdrop = null
  var opener = null

  function el(tag, attrs, children) {
    var n = document.createElement(tag)
    for (var a in attrs || {}) {
      if (a === 'text') n.textContent = attrs[a]
      else n.setAttribute(a, attrs[a])
    }
    ;(children || []).forEach(function (c) {
      if (c) n.appendChild(c)
    })
    return n
  }

  function setSize(level) {
    state.text = level
    save(state)
    apply(state)
    syncPanel()
  }
  function flip(key) {
    state[key] = !state[key]
    save(state)
    apply(state)
    syncPanel()
  }
  function reset() {
    for (var k in DEFAULTS) state[k] = DEFAULTS[k]
    save(state)
    apply(state)
    syncPanel()
    announce(T.resetDone)
  }

  function syncPanel() {
    if (!panel) return
    var sizes = panel.querySelectorAll('[data-size]')
    for (var i = 0; i < sizes.length; i++) {
      sizes[i].setAttribute('aria-pressed', String(Number(sizes[i].getAttribute('data-size')) === state.text))
    }
    var toggles = panel.querySelectorAll('[data-toggle]')
    for (var j = 0; j < toggles.length; j++) {
      var on = !!state[toggles[j].getAttribute('data-toggle')]
      toggles[j].setAttribute('aria-pressed', String(on))
      toggles[j].querySelector('.va11y-state').textContent = on ? T.on : T.off
    }
  }

  function build() {
    var titleId = 'va11y-title'
    var sizeLabelId = 'va11y-size-label'

    var closeBtn = el('button', { type: 'button', class: 'va11y-close', 'aria-label': T.close })
    closeBtn.appendChild(el('span', { 'aria-hidden': 'true', text: '✕' }))
    closeBtn.addEventListener('click', close)

    var sizes = el('div', { class: 'va11y-sizes', role: 'group', 'aria-labelledby': sizeLabelId })
    var samplePx = [16, 19, 22]
    T.sizes.forEach(function (label, i) {
      var b = el('button', { type: 'button', class: 'va11y-size', 'data-size': String(i) }, [
        el('span', { class: 'va11y-size-sample', 'aria-hidden': 'true', text: 'א', style: 'font-size:' + samplePx[i] + 'px' }),
        el('span', { text: label }),
      ])
      b.addEventListener('click', function () {
        setSize(i)
      })
      sizes.appendChild(b)
    })

    var toggles = el('div', { class: 'va11y-toggles' })
    T.toggles.forEach(function (t) {
      var b = el('button', { type: 'button', class: 'va11y-toggle', 'data-toggle': t.key }, [
        el('span', { class: 'va11y-toggle-text' }, [
          el('span', { class: 'va11y-toggle-name', text: t.name }),
          el('span', { class: 'va11y-toggle-hint', text: t.hint }),
        ]),
        el('span', { class: 'va11y-toggle-end', 'aria-hidden': 'true' }, [
          el('span', { class: 'va11y-state' }),
          el('span', { class: 'va11y-switch' }),
        ]),
      ])
      b.addEventListener('click', function () {
        flip(t.key)
      })
      toggles.appendChild(b)
    })

    var resetBtn = el('button', { type: 'button', class: 'va11y-reset', text: T.reset })
    resetBtn.addEventListener('click', reset)

    panel = el(
      'div',
      {
        class: 'va11y-panel',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-labelledby': titleId,
        tabindex: '-1',
        dir: 'rtl',
        lang: 'he',
      },
      [
        el('div', { class: 'va11y-head' }, [el('h2', { class: 'va11y-title', id: titleId, text: T.title }), closeBtn]),
        el('p', { class: 'va11y-sub', text: T.sub }),
        el('span', { class: 'va11y-label', id: sizeLabelId, text: T.sizeLabel }),
        sizes,
        toggles,
        el('div', { class: 'va11y-foot' }, [
          resetBtn,
          el('a', { class: 'va11y-statement', href: '/legal/accessibility.html', target: '_blank', rel: 'noopener noreferrer', text: T.statement }),
        ]),
      ],
    )
    panel.addEventListener('keydown', onKeyDown)

    backdrop = el('div', { class: 'va11y-backdrop', 'aria-hidden': 'true' })
    backdrop.addEventListener('click', close)
  }

  function focusables() {
    return Array.prototype.slice.call(panel.querySelectorAll('button, a[href]'))
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      close()
      return
    }
    if (e.key !== 'Tab') return
    // Tab נשאר בתוך החלון
    var items = focusables()
    if (!items.length) return
    var first = items[0]
    var last = items[items.length - 1]
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  function isOpen() {
    return !!(panel && panel.parentNode)
  }

  function open(trigger) {
    if (isOpen()) return
    if (!panel) build()
    opener = trigger || document.activeElement
    syncPanel()
    document.body.appendChild(backdrop)
    document.body.appendChild(panel)
    var triggers = document.querySelectorAll('[data-veya-a11y-open]')
    for (var i = 0; i < triggers.length; i++) triggers[i].setAttribute('aria-expanded', 'true')
    // הפוקוס לחלון עצמו: קורא המסך מקריא קודם "הגדרות נגישות, חלון".
    panel.focus()
  }

  function close() {
    if (!isOpen()) return
    panel.parentNode.removeChild(panel)
    if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop)
    var triggers = document.querySelectorAll('[data-veya-a11y-open]')
    for (var i = 0; i < triggers.length; i++) triggers[i].setAttribute('aria-expanded', 'false')
    if (opener && opener.focus && document.contains(opener)) opener.focus()
    opener = null
  }

  // פתיחה מכל כפתור מסומן — גם כפתורים שנוצרים אחר כך (React).
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-veya-a11y-open]') : null
    if (!t) return
    e.preventDefault()
    if (isOpen()) close()
    else open(t)
  })

  window.VeyaA11y = {
    open: open,
    close: close,
    get: function () {
      var c = {}
      for (var k in state) c[k] = state[k]
      return c
    },
  }
})()
