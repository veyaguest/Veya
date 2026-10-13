# WhatsApp ב-VEYA — חיבור ל-Meta Cloud API

> מסמך חי. מעודכן לשלב 3 (2026-10-12): לקוח Meta, Templates, תוצאה לא ידועה,
> השלמה מ-webhook, הודעות חופשיות, כלי `hello_world`.
> חלקים שעוד לא נבנו מסומנים **(יושלם בשלב N)**. השרת החי נמצא במצב `mock`.

## איך זה בנוי

```
מסלול אישורי ההגעה (rsvp_timeline / communication / rsvp_scheduler)  ← לא יודע כלום על Meta
        ↓
outbound.send_batch       — accepts? → רישום pending → שליחה → עדכון; נעילה לאירוע
        ↓
messaging.get_provider()  — Mock / TestRecipientGuard(Meta) / Meta / Stopped
        ↓
whatsapp_templates        — שלב במסלול → Template מאושר (היום: ריק)
whatsapp_meta             — הבקשה ל-Meta, ניסיונות חוזרים, "לא ידוע"
        ↓
Meta Cloud API (graph.facebook.com/v26.0)

Meta webhook → /messaging/webhook → whatsapp_inbound (שיוך, RSVP, הודעה חופשית)
                                  → message_status (מסירה, השלמת pending)
```

| קובץ | אחריות |
|---|---|
| `backend/app/messaging.py` | מצב השליחה, בחירת הספק, רשימת הנמענים המורשים, `MetaProvider` |
| `backend/app/whatsapp_meta.py` | **המקום היחיד** שמדבר עם Meta: הגדרות, Template, ניסיונות חוזרים, `hello_world` |
| `backend/app/whatsapp_templates.py` | מיפוי שלב → Template מאושר |
| `backend/app/outbound.py` | כל שליחה יוצאת: סינון, רישום `pending`, שליחה, עדכון |
| `backend/app/message_status.py` | סטטוסים, עדכוני מסירה, השלמת הודעה תקועה (`reconcile_pending`) |
| `backend/app/whatsapp_inbound.py` | שיוך הודעה נכנסת למוזמן; תשובת RSVP; הודעה חופשית |
| `backend/app/routers/messaging.py` | ה-webhook (אימות חתימה, עיבוד פריט-פריט) |
| `backend/app/http_security.py` | הסתרת `hub.verify_token` מלוג uvicorn |
| `backend/scripts/whatsapp_hello_world.py` | כלי בדיקה ידני |

## מצבי שליחה — `WHATSAPP_MODE`

| ערך | מה קורה |
|---|---|
| `mock` (ברירת מחדל) | שום הודעה לא יוצאת. נרשמת ביומן כ"נשלחה" לצורך בדיקת הזרימה |
| `meta_test` | שליחה אמיתית דרך Meta **רק** לטלפונים שב-`WHATSAPP_TEST_RECIPIENTS` |
| `meta` (או `live`) | שליחה אמיתית לכל המוזמנים. **רק באישור מפורש של המייסד** |
| חסר / ריק / לא מוכר | `mock` (ערך לא מוכר נרשם בלוג כאזהרה) |

עצירת חירום מהאדמין (`whatsapp.emergency_stop`) גוברת על כל מצב.
המסכים מקבלים `mock` / `meta_test` / `live`.

### `meta_test` — למה הוא בטוח גם מול מסד הייצור
- נמען שאינו ברשימה נחסם **לפני** Meta ו**בלי שורה במסד** (`send_batch` → `accepts`).
- הספק עצמו (`TestRecipientGuard`) בודק שוב בכל שליחה.
- רשימה חסרה/ריקה = הכול חסום. רשימה: פסיק / נקודה-פסיק / שורה חדשה.
- המשימה המתוזמנת לא כותבת יומן כשהכול נחסם.
- `/messaging/invitations/send` ו-`/messaging/reminders/send` מחזירים `409` מחוץ ל-`mock`.

## משתני סביבה

| משתנה | מתי | מאיפה |
|---|---|---|
| `WHATSAPP_MODE` | תמיד | `mock` / `meta_test` / `meta` |
| `WHATSAPP_TEST_RECIPIENTS` | `meta_test` | הטלפונים שלכם, מופרדים בפסיק |
| `WHATSAPP_ACCESS_TOKEN` | `meta_test` / `meta` | Meta (System User לשימוש מתמשך; הזמני פג אחרי 24 שעות). השם הישן `WHATSAPP_TOKEN` עובד |
| `WHATSAPP_PHONE_NUMBER_ID` | `meta_test` / `meta` | מזהה המספר השולח. השם הישן `WHATSAPP_PHONE_ID` עובד |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | אופציונלי | מזהה ה-WABA (לא בשימוש בקוד עדיין) |
| `WHATSAPP_VERIFY_TOKEN` | webhook | מחרוזת שאתם ממציאים ומזינים גם ב-Meta |
| `WHATSAPP_APP_SECRET` | webhook | App Settings ← Basic. בלעדיו כל webhook נדחה (403) |
| `WHATSAPP_GRAPH_API_VERSION` | אופציונלי | ריק = `v26.0` (`v20.0` פג ב-24.9.2026) |
| `WHATSAPP_INBOUND_RSVP` | אופציונלי | `1` = לחיצת כפתור ב-WhatsApp מעדכנת RSVP. **כבוי** — לא מדליקים בלי החלטה |

