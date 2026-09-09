/**
 * הודעות — עמוד אחד עם דפדוף פנימי.
 *
 * ## מקור אמת אחד
 *
 * ההודעות **נקראות מהשרת בזמן build** (`GET /public/library`), שמחזיר את
 * אותן שורות `MessageDefaultOption` שהמוצר משתמש בהן. אין כאן קובץ תוכן
 * שנכתב ביד. `content/nuschim-snapshot.json` הוא מטמון build שנוצר
 * אוטומטית, ומשמש רק כשהשרת אינו זמין — אין לערוך אותו.
 *
 * ## למה עמוד אחד ולא עמוד לקטגוריה
 *
 * חמישה עמודים כמעט זהים, שכל אחד מציג רשימה ארוכה של טקסטים, הם חמישה
 * עמודים שאף אחד לא גולל עד סופם. במקום זה: ניווט בשני צירים (סוג אירוע
 * × סוג הודעה) ודפדוף בין הנוסחים בתוך מוקאפ טלפון — בדיוק כמו שהזוג
 * רואה אותם בתוך המערכת.
 *
 * ## המשתנים
 *
 * בתוך המוצר ההודעה מכילה `{{guest_name}}` והמערכת ממלאת אותו. בדף
 * ציבורי זה נראה כמו קוד, ולכן כאן הם מוחלפים בפרטי דוגמה קריאים.
 * `{{rsvp_link}}` ו-`{{navigation_link}}` הופכים לכפתורים בתחתית הבועה,
 * כי כך הם מוצגים בפועל ב-WhatsApp.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { page, pageHero, esc, SITE, CTA_PRIMARY } from './site-shell.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SNAPSHOT = path.resolve(__dirname, '../content/nuschim-snapshot.json')

/** פרטי דוגמה לכל סוג אירוע. שמות פרטיים נפוצים ושמות מקום גנריים —
 *  לא שמות של עסקים אמיתיים. */
const SAMPLE = {
  wedding:      { guest: 'דנה כהן', a: 'יונתן', b: 'שירה', venue: 'גן האירועים', addr: 'הזורע 12, רמת גן', date: '14.5.2026', time: '19:30', chat: 'החתונה של יונתן ושירה' },
  henna:        { guest: 'דנה כהן', a: 'יונתן', b: 'שירה', venue: 'בית המשפחה', addr: 'הרצל 8, ראשון לציון', date: '7.5.2026', time: '20:00', chat: 'החינה של יונתן ושירה' },
  bar_mitzvah:  { guest: 'משפחת לוי', a: 'איתי', b: '', venue: 'אולם האירועים', addr: 'ויצמן 3, כפר סבא', date: '9.3.2026', time: '19:00', chat: 'בר המצווה של איתי' },
  bat_mitzvah:  { guest: 'משפחת לוי', a: 'רוני', b: '', venue: 'אולם האירועים', addr: 'ויצמן 3, כפר סבא', date: '9.3.2026', time: '19:00', chat: 'בת המצווה של רוני' },
  brit:         { guest: 'משפחת מזרחי', a: 'הבן שלנו', b: '', venue: 'בית הכנסת', addr: 'הרב קוק 4, פתח תקווה', date: '2.2.2026', time: '9:00', chat: 'הברית של משפחת מזרחי' },
  brita:        { guest: 'משפחת מזרחי', a: 'הבת שלנו', b: '', venue: 'בית המשפחה', addr: 'הרב קוק 4, פתח תקווה', date: '2.2.2026', time: '11:00', chat: 'הבריתה של משפחת מזרחי' },
  business:     { guest: 'נועה אברהם', a: '', b: '', venue: 'מרכז הכנסים', addr: 'הארבעה 21, תל אביב', date: '18.11.2026', time: '18:00', chat: 'כנס הלקוחות השנתי' },
}
const FALLBACK = SAMPLE.wedding

