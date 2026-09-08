/**
 * ספריית הנוסחים — /nuschim/ ועמוד לכל קטגוריה.
 *
 * ## מקור אמת אחד
 *
 * הנוסחים **נקראים מהשרת בזמן build** (`GET /public/library`), שמחזיר את
 * אותן שורות `MessageDefaultOption` שהמוצר משתמש בהן. אין כאן קובץ תוכן
 * שנכתב ביד, ואין מערכת נוסחים מקבילה: כשהבעלים עורך נוסח באדמין, ה-build
 * הבא מרים את השינוי.
 *
 * ## למה build-time ולא fetch בדפדפן
 *
 * העמוד אמור להיות נכס SEO. נוסחים שנטענים ב-JavaScript אינם בהכרח
 * מאונדקסים, ואז נשאר דף עם כותרת וריק. בנוסף, רינדור בצד השרת חוסך
 * לגולש קריאת רשת לפני שהוא רואה תוכן.
 *
 * ## snapshot — למה הוא קיים
 *
 * `content/nuschim-snapshot.json` הוא **מטמון build שנוצר אוטומטית**, לא
 * מקור תוכן. הוא נכתב בכל build מוצלח, ומשמש רק כשהשרת אינו זמין בזמן
 * build (למשל שרת שנרדם) — כדי שדחיפה של שינוי לא קשור לא תרוקן את
 * העמודים בשקט. אין לערוך אותו ביד.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { page, pageHero, esc, SITE, CTA_PRIMARY } from './site-shell.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SNAPSHOT = path.resolve(__dirname, '../content/nuschim-snapshot.json')

/** טקסט הסבר לכל קטגוריה — הקשר, לא תוכן. הנוסחים עצמם מגיעים מה-DB. */
const BLURBS = {
  invitations: {
    intro: 'ההודעה הראשונה שהמוזמנים מקבלים. היא צריכה להגיד מי, מתי, איפה — ולהשאיר מקום לאישור הגעה.',
    when: 'נשלחת פעם אחת, בתחילת התהליך.',
  },
  rsvp: {
    intro: 'הבקשה שממנה מתחיל המספר. ככל שהיא קצרה וברורה יותר, כך אחוז המענה גבוה יותר.',
    when: 'השלב הראשון בלוח הזמנים של אישורי ההגעה.',
  },
  reminders: {
    intro: 'תזכורות יוצאות רק למי שעדיין לא ענה — זה מה שמונע מהן להרגיש נודניקיות.',
    when: 'שלוש תזכורות, פרוסות בין סבבי המעקב.',
  },
  'event-day': {
    intro: 'ההודעה של יום האירוע: שעה, מקום וניווט. היא נשלחת למי שאישר.',
    when: 'ביום האירוע עצמו.',
  },
  thanks: {
    intro: 'הודעת התודה שנשלחת אחרי האירוע.',
    when: 'ביום שאחרי.',
  },
}

/** משתנים שמופיעים בנוסחים — מוסברים פעם אחת, לא בכל כרטיס. */
const VAR_HINT =
  'הטקסטים כוללים משתנים בסוגריים מסולסלים (למשל <code>{{guest_name}}</code>). בתוך המערכת הם מוחלפים אוטומטית בפרטים של האירוע ושל המוזמן; אם אתם מעתיקים את הנוסח לשימוש חיצוני, החליפו אותם ידנית.'

async function fetchLibrary(apiUrl) {
  const url = `${apiUrl.replace(/\/$/, '')}/public/library`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 15000)
  try {
    const res = await fetch(url, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    writeFileSync(SNAPSHOT, JSON.stringify(data, null, 1))
    console.log(`  ↳ נוסחים מהשרת: ${data.total} · ${data.categories.length} קטגוריות`)
    return data
  } catch (err) {
    if (existsSync(SNAPSHOT)) {
      const data = JSON.parse(readFileSync(SNAPSHOT, 'utf8'))
      console.warn(`  ⚠ ${url} לא זמין (${err.message}). נעשה שימוש ב-snapshot: ${data.total} נוסחים.`)
      return data
    }
    console.warn(`  ⚠ ${url} לא זמין (${err.message}) ואין snapshot — ספריית הנוסחים לא תיבנה.`)
    return null
  }
}

