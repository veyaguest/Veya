# VEYA · תוכנית בדיקת RLS על סביבת Staging (לפני ייצור)

**מצב: שלב זה עוסק אך ורק בסביבת staging — פרויקט Supabase נפרד, לא זה של
הייצור. שום פעולה כאן לא נוגעת ב-`DATABASE_URL` של הייצור או במסד הנתונים
האמיתי. RLS יופעל **רק** על ה-staging.**

מסמך זה הוא ה"איך בדיוק" — הצ'קליסט המלא ב-[RLS_REPORT.md](RLS_REPORT.md#שלב-5--צקליסט-מוכנות-לייצור)
כבר מתאר את זה ברמת סעיפים; כאן הפירוט המבצעי, פקודה-פקודה.

---

## שלב 0 — למה בכלל צריך staging נפרד (ולא רק להריץ RLS זמנית בייצור)

RLS+FORCE שכבר קיים ב-DB **לא משפיע** כל עוד השרת מחובר כ-`postgres`
(superuser עוקף RLS לגמרי — ראו הסבר בשלב 4 ב-RLS_REPORT.md). כדי לבדוק
את RLS *באמת*, צריך לחבר אפליקציה בתפקיד `veya_app` (לא-superuser) למסד
נתונים אמיתי — וזה בדיוק השינוי שאסור לעשות על הייצור לפני שהוא אומת. לכן:
פרויקט Supabase נפרד לגמרי, עם עותק של הסכימה, שאפשר "לשבור" בלי סיכון.

## שלב 1 — יצירת פרויקט Staging ב-Supabase

1. ב-Supabase Dashboard → **New Project**. שם מוצע: `veya-staging`.
   אזור (Region): כדאי לבחור את אותו אזור כמו הייצור (ביצועים דומים,
   לא קריטי לבדיקה עצמה).
2. שמרו את ה-**Connection String** (`postgres://postgres:[password]@...`)
   שסופאבייס נותן — זה חיבור ה-superuser של ה-staging, נחוץ לשלבים הבאים.
   **זה שונה לגמרי מהסיסמה של הייצור — פרויקט חדש = superuser חדש.**

## שלב 2 — שכפול הסכימה (בלי נתונים אמיתיים של לקוחות)

יש שתי דרכים אפשריות — מומלץ **אפשרות ב'**, כי היא לא נוגעת בכלל בייצור:

**אפשרות א' (לא מומלצת לשלב הזה):** `pg_dump --schema-only` מהייצור +
`psql` ל-staging. דורשת גישת רשת לייצור — מיותר כשיש דרך פשוטה יותר.

**אפשרות ב' (מומלצת):** להריץ את השרת המקומי (`backend/`) מול ה-staging
DB, עם `DATABASE_URL` מוצבע על ה-connection string מ-Supabase (עדיין
כ-`postgres`, superuser, באופן זמני). עליית השרת (`on_startup` ב-
`app/main.py`) יוצרת את כל הטבלאות אוטומטית (`Base.metadata.create_all`)
+ מריצה זריעת ברירות מחדל (תבניות/משתמש אדמין). כלומר: staging ריק
מקבל סכימה תקינה פשוט ע"י הרצת השרת מולו פעם אחת.

```bash
cd backend
source venv/bin/activate
export DATABASE_URL="postgres://postgres:[staging-password]@[staging-host]:5432/postgres"
uvicorn app.main:app --reload
# בדקו שהשרת עלה בלי שגיאות (טבלאות נוצרו), ואז Ctrl+C לעצור.
```

**חשוב:** אין כאן נתוני מוזמנים/אורחים אמיתיים — staging מתחיל ריק
לחלוטין ומאוכלס רק בנתוני-בדיקה שניצור בעצמנו בשלב 6.

## שלב 3 — הרצת קובצי ה-RLS על ה-Staging

עדיין מחוברים כ-`postgres` ל-staging (Supabase SQL Editor, או `psql`):

1. פתחו את `backend/rls/01_helpers_and_grants.sql`, **החליפו את
   `'CHANGE_ME_STRONG_PASSWORD'`** בסיסמה חזקה (רק ל-staging — לא לשמור
   באותו מקום כמו סיסמת ה-production `veya_app` העתידית), והריצו את כל
   הקובץ ב-SQL Editor.