/** מחליף משתנים בפרטי דוגמה. הקישורים יוצאים מהטקסט והופכים לכפתורים. */
function render(content, s) {
  const buttons = []
  let text = content
  if (/\{\{rsvp_link\}\}/.test(text)) buttons.push('אישור הגעה')
  if (/\{\{navigation_link\}\}/.test(text)) buttons.push('ניווט למקום')
  // שורת קישור נמחקת — הקישור מוצג ככפתור בתחתית הבועה, כמו ב-WhatsApp.
  // **וגם שורת התווית שלפניה** ("לאישור הגעה:"), אחרת נשארת כותרת
  // מיותמת שמצביעה על שום דבר. זו בדיוק התקלה שקיימת גם במנוע הרינדור
  // של המוצר (ראו product-state.md), ולכן חשוב לא לשחזר אותה כאן.
  const LINK = /\{\{(rsvp_link|navigation_link|maps_link|gift_link)\}\}/
  const kept = []
  for (const line of text.split('\n')) {
    if (LINK.test(line)) {
      // אם הוסרה שורת קישור, בודקים אם השורה שנשמרה לפניה היא תווית שלה
      const prev = kept[kept.length - 1]
      if (prev !== undefined && /^.{0,32}:\s*$/.test(prev.trim()) && prev.trim()) kept.pop()
      // אם הקישור היה בתוך שורה עם טקסט — משאירים את הטקסט בלי הקישור
      const rest = line.replace(new RegExp(LINK.source, 'g'), '').trim()
      if (rest && !/^.{0,32}:$/.test(rest)) kept.push(rest)
      continue
    }
    kept.push(line)
  }
  text = kept.join('\n')
  const map = {
    guest_name: s.guest, groom_name: s.a, bride_name: s.b,
    event_date: s.date, event_time: s.time, venue_name: s.venue,
    address: s.addr, maps_link: '', gift_link: '',
    rsvp_link: '', navigation_link: '',
  }
  text = text.replace(/\{\{(\w+)\}\}/g, (m, k) => (k in map ? map[k] : m))
  // ניקוי שאריות: שורות ריקות כפולות שנוצרו מהסרת קישור
  text = text.replace(/\n{3,}/g, '\n\n').trim()
  return { text, buttons }
}

async function fetchLibrary(apiUrl) {
  const url = `${apiUrl.replace(/\/$/, '')}/public/library`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 15000)
  try {
    const res = await fetch(url, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    writeFileSync(SNAPSHOT, JSON.stringify(data, null, 1))
    console.log(`  ↳ הודעות מהשרת: ${data.total}`)
    return data
  } catch (err) {
    if (existsSync(SNAPSHOT)) {
      const data = JSON.parse(readFileSync(SNAPSHOT, 'utf8'))
      console.warn(`  ⚠ ${url} לא זמין (${err.message}). snapshot: ${data.total} הודעות.`)
      return data
    }
    console.warn(`  ⚠ ${url} לא זמין ואין snapshot — עמוד ההודעות לא ייבנה.`)
    return null
  } finally {
    clearTimeout(timer)
  }
}

