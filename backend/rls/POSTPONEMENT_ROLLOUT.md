# נוהל דחייה · הפעלת RLS בייצור

מסמך קצר ומעשי לקובץ `15_postponement_rls.sql` בלבד. התוכנית הרחבה של
הפעלת RLS על כל המערכת נמצאת ב-`PRODUCTION_ROLLOUT.md` — והיא **עדיין לא
בוצעה**, מסיבה שמתועדת למטה.

---

## מה הקובץ עושה, ומה הוא לא עושה

**עושה:** מפעיל RLS על שלוש טבלאות נוהל הדחייה ויוצר עליהן 10 מדיניות:

| טבלה | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| `postponement_requests` | ✓ | ✓ | ✓ | ✓ |
| `event_cycles` | ✓ | ✓ | — | ✓ |
| `guest_cycle_rsvp` | ✓ | ✓ | — | ✓ |

היעדר ה-UPDATE על שתי טבלאות ההיסטוריה הוא **מכוון**: היסטוריה שאפשר לערוך
אינה היסטוריה.

**לא עושה:** אין בקובץ `INSERT`, `UPDATE`, `DELETE`, `DROP TABLE`,
`ALTER COLUMN` או `TRUNCATE`. הפעולות היחידות הן `ALTER TABLE ... ENABLE
ROW LEVEL SECURITY`, `DROP POLICY IF EXISTS` + `CREATE POLICY`, ו-`GRANT`.
**אין שום מסלול שבו הרצתו פוגעת בנתונים קיימים.**

הקובץ idempotent — הרצה חוזרת מגיעה לאותו מצב בדיוק (נבדק: הורץ פעמיים
ברצף, אותן 10 מדיניות).

## תלויות

`app_manages_event` (קובץ 08) ו-`app_is_admin` (קובץ 01). בלעדיהן
`CREATE POLICY` נכשל בקול. המריץ האוטומטי בודק זאת מראש ומדלג בהודעה
ברורה במקום להשאיר מדיניות חלקית.

---

## איך זה מוחל — אוטומטית, בעליית השרת

`app/main.py::_ensure_rls_policies()` מריץ את הקובץ בכל עליית שרת, דרך
חיבור המיגרציות (superuser), מיד אחרי `create_all`.

**למה אוטומטי, בשונה מקובצי 01–14 שמורצים ידנית:** שלוש הטבלאות נולדות
מ-`create_all` בעליית השרת — כלומר **אחרי** שקובצי ה-RLS הידניים כבר רצו.
בלי צעד בעלייה, כל טבלה חדשה במערכת נולדת לנצח בלי מדיניות. זה בדיוק הפער
שהתגלה כאן: הקוד של נוהל הדחייה כבר בייצור, והטבלאות שלו היו ללא RLS.

- `VEYA_SKIP_RLS_MIGRATIONS=1` מכבה את זה מיד מ-Render, בלי deploy של קוד.
- כישלון לעולם אינו מפיל את עליית השרת — נרשם ללוג בלבד.
- הלוג מדפיס את המצב בפועל, כך שאפשר לאמת מ-Render בלי להתחבר ל-DB:

```
[veya:rls] הוחל: 15_postponement_rls.sql
[veya:rls] מצב → event_cycles: rls=on policies=3 · guest_cycle_rsvp: rls=on policies=3 · postponement_requests: rls=on policies=4
```

**הרצה ידנית חלופית:** להדביק את הקובץ ב-Supabase SQL Editor. הקובץ נשמר
נקי מסימני אחוז בכוונה, כדי שיהיה תקין גם דרך SQL Editor וגם דרך מריץ
פייתון (psycopg2 מפרש `%` כ-placeholder ומפיל קובץ שמכיל אותו — זה הפיל
בפועל את קבצים 11 ו-13 בהרצה דרך קוד).

בסוף הקובץ יש בלוק שאילתות אימות (קריאה בלבד) להעתקה.

---

## מה נבדק בפועל