**איפה מגדירים מקומית:** `backend/.env` (מוחרג מ-git — לבדוק: `git check-ignore -v backend/.env`).
`backend/.env.example` מכיל רק שמות, אף פעם לא ערכים. בייצור (Render) — לא נוגעים בלי אישור.

**בלי סודות בלוגים:** הקוד לא מדפיס טוקן, סוד, טלפון מלא או תוכן הודעה. הטוקן מוסר
גם מכל טקסט שגיאה של Meta לפני שהוא נשמר (`_scrub`). `hub.verify_token` מוסתר מלוג
הגישה של uvicorn (`RedactSecretsFilter`) — האימות עצמו לא משתנה.

## שליחה — שלוש תוצאות

| תוצאה | מתי | סטטוס בשורה |
|---|---|---|
| נשלחה | Meta החזירה מזהה הודעה (`wamid`) | `sent` (+ `provider_status`: accepted / held_for_quality_assessment / paused) |
| נכשלה | Meta החזירה שגיאה | `failed` + `failure_code` + תיאור קצר |
| **לא ידוע** | timeout אחרי שהבקשה יצאה, ניתוק, 2xx בלי מזהה, 5xx בלי גוף של Meta, חריגה לא צפויה | `pending` + `provider_status=send_outcome_unknown` + הסבר |

**ניסיון חוזר** — רק כשבטוח ש-Meta לא קיבלה: כשל התחברות לפני שהבקשה יצאה, או קוד
ש-Meta מגדירה זמני (4, 80007, 130429, 131000, 131016, 2494100). עד 3 ניסיונות, המתנה 1s ואז 3s.
**לא** חוזרים על: timeout ("לא ידוע"), טוקן/הרשאה (0, 190, 200…), Template (132xxx),
131026, 131050, 131049/131056 (Meta מבקשת לחכות שעות).

## Templates

Meta שולחת ביוזמתנו רק Template מאושר. הנוסח שבעלי האירוע עורכים **לא** נשלח כמו שהוא
במצבי Meta — `whatsapp_templates.TEMPLATES` קובע מה נשלח בכל שלב.

**היום הרשימה ריקה.** לכן במצבי Meta שום שלב לא נשלח — לא נרשם, לא נחשב כאילו נשלח,
והסבב לא "נשרף": כשהתבנית תאושר ותתווסף, הסבב יוצא אם החלון שלו עדיין פתוח.
אותו דבר כשחסר ערך למילוי (למשל טוקן אישי) — Meta הייתה דוחה ממילא.

ביומן ההודעות נרשם מה שבאמת יצא: `[Template <name>] <ערכים>` — בלי הטוקן האישי.

הנוסחים, יצירתם ב-Meta, ואיך מציגים לזוג את הנוסח המאושר — **(אחרי אישור הטקסטים)**.

## הודעות שהתוצאה שלהן לא ידועה (`pending`)