/* ── סגנון העמוד — מוקאפ הטלפון מועתק מהמוצר (App.css: .ph-*) ── */
const CSS = `    <style>
      /* ניווט בשני צירים */
      .msg-nav { display: grid; gap: 14px; margin-bottom: 26px; }
      .msg-axis { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
      .msg-axis > span.lbl {
        font-size: var(--fs-2xs); letter-spacing: .14em; font-weight: 700;
        color: var(--muted); margin-inline-end: 4px;
      }
      button.msg-chip {
        cursor: pointer; font: inherit; font-size: var(--fs-xs); font-weight: 600;
        /* 44px מינימום — יעד מגע, לא רק אסתטיקה */
        min-height: 44px; padding: 8px 16px; border-radius: var(--radius-pill);
        border: 1px solid var(--line); background: var(--cream); color: var(--body);
        transition: background var(--motion-fast) var(--ease-out),
                    border-color var(--motion-fast) var(--ease-out),
                    color var(--motion-fast) var(--ease-out);
      }
      button.msg-chip[aria-pressed="true"] {
        background: var(--gold); border-color: var(--gold); color: var(--charcoal);
      }
      button.msg-chip:focus-visible { outline: 3px solid var(--gold-light); outline-offset: 2px; }

      /* פריסה: מוקאפ + פאנל */
      .msg-stage { display: grid; grid-template-columns: minmax(0,300px) minmax(0,1fr); gap: 32px; align-items: start; }
      @media (max-width: 820px) { .msg-stage { grid-template-columns: 1fr; justify-items: center; } }

      /* ── מוקאפ הטלפון — זהה לזה שבמערכת ── */
      .ph { width: 290px; max-width: 100%; aspect-ratio: 9/19; display: flex; flex-direction: column;
            background: #1c1a19; border-radius: 34px; padding: 7px;
            box-shadow: 0 10px 30px rgba(28,26,25,.22), 0 1px 0 rgba(255,255,255,.14) inset; }
      .ph-screen { flex: 1; min-height: 0; display: flex; flex-direction: column;
                   background: #ece5dd; border-radius: 28px; overflow: hidden; position: relative; }
      .ph-screen::before { content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
                           width: 40%; height: 15px; background: #1c1a19; border-radius: 0 0 11px 11px; z-index: 2; }
      .ph-status { flex: none; display: flex; align-items: center; justify-content: space-between;
                   background: #075e54; color: #fff; font-size: 11px; padding: 5px 14px 3px; }
      .ph-status-icons { letter-spacing: 1px; opacity: .85; }
      .ph-bar { flex: none; display: flex; align-items: center; gap: 8px;
                background: #075e54; color: #fff; padding: 7px 12px 10px; }
      .ph-back { font-size: 19px; line-height: 1; opacity: .9; }
      .ph-avatar { width: 26px; height: 26px; border-radius: 50%; background: rgba(255,255,255,.24);
                   display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; flex: none; }
      .ph-chat-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .ph-chat { flex: 1; min-height: 0; padding: 12px 10px; overflow-y: auto;
                 scrollbar-width: none; -ms-overflow-style: none;
                 background: linear-gradient(rgba(229,221,213,.5), rgba(229,221,213,.5)),
                             repeating-linear-gradient(45deg, #ece5dd 0 12px, #e7dfd4 12px 24px); }
      .ph-chat::-webkit-scrollbar { display: none; }
      .ph-bubble { background: #dcf8c6; border-radius: 10px 10px 10px 3px; padding: 8px 9px 6px;
                   box-shadow: 0 1px 1px rgba(0,0,0,.13); }
      .ph-text { font-size: 14px; line-height: 1.6; color: #1f2c1a; word-break: break-word; overflow-wrap: anywhere; }
      .ph-line { min-height: 1.1em; }
      .ph-btns { display: flex; flex-direction: column; margin-top: 6px; }
      .ph-btn { text-align: center; font-size: 13px; font-weight: 600; color: #0a84c4;
                padding-top: 6px; margin-top: 6px; border-top: 1px solid rgba(0,0,0,.08); }
      .ph-meta { display: block; text-align: left; font-size: 10px; color: #5b7052; margin-top: 3px; }

      /* פאנל הצד */
      .msg-panel { min-width: 0; }
      .msg-tone { font-family: var(--font-display); font-size: var(--fd-md); color: var(--charcoal); margin: 0 0 6px; }
      .msg-sub { font-size: var(--fs-xs); color: var(--muted); margin: 0 0 20px; }
      .msg-pager { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
      button.msg-arrow {
        cursor: pointer; width: 44px; height: 44px; border-radius: var(--radius-pill);
        border: 1px solid var(--line); background: var(--cream); color: var(--charcoal);
        font-size: 17px; line-height: 1; display: flex; align-items: center; justify-content: center;
        transition: border-color var(--motion-fast) var(--ease-out);
      }
      button.msg-arrow:hover:not(:disabled) { border-color: var(--gold); }
      button.msg-arrow:disabled { opacity: .35; cursor: default; }
      button.msg-arrow:focus-visible { outline: 3px solid var(--gold-light); outline-offset: 2px; }
      .msg-count { font-size: var(--fs-sm); color: var(--muted); font-variant-numeric: tabular-nums; }
      .msg-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
      .msg-copied { font-size: var(--fs-sm); color: var(--success); font-weight: 600; }
      .msg-live { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
      .msg-empty { color: var(--muted); padding: 24px 0; }

      /* רשימת המקור — נראית כשאין JavaScript, ומוסתרת ברגע שהמוקאפ עולה.
         היא לא display:none מראש: זה מה שהופך אותה לזמינה לזחלנים. */
      .msg-source { display: grid; gap: 20px; margin-top: 10px; }
      .msg-item { border: 1px solid var(--line); border-radius: var(--radius-lg);
                  background: var(--cream); padding: 18px 20px; }
      .msg-item-h { font-size: var(--fs-sm); color: var(--gold-deep); margin: 0 0 10px;
                    font-family: var(--font-body); font-weight: 700; }
      .msg-item-text { margin: 0; white-space: pre-wrap; word-break: break-word;
                       font-family: inherit; font-size: var(--fs-md); line-height: 1.8; color: var(--body); }
    </style>`