Postgres אמיתי מקומי (`pgserver`), סכימה מלאה מ-`create_all`, כל קובצי
RLS 01–15, והסכימה יושרה לצורת הייצור (עמודות שנוספו דרך `_EXTRA_COLUMNS`
הן nullable בייצור).

`tests/test_postponement_rls_postgres.py` — **42 בדיקות, 0 כשלים**, מול
שרת חי: נעילה, בקשה, הפרדת סמכויות, אישור, עריכה מלאה, הודעת דחייה,
מחזור חדש, ארכיון, RSVP במחזור החדש, דחייה שנייה, דחיית בקשה, ובידוד בין
אירועים. כולל בדיקה שבעלי אירוע **אינם** יכולים לאשר לעצמם דחייה בעקיפה
ישירה ב-DB — מדיניות ה-UPDATE חוסמת זאת (0 שורות עודכנו).

---

## ‼️ מה שהבדיקה חשפה: RLS מלא עדיין לא ניתן להפעלה

**זה לא נוגע לקובץ 15, והוא בטוח להתקנה. זה חוסם את שלב ג' של
`PRODUCTION_ROLLOUT.md` — המעבר של `DATABASE_URL` לתפקיד `veya_app`.**

כשהאפליקציה רצה כ-`veya_app` (כלומר RLS נאכף באמת), **יצירת אירוע נכשלת**:

```
POST /events → 500
new row violates row-level security policy for table "event_messages"
```

**הסיבה:** `app/auth.py::get_current_user` הוא `def` סינכרוני, ולכן FastAPI
מריץ אותו ב-threadpool. `set_request_identity()` שם קובע `ContextVar`
בהקשר **המועתק** של אותו worker — והוא אינו מגיע לפונקציית ה-endpoint,
שרצה בקריאת threadpool אחרת.

עד היום זה עבד במקרה: הטרנזקציה הראשונה נפתחת *בתוך* ה-dependency עצמו
(`db.get(models.User, ...)`) ונשארת פתוחה לכל אורך הבקשה, כך שהזהות שהוזרקה
בה תקפה. אבל כל endpoint שעושה `db.commit()` ואז ממשיך לעבוד מול ה-DB פותח
טרנזקציה **שנייה** — ובה `after_begin` קורא `current_user_id.get()` ומקבל
`None`.

הוכחה (מאזין זמני שמדפיס את הזהות בכל `after_begin` במהלך `POST /events`):

```
[spy] after_begin · uid = 8      ← טרנזקציה 1, מתוך ה-dependency
[spy] after_begin · uid = None   ← טרנזקציה 2, אחרי commit → RLS חוסם
```

`app_create_event` שורד כי הוא `SECURITY DEFINER` ועוקף RLS; מיד אחריו
`provision_event_messages` נופל.

**מה זה אומר:**

1. **בייצור כרגע RLS אינו נאכף** — אחרת יצירת אירוע הייתה שבורה לכולם.
   כלומר `DATABASE_URL` עדיין מצביע ל-`postgres` (superuser).
2. התקנת קובץ 15 בייצור **אינה משנה התנהגות כלל** במצב הזה (superuser עוקף
   RLS), ולכן היא בטוחה. היא מכינה את הקרקע.
3. שלב ג' חסום עד שהבאג הזה מתוקן. הכיוון: להפוך את `get_current_user`
   ל-`async def`, או להזריק את הזהות ב-middleware במקום ב-dependency.
   **לא תוקן כאן** — זה נוגע ללב מנגנון האימות, ומגיע לו סבב משלו.

---

## נספח: הקמת Postgres מקומי לבדיקה (בלי Docker)

```bash
pip install pgserver
python -c "import pgserver; s = pgserver.get_server('/tmp/pgdata'); print(s.get_uri())"
```

התהליך שמחזיק את השרת חייב להישאר חי. אחר כך: `create_all` על ה-URI,
הרצת `rls/01`–`rls/15`, יישור העמודות של `_EXTRA_COLUMNS` ל-nullable
(כך הן בייצור), והרמת uvicorn עם `DATABASE_URL` מוצבע לשם.