### מאיפה הן מגיעות
1. השרת נפל בין הרישום לבין השליחה/העדכון.
2. Meta לא ענתה (timeout וכו') — `provider_status=send_outcome_unknown`.

### מה המערכת עושה
- **אף מסלול אוטומטי לא שולח אותה שוב** (המשימה המתוזמנת, השליחה מהתור, שליחת
  הזמנות של בעלי האירוע). רק אדמין-על, בפעולה ידנית ומכוונת.
- **השלמה אוטומטית מ-webhook:** כל הודעה יוצאת ל-Meta עם
  `biz_opaque_callback_data = veya:m<שורה>:e<אירוע>:g<מוזמן>`. לפי התיעוד של Meta
  (נבדק 2026-10-12) השדה חוזר כמו שנשלח בעדכוני הסטטוס של אותה הודעה, ורק אם שלחנו
  אותו; התיעוד לא מתחייב באילו סטטוסים — ולכן לא מניחים סטטוס מסוים.
  השורה נסגרת **רק אם כל התנאים מתקיימים:** הפורמט שלנו בדיוק · השורה יוצאת, מ-Meta,
  עדיין `pending`, בלי מזהה · אירוע ומוזמן תואמים · הטלפון של המוזמן = `recipient_id` ·
  מזהה ה-Meta לא שייך לשורה אחרת. אחרת — לא נוגעים.
- אם Meta לא קיבלה את ההודעה בכלל, לא יגיע עדכון והשורה תישאר `pending`.

### איך מוצאים אותן (שאילתה, קריאה בלבד)
```sql
SELECT id, event_id, guest_id, kind, provider_status, created_at
FROM messages
WHERE direction = 'outbound' AND status = 'pending'
  AND created_at < now() - interval '15 minutes'
ORDER BY created_at;
```

### עוד לא נבנה (דורש אישור)
- **רשימה באדמין** — "הודעות במצב לא ידוע" שלא נסגרו אחרי 24 שעות, עם פעולה אחת:
  "סמן כלא נשלחה" (לא שולחת; רק פותחת את הניסיון החוזר הרגיל).
- **מסך המעקב** — להציג אותן כ"בבדיקה" ולא כ"ממתינה לשליחה".

## הודעות נכנסות

**שום הודעה נכנסת לא משנה אישור הגעה** (2026-10-13). אישור הגעה — רק דרך הקישור האישי.

| סוג | מה קורה |
|---|---|
| טקסט חופשי / תמונה / הקלטה… | נשמר ביומן ההודעות כ"דורש טיפול" (`needs_attention`). גם לא "נגיע 3" |
| כפתור `rsvp_yes`/`rsvp_no` (נוסח ישן) | גם הוא נשמר כ"דורש טיפול", בלי לשנות RSVP |
| שולח לא מזוהה / עמימות בין אירועים | שורת יומן אבטחה בלבד, בלי התוכן |

כל הודעה נכנסת נשמרת עם מזהה Meta שלה — webhook חוזר לא יוצר כפילות.

עדכון RSVP מלחיצת כפתור (שיוך חד-משמעי, חלון אישורי ההגעה, `rsvp_response`, יומן
פעילות) קיים ונבדק, אבל רץ רק עם `WHATSAPP_INBOUND_RSVP=1` — כבוי כברירת מחדל,
ולא מדליקים בלי החלטה מפורשת.

## ה-webhook — מה נבדק לפני בדיקה חיצונית

| מה | איך |
|---|---|
| אימות GET | רק `hub.mode=subscribe` עם `WHATSAPP_VERIFY_TOKEN` המדויק (השוואה בזמן קבוע). בלי הגדרה — 403 |
| חתימה (POST) | HMAC-SHA256 עם `WHATSAPP_APP_SECRET` על הגוף הגולמי. בלי סוד — 403. כותרת פגומה — 403 (לא 500) |
| גודל | עד 3MB (התקרה של Meta), נבדק לפני החתימה — גם בלי `Content-Length`. מעבר לזה — 413 |
| עיבוד | כל פריט בטרנזקציה משלו; כשל DB זמני — 500 ו-Meta שולחת שוב; פריט לא צפוי — מדולג, 200 |
| כפילויות | הודעה נכנסת — לפי מזהה Meta; סטטוס — בלי נסיגה, ועדכון זהה שומר את הזמן המקורי |
| אישור הגעה | עדכוני סטטוס נוגעים רק בשורת ההודעה — לעולם לא באורח |
| לוג | בלי טוקן, סוד, טלפון, תוכן הודעה או `wamid` |

## כלי בדיקה ידני — `hello_world`

שולח את תבנית `hello_world` של Meta (קיימת בכל חשבון בדיקה) — בלי מסד, בלי אורחים.
```bash
cd backend
venv/bin/python scripts/whatsapp_hello_world.py                  # מצב ההגדרות (מוגדר/חסר)
venv/bin/python scripts/whatsapp_hello_world.py --to 05XXXXXXXX  # בדיקת תנאים, בלי שליחה
venv/bin/python scripts/whatsapp_hello_world.py --to 05XXXXXXXX --send
```
שולח רק כש**כל** התנאים מתקיימים: `WHATSAPP_MODE=meta_test` · `VEYA_ENV` אינו
`production` · עצירת חירום כבויה · הנמען ברשימה המורשית (שלנו) · טוקן ומזהה מספר מוגדרים.
מספר בדיקה של Meta שולח רק לנמענים שאושרו גם בדשבורד של Meta (עד 5).

## בדיקות

```bash
cd backend
venv/bin/python -m pytest -q tests/test_whatsapp_safety.py tests/test_whatsapp_meta_test_mode.py \
    tests/test_whatsapp_meta_api.py tests/test_webhook_signature.py tests/test_message_status.py
venv/bin/python -m pytest -q tests/test_whatsapp_postgres.py     # Postgres זמני + RLS (pgserver)
VEYA_META_INTEGRATION=1 venv/bin/python -m pytest -q tests/test_whatsapp_meta_integration.py  # אמיתי
```
כל הבדיקות מלבד האחרונה עובדות מול Meta מזויפת, בלי רשת. האחרונה מדולגת תמיד, אלא
אם מפעילים אותה במפורש — ואז היא שולחת רק `hello_world` לנמען המורשה הראשון.

## עוד לא כאן

- כתובת webhook ציבורית לבדיקה מקומית, והגדרת ה-webhook ב-Meta — **(שלב 5, באישור)**
- נוסחי Templates ויצירתם — **(אחרי אישור הטקסטים)**
- בדיקה מקצה לקצה עם מספר הבדיקה — **(שלב 5)**
- מעבר ל-`meta`, החלפת credentials, בדיקת כשלי מסירה, rollback — **(שלב 6)**