/** רשימת ההודעות כ-HTML אמיתי.
 *
 *  **למה לא משתנה JavaScript:** זחלני AI (ו-Googlebot לצורך טקסט) לא
 *  מריצים JS. כשההודעות ישבו ב-`var MSGS` העמוד הכיל 1,181 תווים גלויים
 *  מול 13,543 שנעולים בסקריפט — כלומר כל התוכן שלו היה בלתי נראה.
 *  עכשיו הכול ב-DOM, וה-JS רק משדרג אותו למוקאפ עם ניווט. בלי JS נשארת
 *  רשימה קריאה ותקינה. */
const list = (data) => `          <div class="msg-source" id="msg-source">
${data.items.map((m, i) => `            <article class="msg-item" data-ev="${esc(m.ev)}" data-ty="${esc(m.ty)}"
              data-ev-label="${esc(m.evLabel)}" data-ty-label="${esc(m.tyLabel)}"
              data-tone="${esc(m.tone || '')}" data-chat="${esc(m.chat)}"
              data-buttons="${esc(m.buttons.join('|'))}">
              <h3 class="msg-item-h">${esc(m.tyLabel)} · ${esc(m.evLabel)}${m.tone ? ' · ' + esc(m.tone) : ''}</h3>
              <pre class="msg-item-text">${esc(m.text)}</pre>
            </article>`).join('\n')}
          </div>`