2. הריצו את `backend/rls/02_policies.sql` במלואו.
3. ודאו שאין שגיאות. שני הקבצים idempotent — אפשר להריץ שוב בבטחה.

בדיקת עשן מהירה ב-SQL Editor (עדיין כ-postgres, אז אמור להראות הכול):
```sql
select tablename, rowsecurity, forcerowsecurity
from pg_tables t join pg_class c on c.relname = t.tablename
where schemaname='public' and rowsecurity;
```
צריך להראות את כל 10 הטבלאות המוגנות עם `rowsecurity=true`.

## שלב 4 — מעבר לתפקיד המוגבל `veya_app`

זה הרגע שבו RLS **מתחיל להשפיע בפועל** — ורק על ה-staging:

```bash
export DATABASE_URL="postgres://veya_app:[staging-veya_app-password]@[staging-host]:5432/postgres"
export MIGRATIONS_DATABASE_URL="postgres://postgres:[staging-postgres-password]@[staging-host]:5432/postgres"
uvicorn app.main:app --reload
```

השרת אמור לעלות בהצלחה (המיגרציות/הזריעה רצות דרך `MIGRATIONS_DATABASE_URL`,
כלומר כ-superuser — ראו `app/database.py`). אם השרת נופל כאן, זה עצמו ממצא
לתיעוד בדוח הבדיקה (שלב 7 למטה) — לא ממשיכים לפני שמבינים למה.

## שלב 5 — נתוני בדיקה

ריצה אחת של סקריפט הבדיקה האוטומטי (ראו `backend/tests/test_staging_rls.py`,
שנבנה במשימה הזו) יוצרת בעצמה את כל המשתמשים/אירוע/מוזמנים/חברי-אירוע
הדרושים לבדיקה, ומנקה אחריה. אין צורך להזין נתונים ידנית.

## שלב 6 — הרצת הבדיקה האוטומטית המלאה

```bash
export STAGING_BASE_URL="http://localhost:8000"   # השרת מהשלב הקודם, רץ מול veya_app
export STAGING_ADMIN_DB_URL="postgres://postgres:[staging-postgres-password]@[staging-host]:5432/postgres"
python tests/test_staging_rls.py
```

הסקריפט מריץ את כל תרחישי הבדיקה (שלב 6 בבקשה שלך — בעלים/אדמין/מפיק/אולם/
מוזמן/webhook/הושבה/הזמנות/הודעות/מדיה), ומדפיס דוח PASS/FAIL לכל תרחיש.

## שלב 7 — דוח בדיקה

תוצאות ההרצה מתועדות ב-`backend/rls/STAGING_TEST_REPORT.md` (נוצר/מתעדכן
אוטומטית ע"י הסקריפט + סיכום ידני). קריטריון למעבר לשלב הבא: **0 כשלים
קריטיים** (גישה לא-מורשית שעברה, או פעולה לגיטימית שנחסמה).

## שלב 8 — לאחר הצלחה מלאה

רק אם כל הבדיקות עברו: עוברים למסמך [PRODUCTION_ROLLOUT.md](PRODUCTION_ROLLOUT.md)
(ייווצר בנפרד, ורק בשלב הזה) — תוכנית ההפעלה בייצור, שעדיין מחכה לאישור
מפורש נוסף לפני כל פעולה על הייצור עצמו.

## מה אני (Claude) לא יכול לעשות לבד

אין לי גישה לחשבון ה-Supabase שלך ואין לי כלי ליצור פרויקט Supabase
בעצמי — שלבים 1-2 (יצירת הפרויקט, קבלת ה-connection string) דורשים
פעולה שלך בדשבורד. ברגע שיש connection string ל-staging (רצוי כמשתנה
סביבה, לא מודבק בצ'אט בטקסט גלוי), אני יכול להריץ בעצמי את שלבים 3-7 —
כולל התחברות ישירה ל-DB והרצת כל הבדיקות — בלי לגעת בייצור.