/** כרטיס נוסח יחיד. `.numcard` הקיים, בלי רכיב חדש. */
function wordingCard(w, idx) {
  const id = `w-${w.event_type}-${w.message_type}-${w.option_number}`
  const meta = [w.event_type_label, w.message_type_label, w.tone].filter(Boolean)
  const name = w.tone || w.title || `נוסח ${idx + 1}`
  // `aria-label` ייחודי לכל כפתור: בעמוד יש עשרות כפתורי "העתקת הנוסח",
  // ומי שמנווט ברשימת הכפתורים של קורא מסך היה שומע את אותה מילה שוב ושוב.
  const label = `העתקת הנוסח: ${name} · ${w.event_type_label}`
  return `            <article class="numcard nuschim-card" data-event="${esc(w.event_type)}" id="${id}">
              <div class="numcard-head">
                <h3>${esc(name)}</h3>
                <span class="numcard-tag">${esc(w.event_type_label)}</span>
              </div>
              <p class="nuschim-meta">${esc(meta.join(' · '))}</p>
              <pre class="nuschim-text" id="${id}-t">${esc(w.content)}</pre>
              <div class="nuschim-actions">
                <button type="button" class="btn btn-ghost nuschim-copy" data-target="${id}-t" aria-label="${esc(label)}">
                  העתקת הנוסח
                </button>
                <span class="nuschim-copied" aria-hidden="true"></span>
              </div>
            </article>`
}

function categoryPage(cat, allCats) {
  const blurb = BLURBS[cat.key] || { intro: '', when: '' }
  const others = allCats
    .filter((c) => c.key !== cat.key)
    .map((c) => `            <li><a href="/nuschim/${c.key}/"><h3>${esc(c.label)}</h3><p>${c.wordings.length} נוסחים</p></a></li>`)
    .join('\n')

  const filters = cat.event_types.length > 1
    ? `          <div class="nuschim-filters" role="group" aria-label="סינון לפי סוג אירוע">
            <button type="button" class="note-chip nuschim-filter is-on" data-event="all" aria-pressed="true">הכול (${cat.wordings.length})</button>
${cat.event_types.map((e) => `            <button type="button" class="note-chip nuschim-filter" data-event="${esc(e.key)}" aria-pressed="false">${esc(e.label)} (${e.count})</button>`).join('\n')}
          </div>`
    : ''

  const eventLinks = cat.event_types
    .map((e) => {
      const slug = { bar_mitzvah: 'bar-mitzvah', bat_mitzvah: 'bat-mitzvah' }[e.key] || e.key
      return `<a href="/events/${slug}/">${esc(e.label)}</a>`
    })
    .join(' · ')

  return page({
    path: `/nuschim/${cat.key}/`,
    title: `${cat.label} לאירוע | VEYA`,
    description: `${cat.label} מוכנים לשימוש, לפי סוג האירוע. ${blurb.intro}`.slice(0, 300),
    trail: [{ name: 'VEYA', url: '/' }, { name: 'נוסחי הודעות', url: '/nuschim/' }, { name: cat.label }],
    schema: [
      {
        '@type': 'CollectionPage',
        name: cat.label,
        inLanguage: 'he-IL',
        url: `${SITE}/nuschim/${cat.key}/`,
        description: blurb.intro,
      },
    ],
    head: NUSCHIM_CSS,
    body: `${pageHero({
      eyebrow: 'נוסחי הודעות',
      h1: esc(cat.label),
      lead: esc(blurb.intro),
      trail: [{ name: 'VEYA', url: '/' }, { name: 'נוסחי הודעות', url: '/nuschim/' }, { name: cat.label }],
    })}

      <section class="article-wrap">
        <div class="wrap">
          <p class="calc-note" style="max-width:70ch;margin-bottom:22px">
            <b>מתי משתמשים:</b> ${esc(blurb.when)} ${VAR_HINT}
          </p>

${filters}

          <h2 class="section-title" style="font-size:22px;margin-bottom:18px">${esc(cat.label)} מוכנים להעתקה</h2>
          <div class="nuschim-list">
${cat.wordings.map(wordingCard).join('\n')}
          </div>

          <p class="nuschim-empty" hidden>אין נוסחים לסוג האירוע הזה בקטגוריה הזו.</p>

          <!-- אזור הכרזה יחיד לכל העמוד: העתקה וסינון מדווחים דרכו. -->
          <p id="nuschim-live" class="nuschim-live" role="status" aria-live="polite"></p>

          <div class="callout" style="max-width:660px;margin-top:40px">
            <p class="callout-h">צריכים גם לדעת מתי לשלוח את הבקשה?</p>
            <p>לוח הזמנים של אישורי ההגעה נבנה לאחור ממועד סגירת הרשימה.</p>
            <p><a href="/calculators/rsvp-timeline/">למחשבון לוח הזמנים</a></p>
          </div>

          ${eventLinks ? `<p class="calc-note" style="margin-top:26px">ניהול האירוע לפי סוג: ${eventLinks}</p>` : ''}

${others ? `          <div class="guide-cluster">
            <h2>קטגוריות נוספות</h2>
            <ul class="guide-list">
${others}
            </ul>
          </div>` : ''}
        </div>
      </section>

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>הנוסחים האלה כבר בפנים</h2>
            <p class="band-more">
              בתוך VEYA בוחרים נוסח לכל שלב, עורכים אותו אם בא לכם, ורואים תצוגה
              מקדימה לפני שמשהו יוצא.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`,
    scripts: NUSCHIM_JS,
  })
}

