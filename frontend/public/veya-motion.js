/* ═══════════════════════════════════════════════════════════════════════
   VEYA — שפת התנועה
   ═══════════════════════════════════════════════════════════════════════

   קובץ אחד, בלי ספריות, ~4KB. הכול על transform/opacity בלבד — שום
   אנימציה כאן לא מפעילה חישוב layout מחדש.

   שלושה תפקידים:
     1. חשיפה בגלילה עם stagger      (`.v-reveal`, `[data-v-stagger]`)
     2. מונה מספרים                  (`[data-count-to]`)
     3. שלוש הסצנות של סיפור המוצר   (`[data-scene]`)

   ## כיבוד prefers-reduced-motion

   כשהמשתמש ביקש תנועה מופחתת, הקובץ **לא מריץ שום אנימציה**: הוא מסמן
   הכול כגלוי ומציב את המספרים על ערך היעד. אין מצב שבו מידע קיים רק
   בתוך אנימציה — זה גם כלל נגישות וגם הסיבה שכל סצנה מקבלת ערך סופי
   ב-HTML עצמו, לא רק ב-JS.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict'

  var reduced =
    !window.matchMedia || window.matchMedia('(prefers-reduced-motion: reduce)').matches
  var supported = 'IntersectionObserver' in window

  // ── עזר: פורמט מספר עברי (מפריד אלפים, בלי לוקאל שמשתנה בין דפדפנים) ──
  function fmt(n, decimals) {
    var v = decimals ? n.toFixed(decimals) : String(Math.round(n))
    var parts = v.split('.')
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    return parts.join('.')
  }

  // ══ 1. חשיפה בגלילה ═════════════════════════════════════════════════
  function revealAll(root) {
    var els = (root || document).querySelectorAll('.v-reveal:not(.is-in)')
    for (var i = 0; i < els.length; i++) els[i].classList.add('is-in')
  }

  function initReveal() {
    // stagger מוגדר בהורה, כדי שלא נצטרך לכתוב delay על כל ילד ביד
    var groups = document.querySelectorAll('[data-v-stagger]')
    for (var g = 0; g < groups.length; g++) {
      var step = parseInt(groups[g].getAttribute('data-v-stagger'), 10) || 70
      var kids = groups[g].querySelectorAll('.v-reveal')
      for (var k = 0; k < kids.length; k++) {
        // תקרה של 6 שלבים: מעבר לזה ההמתנה מורגשת כאיטיות, לא כקצב
        kids[k].style.setProperty('--v-delay', Math.min(k, 6) * step + 'ms')
      }
    }

    if (reduced || !supported) { revealAll(); return }

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return
          e.target.classList.add('is-in')
          io.unobserve(e.target)
        })
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' }
    )
    var els = document.querySelectorAll('.v-reveal')
    for (var i = 0; i < els.length; i++) io.observe(els[i])

    // רשת ביטחון: אלמנט שכבר בתוך המסך בטעינה, או שנחצה בגלילת flick
    // מהירה מדי ל-IntersectionObserver, חייב להיחשף בכל מקרה.
    function sweep() {
      var limit = window.innerHeight * 0.94
      var pending = document.querySelectorAll('.v-reveal:not(.is-in)')
      for (var j = 0; j < pending.length; j++) {
        if (pending[j].getBoundingClientRect().top < limit) {
          pending[j].classList.add('is-in')
          io.unobserve(pending[j])
        }
      }
    }
    sweep()
    window.addEventListener('load', sweep)
    var ticking = false
    window.addEventListener(
      'scroll',
      function () {
        if (ticking) return
        ticking = true
        requestAnimationFrame(function () { ticking = false; sweep() })
      },
      { passive: true }
    )
  }

  // ══ 2. מונה מספרים ══════════════════════════════════════════════════
  // `data-count-to` — ערך היעד. `data-count-from` — התחלה (ברירת מחדל 0).
  // `data-count-prefix` / `data-count-suffix` — טקסט צמוד (למשל " ₪").
  function countUp(el, done) {
    var to = parseFloat(el.getAttribute('data-count-to'))
    var from = parseFloat(el.getAttribute('data-count-from') || '0')
    var dec = parseInt(el.getAttribute('data-count-decimals') || '0', 10)
    var pre = el.getAttribute('data-count-prefix') || ''
    var suf = el.getAttribute('data-count-suffix') || ''
    var dur = parseInt(el.getAttribute('data-count-duration') || '900', 10)

    if (isNaN(to)) return done && done()
    if (reduced) { el.textContent = pre + fmt(to, dec) + suf; return done && done() }

    var start = null
    function frame(ts) {
      if (start === null) start = ts
      var p = Math.min((ts - start) / dur, 1)
      // ease-out cubic — מגיע מהר ומתיישב, כמו שאר התנועה באתר
      var eased = 1 - Math.pow(1 - p, 3)
      el.textContent = pre + fmt(from + (to - from) * eased, dec) + suf
      if (p < 1) requestAnimationFrame(frame)
      else if (done) done()
    }
    requestAnimationFrame(frame)
  }

  function initCounters() {
    var nums = document.querySelectorAll('[data-count-to]:not([data-scene] [data-count-to])')
    if (!nums.length) return
    if (reduced || !supported) {
      for (var i = 0; i < nums.length; i++) countUp(nums[i])
      return
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return
          io.unobserve(e.target)
          countUp(e.target)
        })
      },
      { threshold: 0.5 }
    )
    for (var j = 0; j < nums.length; j++) io.observe(nums[j])
  }

  // ══ 3. סצנות — התנועה שמסבירה את המוצר ══════════════════════════════
  //
  // כל סצנה היא רצף של צעדים שמופעל פעם אחת, כשהסקשן נכנס למסך.
  // הצעדים מסומנים ב-HTML ב-`data-step="1"`, `data-step="2"` וכו',
  // ומקבלים `.is-on` בתורם. מה שהם מציגים כתוב ב-HTML ולא ב-JS —
  // הסצנה רק חושפת אותו בקצב.
  function playScene(scene) {
    var steps = scene.querySelectorAll('[data-step]')
    var arr = []
    for (var i = 0; i < steps.length; i++) arr.push(steps[i])
    arr.sort(function (a, b) {
      return (+a.getAttribute('data-step')) - (+b.getAttribute('data-step'))
    })

    if (reduced) {
      arr.forEach(function (s) {
        s.classList.add('is-on')
        var n = s.querySelector('[data-count-to]')
        if (n) countUp(n)
      })
      return
    }

    var gap = parseInt(scene.getAttribute('data-scene-gap') || '520', 10)
    arr.forEach(function (s, idx) {
      setTimeout(function () {
        s.classList.add('is-on')
        var n = s.querySelector('[data-count-to]')
        if (n) countUp(n)
      }, idx * gap)
    })
  }

  function initScenes() {
    var scenes = document.querySelectorAll('[data-scene]')
    if (!scenes.length) return
    if (reduced || !supported) {
      for (var i = 0; i < scenes.length; i++) playScene(scenes[i])
      return
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return
          io.unobserve(e.target)
          playScene(e.target)
        })
      },
      { threshold: 0.35 }
    )
    for (var j = 0; j < scenes.length; j++) io.observe(scenes[j])
  }

  function boot() {
    initReveal()
    initCounters()
    initScenes()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot)
  } else {
    boot()
  }

  // נחשף כדי שעמוד המחשבון יוכל להנפיש מספר שהתקבל מהשרת.
  window.veyaCountUp = countUp
  window.veyaReducedMotion = reduced
})()

;/* ── Header שמתכווץ בגלילה ──
   נפרד מהמודול הראשי בכוונה: הוא לא אנימציית תוכן אלא מצב ניווט, והוא
   צריך לרוץ גם כשהמשתמש ביקש תנועה מופחתת (שם הוא פשוט מחליף מצב בלי
   מעבר — ה-CSS מבטל את ה-transition). */
(function () {
  'use strict'
  var header = document.querySelector('.site-header')
  if (!header) return
  var ticking = false
  function update() {
    ticking = false
    header.classList.toggle('is-compact', window.scrollY > 40)
  }
  update()
  window.addEventListener('scroll', function () {
    if (ticking) return
    ticking = true
    requestAnimationFrame(update)
  }, { passive: true })
})()