const JS = () => `    <script>
      (function () {
        var evChips = document.getElementById('ev-axis');
        var tyChips = document.getElementById('ty-axis');
        var stage = document.getElementById('stage');
        var live = document.getElementById('msg-live');
        if (!evChips || !stage) return;

        // מקור הנתונים היחיד: הרשימה שכבר נמצאת ב-HTML.
        var nodes = [].slice.call(document.querySelectorAll('#msg-source .msg-item'));
        if (!nodes.length) return;
        var MSGS = { events: [], items: nodes.map(function (n) {
          return {
            ev: n.dataset.ev, evLabel: n.dataset.evLabel,
            ty: n.dataset.ty, tyLabel: n.dataset.tyLabel,
            tone: n.dataset.tone, chat: n.dataset.chat,
            buttons: n.dataset.buttons ? n.dataset.buttons.split('|') : [],
            text: n.querySelector('.msg-item-text').textContent,
          };
        }) };
        MSGS.items.forEach(function (m) {
          if (!MSGS.events.some(function (e) { return e.key === m.ev; })) {
            MSGS.events.push({ key: m.ev, label: m.evLabel });
          }
        });
        // מרגע שה-JS פעיל, הרשימה הגולמית מוסתרת — המוקאפ מחליף אותה.
        document.getElementById('msg-source').hidden = true;

        var state = { ev: MSGS.events[0].key, ty: null, i: 0 };

        function forEvent(ev) { return MSGS.items.filter(function (m) { return m.ev === ev; }); }
        function types(ev) {
          var seen = [], out = [];
          forEvent(ev).forEach(function (m) {
            if (seen.indexOf(m.ty) < 0) { seen.push(m.ty); out.push({ key: m.ty, label: m.tyLabel }); }
          });
          return out;
        }
        function current() {
          return forEvent(state.ev).filter(function (m) { return m.ty === state.ty; });
        }

        function chip(label, on, onClick) {
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'msg-chip';
          b.textContent = label;
          b.setAttribute('aria-pressed', on ? 'true' : 'false');
          b.addEventListener('click', onClick);
          return b;
        }

        function renderChips() {
          evChips.querySelectorAll('button').forEach(function (b) { b.remove(); });
          MSGS.events.forEach(function (e) {
            evChips.appendChild(chip(e.label, e.key === state.ev, function () {
              state.ev = e.key; state.ty = null; state.i = 0; renderAll();
            }));
          });
          var ts = types(state.ev);
          if (!state.ty || !ts.some(function (t) { return t.key === state.ty; })) {
            state.ty = ts.length ? ts[0].key : null;
          }
          tyChips.querySelectorAll('button').forEach(function (b) { b.remove(); });
          ts.forEach(function (t) {
            tyChips.appendChild(chip(t.label, t.key === state.ty, function () {
              state.ty = t.key; state.i = 0; renderAll();
            }));
          });
          tyChips.hidden = ts.length < 2;
        }

        function renderStage() {
          var list = current();
          if (!list.length) { stage.innerHTML = '<p class="msg-empty">אין כאן הודעות עדיין.</p>'; return; }
          if (state.i >= list.length) state.i = 0;
          var m = list[state.i];
          var lines = m.text.split('\\n').map(function (l) {
            return '<div class="ph-line">' + (l ? esc(l) : '&nbsp;') + '</div>';
          }).join('');
          var btns = m.buttons.length
            ? '<div class="ph-btns">' + m.buttons.map(function (b) {
                return '<span class="ph-btn">' + esc(b) + '</span>';
              }).join('') + '</div>'
            : '';

          stage.innerHTML =
            '<div class="ph" dir="rtl">' +
              '<div class="ph-screen">' +
                '<div class="ph-status"><span>9:41</span><span class="ph-status-icons" aria-hidden="true">▮▮ ⌁</span></div>' +
                '<div class="ph-bar"><span class="ph-back" aria-hidden="true">›</span>' +
                  '<span class="ph-avatar" aria-hidden="true">' + esc(m.chat.charAt(0)) + '</span>' +
                  '<span class="ph-chat-name">' + esc(m.chat) + '</span></div>' +
                '<div class="ph-chat"><div class="ph-bubble">' +
                  '<div class="ph-text">' + lines + '</div>' + btns +
                  '<span class="ph-meta">9:41</span>' +
                '</div></div>' +
              '</div>' +
            '</div>' +
            '<div class="msg-panel">' +
              '<p class="msg-tone">' + esc(m.tone || 'נוסח ' + (state.i + 1)) + '</p>' +
              '<p class="msg-sub">' + esc(m.tyLabel) + ' · ' + esc(m.evLabel) + '</p>' +
              '<div class="msg-pager">' +
                '<button type="button" class="msg-arrow" id="prev" aria-label="ההודעה הקודמת">›</button>' +
                '<span class="msg-count">' + (state.i + 1) + ' מתוך ' + list.length + '</span>' +
                '<button type="button" class="msg-arrow" id="next" aria-label="ההודעה הבאה">‹</button>' +
              '</div>' +
              '<div class="msg-actions">' +
                '<button type="button" class="btn btn-ghost" id="copy">העתקת ההודעה</button>' +
                '<span class="msg-copied" id="copied" aria-hidden="true"></span>' +
              '</div>' +
            '</div>';

          var prev = document.getElementById('prev'), next = document.getElementById('next');
          prev.disabled = state.i === 0;
          next.disabled = state.i === list.length - 1;
          prev.addEventListener('click', function () { if (state.i > 0) { state.i--; renderStage(); announce(); } });
          next.addEventListener('click', function () { if (state.i < list.length - 1) { state.i++; renderStage(); announce(); } });
          document.getElementById('copy').addEventListener('click', function () { copy(m.text); });
        }

        function announce() {
          var list = current();
          if (live) live.textContent = 'הודעה ' + (state.i + 1) + ' מתוך ' + list.length;
        }

        function copy(text) {
          var note = document.getElementById('copied');
          function done(ok) {
            var msg = ok ? 'ההודעה הועתקה' : 'לא הצלחנו להעתיק — אפשר לסמן ולהעתיק ידנית';
            if (note) note.textContent = msg;
            if (live) live.textContent = msg;
            setTimeout(function () { if (note) note.textContent = ''; if (live) live.textContent = ''; }, 4000);
          }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
          } else { done(false); }
        }

        function esc(s) {
          return String(s).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
          });
        }

        function renderAll() { renderChips(); renderStage(); }
        renderAll();
      })();
    </script>`

/** ממיר את מבנה ה-API למבנה שטוח שהעמוד עובד איתו. */
function flatten(data) {
  const events = []
  const items = []
  for (const cat of data.categories) {
    for (const w of cat.wordings) {
      const s = SAMPLE[w.event_type] || FALLBACK
      const { text, buttons } = render(w.content, s)
      if (!text.trim()) continue
      items.push({
        ev: w.event_type, evLabel: w.event_type_label,
        ty: w.message_type, tyLabel: w.message_type_label,
        tone: w.tone, text, buttons, chat: s.chat,
      })
      if (!events.some((e) => e.key === w.event_type)) {
        events.push({ key: w.event_type, label: w.event_type_label })
      }
    }
  }
  // חתונה ראשונה — היא הסוג העשיר ביותר, ושאר הסוגים לפי סדר הופעה.
  events.sort((a, b) => (a.key === 'wedding' ? -1 : b.key === 'wedding' ? 1 : 0))
  return { events, items }
}