function indexPage(cats, total) {
  return page({
    path: '/nuschim/',
    title: 'נוסחי הודעות לאירועים | VEYA',
    description:
      'נוסחי הזמנה, בקשת אישור הגעה, תזכורת, יום האירוע ותודה — לפי סוג האירוע והשלב שבו אתם נמצאים. מוכנים להעתקה.',
    trail: [{ name: 'VEYA', url: '/' }, { name: 'נוסחי הודעות' }],
    schema: [
      {
        '@type': 'CollectionPage',
        name: 'נוסחי הודעות לאירועים',
        inLanguage: 'he-IL',
        url: `${SITE}/nuschim/`,
        description: 'ספריית נוסחי הודעות לאירועים, לפי שלב וסוג אירוע.',
      },
    ],
    head: NUSCHIM_CSS,
    body: `${pageHero({
      eyebrow: 'ספריית נוסחים',
      h1: 'נוסחי הודעות לאירועים',
      lead: 'נוסחי הזמנה, אישור הגעה, תזכורת, יום האירוע ותודה — לפי סוג האירוע והשלב שבו אתם נמצאים.',
      trail: [{ name: 'VEYA', url: '/' }, { name: 'נוסחי הודעות' }],
    })}

      <section class="article-wrap">
        <div class="wrap">
          <h2 class="section-title" style="font-size:22px;text-align:center;margin-bottom:20px">הקטגוריות</h2>
          <ul class="guide-list" style="max-width:720px;margin:0 auto">
${cats.map((c) => `            <li><a href="/nuschim/${c.key}/"><h3>${esc(c.label)}</h3><p>${esc((BLURBS[c.key] || {}).intro || '')} (${c.wordings.length} נוסחים)</p></a></li>`).join('\n')}
          </ul>

          <p class="calc-note" style="max-width:66ch;margin:30px auto 0;text-align:center">
            ${total} נוסחים, מתוך אותה ספרייה שמוצגת בתוך המערכת. ${VAR_HINT}
          </p>

          <div class="callout" style="max-width:660px;margin:34px auto 0">
            <p class="callout-h">צריכים גם לדעת מתי לשלוח את הבקשה?</p>
            <p>לוח הזמנים של אישורי ההגעה נבנה לאחור ממועד סגירת הרשימה.</p>
            <p><a href="/calculators/rsvp-timeline/">למחשבון לוח הזמנים</a></p>
          </div>
        </div>
      </section>

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>לא צריך להעתיק ידנית</h2>
            <p class="band-more">
              בתוך VEYA הנוסחים כבר משויכים לשלב הנכון, עם הפרטים של האירוע שלכם.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`,
    scripts: NUSCHIM_JS,
  })
}

