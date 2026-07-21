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
  `message_library.py` · `rsvp_timeline.py` · `rsvp_track.py` · `venues.py` · `invitations.py`.
- `routers/` — endpoint לכל תחום, prefixים: `/auth` `/admin` `/events`
  `/events/{id}/members` `/guests` `/guests/import` `/seating` `/constraints`
  `/messaging` `/stats` `/event` `/hall` `/confirm` `/automation` `/venues` `/media`.

## מפת קוד — Frontend (`frontend/src/`)
- `App.tsx` — שורש, ניתוב עמודים ידני, מצב אדמין/התחזות, טעינת אירוע.
- `api.ts` — קריאות ל-backend · `authStore.ts` — טוקן/eventId ב-localStorage ·
  `types.ts` · `readiness.ts` · `seatingAdvisor.ts`.
- `strings/he.ts` — **מקור אמת יחיד לטקסטים בעברית** (קול המותג).
- `components/` — מסך לכל תחום: `DashboardPage` `GuestsPage` `RsvpPage`
  `HallPage` `ConfirmPage` `AdminApp/AdminPage` `OnboardingWizard` +
  דיאלוגים/פאנלים (Import, Automation*, MessageBuilder, PrepWizard,
  SmartAssistantPanel, VenueAutocomplete ועוד).
- מערכת עיצוב: `App.css` (~9,300 שורות, design tokens ב-`:root`) — ראה `design-system.md`.

## מודל נתונים (עיקרי)
`User` (owner/admin, account_type couple/planner/venue) → `Event` (פרטי חתונה,
מפת אולם JSON, תבנית הודעה, מסלול RSVP) → `Guest` (מקור אמת: צד/קבוצה/כמות/
הערות/טוקן אישי/confirmed_count/is_child). סביבם: `Message`, `MessageTemplate`,
`AutomationRule`, `Clarification`, `EventMember`, `AuditLog`, `LoginEvent`,
`Venue`, `MediaBlob`, `VeyaTemplate`, `VeyaWorkflowStep`. פרטים מלאים ב-`models.py`.

## עקרונות ארכיטקטוניים נעולים
- **הפרדת AI:** LLM לפרשנות/שיח בלבד; חישוב השיבוץ **דטרמיניסטי**. ראה `decisions.md`.
- **מודל "תור לאישור":** אוטומציות מחשבות מה הגיע זמנו; שום דבר לא נשלח בלי
  אישור מפורש של הבעלים.
- **מיגרציות:** כרגע ידניות ב-`main.py`. מעבר ל-Alembic הוא חוב ידוע.
- **Event-ready — `event_type` הוא מקור ההתאמה המרכזי (🔒 `decisions.md`):**
  שדה `event_type` על `Event` (ברירת מחדל `"wedding"`) הוא ה-**single source
  of truth** לכל התאמה תלוית-סוג-אירוע — לוגיקה ושפה כאחד. אף מסך לא מחליט
  "זו חתונה" על סמך הנחה מקומית; הכול נשען על השדה הזה.
- **שכבת Lexicon מרכזית** (לא לפזר טקסטים קשיחים במסכים): `frontend/src/
  strings/eventTypes.ts` (`getEventTerms()`, נשען על `getActiveEventType()`)
  ו-`backend/app/event_terms.py` (`EVENT_TERMS` dict) הם **מקור האמת היחיד**
  לכל טקסט/תווית תלוית-אירוע (כינוי בעלי האירוע, תוויות צד, ניסוח "החתונה"/
  "האירוע" וכו'). קומפוננטה/הודעה **אף פעם לא** מקבעת "חתן/כלה" ישירות —
  קוראת ל-Lexicon. הוספת סוג אירוע חדש = רשומה אחת בכל Lexicon, בלי לגעת
  במסכים. פירוט כללי הניסוח (דקדוק `celebration`/`celebration_construct`)
  ב-`decisions.md`; כללי קופי מלאים ב-`brand.md`.
- **מאגר הודעות מודע-סוג-אירוע:** `message_library.py: entries_for(event_type)`
  — `wedding` מקבל את `LIBRARY` המלאה (75 תבניות ייעודיות), כל סוג אחר מקבל
  `GENERIC_LIBRARY` משותפת (12 תבניות מבוססות-טוקנים). ראה פער עתידי ב-
  `product-state.md`/`roadmap.md` (מאגר עמוק לכל קטגוריה עדיין לא בנוי).

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