export async function buildNuschim(apiUrl) {
  const raw = await fetchLibrary(apiUrl)
  if (!raw || !raw.categories.length) return []
  const data = flatten(raw)
  if (!data.items.length) return []

  const evNames = data.events.map((e) => e.label).join(' · ')
  const body = `${pageHero({
    eyebrow: 'מה נשלח למוזמנים',
    h1: 'ההודעות שהמוזמנים שלכם מקבלים',
    lead: `הזמנה, בקשת אישור הגעה ותזכורות — לפי סוג האירוע. אלה ההודעות שכבר נמצאות בתוך VEYA, בדיוק כפי שהן נראות בטלפון של המוזמן.`,
    trail: [{ name: 'VEYA', url: '/' }, { name: 'הודעות' }],
  })}

      <section class="article-wrap">
        <div class="wrap">
          <div class="msg-nav">
            <div class="msg-axis" id="ev-axis" role="group" aria-label="סוג האירוע">
              <span class="lbl">סוג האירוע</span>
            </div>
            <div class="msg-axis" id="ty-axis" role="group" aria-label="סוג ההודעה">
              <span class="lbl">סוג ההודעה</span>
            </div>
          </div>

          <div class="msg-stage" id="stage"></div>

${list(data)}
          <p class="msg-live" id="msg-live" role="status" aria-live="polite"></p>

          <p class="calc-note" style="max-width:66ch;margin-top:34px">
            <b>הפרטים בהודעות הם דוגמה.</b> בתוך VEYA השם של כל מוזמן, התאריך,
            השעה והמקום נכנסים אוטומטית מפרטי האירוע שלכם — לא צריך למלא אותם
            בכל הודעה מחדש. הכפתורים בתחתית ההודעה הם מה שהמוזמן לוחץ עליו
            בפועל.
          </p>

          <div class="callout" style="max-width:660px;margin-top:30px">
            <p class="callout-h">ומתי שולחים כל אחת מהן?</p>
            <p>לוח הזמנים של אישורי ההגעה נבנה לאחור ממועד סגירת הרשימה.</p>
            <p><a href="/calculators/rsvp-timeline/">לראות את לוח הזמנים</a></p>
          </div>

          <p class="calc-note" style="margin-top:24px">
            ניהול האירוע לפי סוג: ${data.events.map((e) => {
              const slug = { bar_mitzvah: 'bar-mitzvah', bat_mitzvah: 'bat-mitzvah' }[e.key] || e.key
              return `<a href="/events/${slug}/">${esc(e.label)}</a>`
            }).join(' · ')}
          </p>
        </div>
      </section>

      <section class="band-wrap">
        <div class="wrap">
          <div class="band">
            <span class="kicker">מתחילים</span>
            <h2>ההודעות האלה כבר בפנים</h2>
            <p class="band-more">
              בתוך VEYA בוחרים הודעה לכל שלב, עורכים אותה אם בא לכם, ורואים
              תצוגה מקדימה לפני שמשהו יוצא.
            </p>
            ${CTA_PRIMARY}
          </div>
        </div>
      </section>`

  const html = page({
    path: '/nuschim/',
    title: 'הודעות — מה המוזמנים מקבלים | VEYA',
    description: `ההודעות שנשלחות למוזמנים באירוע: הזמנה, בקשת אישור הגעה ותזכורות, לפי סוג האירוע — ${evNames}. בדיוק כפי שהן נראות בטלפון.`,
    trail: [{ name: 'VEYA', url: '/' }, { name: 'הודעות' }],
    schema: [
      {
        '@type': 'CollectionPage',
        name: 'הודעות',
        inLanguage: 'he-IL',
        url: `${SITE}/nuschim/`,
        description: 'ההודעות שנשלחות למוזמנים באירוע, לפי סוג האירוע ולפי שלב.',
      },
    ],
    head: CSS,
    body,
    scripts: JS(),
  })

  return [{ path: '/nuschim/', html }]
}