/** CSS מקומי לעמוד — נשען על הטוקנים הקיימים בלבד, בלי לגעת בגלובלי. */
const NUSCHIM_CSS = `    <style>
      .nuschim-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 26px; }
      button.nuschim-filter { cursor: pointer; font: inherit; font-size: 13.5px; border: 1px solid var(--line); background: var(--cream); color: var(--body); }
      button.nuschim-filter.is-on { background: var(--gold); border-color: var(--gold); color: var(--charcoal); font-weight: 600; }
      button.nuschim-filter:focus-visible { outline: 3px solid var(--gold-light); outline-offset: 2px; }
      .nuschim-list { display: grid; gap: 18px; }
      /* numcard הגיע מדף הבית עם רוחב מוגבל ומרווח עליון משלו. ברשימה כאן
         הרוחב מלא והמרווח מגיע מהגריד, ולכן שניהם מאופסים. */
      .nuschim-card { max-width: none; margin: 0; }
      .nuschim-meta { margin: 0; padding: 10px 20px 0; font-size: 13.5px; color: var(--muted); }
      .nuschim-text {
        margin: 10px 0 0; padding: 16px 20px; white-space: pre-wrap; word-break: break-word;
        font-family: inherit; font-size: 15.5px; line-height: 1.8; color: var(--body);
        background: var(--ivory); border-top: 1px solid var(--line);
      }
      .nuschim-actions { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-top: 1px solid var(--line); }
      .nuschim-actions .btn { padding: 9px 20px; font-size: 14.5px; }
      .nuschim-copied { font-size: 14px; color: var(--green); font-weight: 600; }
      .nuschim-empty { text-align: center; color: var(--muted); padding: 30px 0; }
      /* אזור ההכרזה נקרא ע"י קורא מסך בלבד — המשוב הוויזואלי יושב ליד הכפתור. */
      .nuschim-live { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
      .nuschim-text code, .calc-note code { background: var(--ivory-2); padding: 1px 5px; border-radius: 5px; font-size: 0.92em; }
    </style>`

const NUSCHIM_JS = `    <script>
      (function () {
        // ---- סינון לפי סוג אירוע ----
        var filters = document.querySelectorAll('.nuschim-filter');
        var cards = document.querySelectorAll('.nuschim-card');
        var empty = document.querySelector('.nuschim-empty');
        filters.forEach(function (btn) {
          btn.addEventListener('click', function () {
            var want = btn.dataset.event;
            filters.forEach(function (b) {
              var on = b === btn;
              b.classList.toggle('is-on', on);
              b.setAttribute('aria-pressed', on ? 'true' : 'false');
            });
            var shown = 0;
            cards.forEach(function (c) {
              var show = want === 'all' || c.dataset.event === want;
              c.hidden = !show;
              if (show) shown++;
            });
            if (empty) empty.hidden = shown > 0;
            var live = document.getElementById('nuschim-live');
            if (live) live.textContent = shown + ' נוסחים מוצגים';
          });
        });

        // ---- העתקה ----
        document.querySelectorAll('.nuschim-copy').forEach(function (btn) {
          btn.addEventListener('click', function () {
            var el = document.getElementById(btn.dataset.target);
            if (!el) return;
            var note = btn.parentNode.querySelector('.nuschim-copied');
            var live = document.getElementById('nuschim-live');
            var text = el.textContent;
            function done(ok) {
              // כשההעתקה לא מתאפשרת (דפדפן ללא הרשאת לוח, הקשר לא מאובטח)
              // מסמנים את הטקסט עצמו, כדי ש"להעתיק ידנית" יהיה הקשה אחת
              // ולא בחירה ידנית של פסקה שלמה.
              if (!ok) {
                try {
                  var sel = window.getSelection();
                  var range = document.createRange();
                  range.selectNodeContents(el);
                  sel.removeAllRanges();
                  sel.addRange(range);
                } catch (e2) { /* אין מה לעשות — ההודעה למטה עדיין מסבירה */ }
              }
              var msg = ok ? 'הנוסח הועתק' : 'סימנו לכם את הטקסט — אפשר להעתיק עכשיו';
              if (note) note.textContent = msg;
              if (live) live.textContent = msg;
              setTimeout(function () {
                if (note) note.textContent = '';
                if (live) live.textContent = '';
              }, 5000);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
            } else {
              try {
                var ta = document.createElement('textarea');
                ta.value = text; ta.setAttribute('readonly', '');
                ta.style.position = 'absolute'; ta.style.left = '-9999px';
                document.body.appendChild(ta); ta.select();
                document.execCommand('copy'); document.body.removeChild(ta);
                done(true);
              } catch (e) { done(false); }
            }
          });
        });
      })();
    </script>`

/**
 * @returns {Promise<Array<{path: string, html: string}>>}
 */
export async function buildNuschim(apiUrl) {
  const data = await fetchLibrary(apiUrl)
  if (!data || !data.categories.length) return []
  const cats = data.categories
  const out = [{ path: '/nuschim/', html: indexPage(cats, data.total) }]
  for (const cat of cats) {
    out.push({ path: `/nuschim/${cat.key}/`, html: categoryPage(cat, cats) })
  }
  return out
}
