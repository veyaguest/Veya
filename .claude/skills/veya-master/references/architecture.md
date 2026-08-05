# VEYA — Architecture

## סטאק בפועל
| שכבה | טכנולוגיה |
|---|---|
| Frontend | React 19 + TypeScript + Vite. **בלי ספריית router** (ניהול עמוד ידני ב-state) · **בלי ספריית state** (localStorage `authStore`). עורך המפה נבנה **בלי Konva/Fabric** — React טהור. |
| Backend | FastAPI + SQLAlchemy 2.0 (Mapped/mapped_column) |
| DB | SQLite (פיתוח) / PostgreSQL — Supabase (ייצור) |
| Auth | JWT — bcrypt + PyJWT, `token_version` לביטול, rate-limit |
| Deploy | Vercel (frontend) · Render (backend) · Supabase (db) |
| WhatsApp | httpx → Meta Cloud API (במצב `mock`) |

תלויות: ראה `backend/requirements.txt` (httpx כלול) ו-`frontend/package.json`.

## מפת קוד — Backend (`backend/app/`)
- `main.py` — כניסה, רישום routers, מיגרציות קלות (`_ensure_columns`/`_ensure_indexes`),
  seeding ברירות מחדל גלובליות, גיבוי ב-startup.
- `models.py` — כל מודלי ה-DB (מקור אמת לסכימה).
- `database.py` · `deps.py` · `auth.py` · `schemas.py` · `validators.py` ·
  `ratelimit.py` · `audit.py` · `backup.py` · `media.py`.
- `seating.py` — מנוע השיבוץ הדטרמיניסטי (`seating-engine.md`).
- `constraints.py` · `automation.py` · `messaging.py` · `importer.py` ·
  `communication.py` (רצף "תקשורת עם אורחים" — ראה למטה) · `rsvp_timeline.py` ·
  `venues.py` · `invitations.py`.
- `routers/` — endpoint לכל תחום, prefixים: `/auth` `/admin` `/events`
  `/events/{id}/members` `/guests` `/guests/import` `/seating` `/constraints`
  `/messaging` `/stats` `/event` `/hall` `/confirm` `/automation`
  `/communication` `/venues` `/media`.

## מפת קוד — Frontend (`frontend/src/`)
- `App.tsx` — שורש, ניתוב עמודים ידני, מצב אדמין/התחזות, טעינת אירוע.
- `api.ts` — קריאות ל-backend · `authStore.ts` — טוקן/eventId ב-localStorage ·
  `types.ts` · `readiness.ts` · `seatingAdvisor.ts`.
- `strings/he.ts` — **מקור אמת יחיד לטקסטים בעברית** (קול המותג).
- `components/` — מסך לכל תחום: `DashboardPage` `GuestsPage` `RsvpPage`
  `HallPage` `ConfirmPage` `AdminApp/AdminPage` `OnboardingWizard` +
  דיאלוגים/פאנלים (Import, `CommunicationTab` — "תקשורת עם אורחים", PrepWizard,
  SmartAssistantPanel, VenueAutocomplete ועוד).
- מערכת עיצוב: `App.css` (~9,300 שורות, design tokens ב-`:root`) — ראה `design-system.md`.

## מודל נתונים (עיקרי)
`User` (owner/admin, account_type couple/planner/venue) → `Event` (פרטי חתונה,
מפת אולם JSON, תבנית הודעה, מסלול RSVP) → `Guest` (מקור אמת: צד/קבוצה/כמות/
הערות/טוקן אישי/confirmed_count/is_child). סביבם: `Message`, `Clarification`,
`EventMember`, `AuditLog`, `LoginEvent`, `Venue`, `MediaBlob`. תקשורת עם
אורחים: `MessageDefault` (קטלוג גלובלי event_type×message_type) +
`EventMessage` (רצף בפועל לכל אירוע) — ראה סעיף ייעודי למטה.
`MessageTemplate`/`AutomationRule`/`VeyaTemplate`/`VeyaWorkflowStep` **DEPRECATED**
(נשארו בקובץ לתיעוד היסטורי בלבד — לא נכתבים אליהם יותר, ראו `decisions.md`
2026-08-05). פרטים מלאים ב-`models.py`.

## תקשורת עם אורחים (רצף הודעות קבוע — 🔒 `decisions.md` 2026-08-05)
מחליף צירוף ישן של 3 מנגנונים (ספריית קטגוריות/סגנונות + אוטומציות חופשיות +
מסלול RSVP גלובלי) במודל אחד ופשוט:
- **`MessageDefault`** (גלובלי, מנוהל אדמין ב-`/admin/message-defaults`) —
  48 שורות קבועות: 8 סוגי אירוע × 6 סוגי הודעה
  (`invitation`/`reminder_1`/`reminder_2`/`final_reminder`/`event_day`/
  `thank_you`). `content` ריק עד שהאדמין מזין טקסט סופי — לא מומצא.
- **`EventMessage`** (לכל אירוע) — מוקצה אוטומטית (idempotent,
  `communication.py: provision_event_messages`) מ-`MessageDefault` לפי
  `event.event_type`, בעת יצירת אירוע. הזוג עורך כאן — לא בוחר תבניות.
  שדות תזמון/קהל (`trigger_offset_days`/`target_audience`) קבועים לכל
  message_type, לא מוגדרים ידנית כמו ב-`AutomationRule` הישן.
- **רינדור:** `communication.py: render_message()` — משתני `{{var}}` (רשימה
  סגורה: `guest_name`/`guest_names`/`host_names`/`event_type`/`event_date`/
  `event_time`/`venue_name`/`address`/`navigation_link`/`rsvp_link`/
  `table_number`/`gift_link`), **שונה** מהטוקנים הישנים בסוגריים מרובעים
  ({{name}}-style) של `messaging.py`. שורה שכל משתניה ריקים נמחקת ("תוכן חכם").
- **UX:** `CommunicationTab.tsx` — לשונית/מסך אחד "תקשורת עם אורחים" (6
  כרטיסים קבועים: עריכה, הפעלה/כיבוי, תצוגה מקדימה, שליחה לבדיקה), מוטמע גם
  במסך הזוג (`CoupleRsvpView`, אנקור `#mb-anchor`) וגם בפאנל האדמין הטכני.
- **שילוב עם השליחה האמיתית:** `routers/automation.py: /track/activate`
  (שליחת הזמנות בפועל) ו-`/track/advance` (תזכורות/יום-אירוע/תודה אוטומטיות)
  **נשארו** — רק המקור הפנימי שלהם הוחלף מ-`AutomationRule`/`rsvp_track.py`
  ל-`EventMessage`/`communication.py`, כדי לא לשבור את הפלואו האמיתי שה-Dashboard
  כבר תלוי בו. עקרון "תור לאישור" (שום דבר לא נשלח בלי אישור מפורש) נשמר —
  `/communication/due` מחשב, `/communication/due/send` שולח רק אחרי אישור.

## עקרונות ארכיטקטוניים נעולים
- **הפרדת AI:** LLM לפרשנות/שיח בלבד; חישוב השיבוץ **דטרמיניסטי**. ראה `decisions.md`.
- **מודל "תור לאישור":** אוטומציות מחשבות מה הגיע זמנו; שום דבר לא נשלח בלי
  אישור מפורש של הבעלים.
- **מיגרציות:** כרגע ידניות ב-`main.py`. מעבר ל-Alembic הוא חוב ידוע.
- **Event-first architecture — `event_type` הוא מקור ההתאמה המרכזי (🔒
  `decisions.md`):** מערכת אחת, לא מערכת נפרדת לכל סוג אירוע. שדה `event_type`
  על `Event` (ברירת מחדל `"wedding"`) הוא ה-**single source of truth** לכל
  התאמה תלוית-סוג-אירוע — לוגיקה ושפה כאחד. אף מסך לא מחליט "זו חתונה" על
  סמך הנחה מקומית; הכול נשען על השדה הזה.
- **שכבת Lexicon מרכזית** (לא לפזר טקסטים קשיחים במסכים): `frontend/src/
  strings/eventTypes.ts` (`getEventTerms()`, נשען על `getActiveEventType()`)
  ו-`backend/app/event_terms.py` (`EVENT_TERMS` dict) הם **מקור האמת היחיד**
  לכל טקסט/תווית תלוית-אירוע (כינוי בעלי האירוע, תוויות צד, ניסוח "החתונה"/
  "האירוע" וכו'). קומפוננטה/הודעה **אף פעם לא** מקבעת "חתן/כלה" ישירות —
  קוראת ל-Lexicon. הוספת סוג אירוע חדש = רשומה אחת בכל Lexicon, בלי לגעת
  במסכים. פירוט כללי הניסוח (דקדוק `celebration`/`celebration_construct`)
  ב-`decisions.md`; כללי קופי מלאים ב-`brand.md`.
- **רצף תקשורת מודע-סוג-אירוע:** `MessageDefault` (טבלת DB, לא קובץ קוד) —
  שורה אחת לכל event_type×message_type (48 בסך הכול). ראה סעיף ייעודי
  "תקשורת עם אורחים" למעלה. **מחליף** את `message_library.py` הישן (הוסר
  לגמרי ב-2026-08-05, ראה `decisions.md`).
- **טקסונומיית קבוצות מודעת-סוג-אירוע:** `group_options`/`groupOptions`
  בלקסיקון (שני הצדדים) — רשימת קבוצות שונה לכל `event_type` (למשל עסקי:
  עובדים/לקוחות/ספקים/הנהלה/שותפים; בר/בת מצווה: משפחת אב/אם/כיתה/צוות).
  משפיע על טופס הוספת מוזמן, ייבוא (`importer.py: GROUP_VALUE_MAP`),
  וסטטיסטיקות (`routers/stats.py`). `group_type` עצמו נשאר `str` חופשי
  ב-DB — לכן הוספת/שינוי טקסונומיה היא שינוי לקסיקון בלבד, לא מיגרציה.
- **מנוע ההושבה מודע-event_type (עדין):** `seating.py:
  SEATING_WEIGHTS_BY_EVENT_TYPE` — משקלי "אותו צד"/"אותה קבוצה" יכולים
  להשתנות לפי סוג אירוע (למשל `business` מדגיש קבוצה על פני צד). ברירת
  המחדל לכל סוג שלא הוגדר לו במפורש = בדיוק כמו חתונה, כדי לא לפגוע
  בחוויית החתונה הקיימת. חוקים קשיחים (קיבולת/זוגות אסורים) **לא**
  משתנים לפי סוג — נשארים אוניברסליים.
- **פאנל אדמין מודע-event_type:** `AdminEventRow`/`AdminDashboardEvent`
  (`schemas.py`) חושפים `event_type` + `hosts` (בנוי דרך
  `event_terms.hosts_names()`, לא groom/bride גולמי); לוח הבקרה כולל
  פילוח `events_by_type`. מסך "כל האירועים" תומך סינון/חיפוש לפי סוג.

### איך מוסיפים סוג אירוע חדש (Step-by-step)
הוספת סוג אירוע ל-VEYA **לא דורשת שינוי סכימה ולא נגיעה במסכים** — רק
עדכון הלקסיקון בשני הצדדים:
1. **Backend** — `backend/app/event_terms.py`: הוסיפו רשומת `EventTerms`
   חדשה ל-`EVENT_TERMS` (label/hosts_label/side_groom/side_bride/
   celebration/celebration_construct/guests_label/gift_label/
   group_options). עדכנו את ה-`Literal["wedding", ...]` ב-`schemas.py`
   (`EventType`) ובמודל אם צריך ולידציה נוספת.
2. **Frontend** — `frontend/src/strings/eventTypes.ts`: הוסיפו רשומה
   מקבילה ל-`EVENT_TERMS` ופריט ל-`EVENT_TYPE_OPTIONS` (הבורר ביצירת
   אירוע). ודאו ש-`groupOptions` תואם בדיוק לצד ה-backend.
3. **(אופציונלי) 6 ברירות מחדל לתקשורת עם אורחים** — הוסיפו 6 שורות
   `MessageDefault` (event_type=הסוג החדש, message_type=כל אחד מ-6
   הסוגים הקבועים) דרך `/admin/message-defaults`. אם מדלגים, האירוע עדיין
   מקבל 6 שורות `EventMessage` ריקות (title בלבד) — לא שגיאה, פשוט אין
   תוכן ברירת מחדל לסוג הזה עד שיוזן.
4. **(אופציונלי) משקלי הושבה ייעודיים** — `seating.py:
   SEATING_WEIGHTS_BY_EVENT_TYPE`: רק אם יש סיבה מוצרית ברורה לסטות
   מברירת המחדל (=חתונה).
5. **בדיקה:** צרו אירוע מהסוג החדש בדפדפן ועברו על כל ה-flow (דשבורד →
   מוזמנים → קבוצות → הודעות → הזמנה → הושבה → RSVP) — ודאו שאין טקסט
   "חתן/כלה/זוג" דולף. שום קובץ אחר לא אמור להזדקק לעריכה.

### מה אסור לעשות (Event-first — כללי ברזל)
- **אסור** לבנות מסך/רכיב/endpoint נפרד לכל סוג אירוע — תמיד שכבת
  התאמה מעל מערכת אחת (`event_type` + Lexicon), לעולם לא הסתעפות קוד.
- **אסור** לקבע "חתן"/"כלה"/"זוג"/"חתונה" כטקסט קשיח בשום מסך, הודעה,
  placeholder, tooltip, empty state, הודעת הצלחה/שגיאה — תמיד דרך
  `activeEventTerms()` / `event_terms.get_event_terms()`.
- **אסור** להניח שברירת המחדל היא חתונה בלוגיקה (רק כברירת מחדל
  מפורשת בפרמטר/שדה, לתאימות אחורה — לא כהנחה שקטה).
- **מותר ובטוח** להשאיר שמות שדה פנימיים (`groom_name`/`bride_name`/
  `Side = 'groom'|'bride'|'shared'`) כפי שהם — אלה מפתחות טכניים
  שמוצגים תמיד דרך הלקסיקון; שינוי שמם הוא מיגרציה מיותרת בלי תועלת
  משתמש (`decisions.md`).

## אינטגרציות חיצוניות (מפת תלויות)
כל שירות חיצוני = נקודת תלות וסיכון (`risk-register.md`) ועלות (`business-model-finance.md`).
| שירות | תפקיד | מצב |
|---|---|---|
| Meta WhatsApp Cloud API | הזמנות/RSVP/תזכורות | קוד קיים, `mock` |
| ספק LLM (API חיצוני) | פרסור טקסט/שיח | לפי `ai-guidelines.md` |
| Supabase (Postgres) | DB ייצור | פעיל |
| Vercel / Render | אירוח frontend/backend | פעיל |
| ספק סליקה ישראלי | מתנות באשראי | עתידי `[לאימות]` — `roadmap.md` |
עיקרון: גבול כל אינטגרציה מצומצם בכוונה כדי שתהיה **ניתנת להחלפה** (`ai-guidelines.md`).

## ביצועים (Performance)
ביצועים = חלק מחוויית פרימיום (`product-principles.md`), לא רק "מדד טכני".
- **יעד:** טעינה מהירה במובייל ברשת סלולרית; אין הבזק לבן (`design-system.md`).
- **נקודות תשומת לב ידועות:** קבצים ענקיים (`HallPage.tsx`, `App.css`),
  SPA יחיד בלי code-splitting, אחסון תמונות ב-DB (`media_blobs`).
- `[לאימות]` תקציב ביצועים מספרי (Core Web Vitals) טרם נקבע — `open-questions.md`.

## בדיקות ואיכות (QA)
- **מצב היום:** אין בדיקות אוטומטיות ואין CI (חוב ידוע — `product-state.md`).
- **עדיפות ראשונה כשנוסיף:** בדיקות למנוע ההושבה (דטרמיניסטי → קל לבדוק,
  קריטי לנכונות) ולזרימת RSVP. מנוע ההושבה הוא הקניין — regression בו = כשל מוצר.
- כל שינוי בחוקים הקשיחים (`seating-engine.md`) חייב בדיקה שמוודאת 0 הפרות.

## שיקולי CTO קבועים (סדר חשיבה 5–10 ב-SKILL.md)
לפני קוד: איפה זה יושב במפה למעלה? תואם לדפוסים הקיימים? השפעה על ביצועים/DB?
קלט משתמש מאובטח (נתוני מוזמנים = מידע אישי)? מחזיק ב-10K זוגות? החלטות
משמעותיות → `decisions.md`.
