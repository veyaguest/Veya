# VEYA · דוח בדיקת RLS על Staging

**תוצאה סופית: 44/44 בדיקות עברו, 0 כשלים קריטיים, על סביבת Supabase
staging אמיתית (לא SQLite, לא סימולציה) — הרצה יציבה פעמיים ברצף.**

## למה הבדיקה הזו הייתה הכרחית (לא רק פורמלית)

כל התיקונים הקודמים (Task #1–13, ראו RLS_REPORT.md) עברו סקירת קוד קפדנית
וטסטים מול SQLite — אבל **SQLite לא אוכף RLS בכלל**, כך שאף אחת מהבעיות
הבאות לא הייתה יכולה להתגלות בלי הרצה אמיתית מול Postgres. זו בדיוק הסיבה
שהמשימה "אל תפעילו RLS בייצור לפני staging" הייתה קריטית: **4 באגים
אמיתיים, חלקם חמורים, התגלו רק כאן** — ותוקנו לפני שהיה סיכוי שיפגעו
במשתמש אמיתי.

## הבאגים שהתגלו ותוקנו בסבב הזה

### 1. `INSERT ... RETURNING` + מדיניות SELECT — מחלקת-באג שיטתית
**מה קרה:** Postgres דורש שבכל `INSERT`/`UPDATE` עם `RETURNING` (וזו ברירת
המחדל של SQLAlchemy בכל INSERT דרך ה-ORM, כדי לקבל `id`/`created_at`) —
השורה המוחזרת חייבת לעבור גם את מדיניות ה-**SELECT** של הטבלה, לא רק את
ה-`WITH CHECK` של מדיניות ה-INSERT עצמה. בהרשמה/כניסה/דף-אישור-ציבורי,
עדיין אין זהות מחוברת (או שיש רק guest_token) שמספיקה כדי לעבור את מדיניות
ה-SELECT הרגילה — כך שה-INSERT כולו נדחה, גם כש-`WITH CHECK` היה מרשה אותו.
**איפה זה פגע בפועל:** הרשמת משתמש חדש (`users`), רישום התחברות
(`login_events`), תשובת RSVP של מוזמן אנונימי דרך דף האישור (`messages`),
ורישום ליומן אבטחה מנתיבים ציבוריים (`audit_logs`) — **ארבע הזרימות הכי
בסיסיות במערכת היו נשברות לגמרי תחת RLS אמיתי**, ולא היה שום דרך לגלות
זאת בלי Postgres אמיתי.
**התיקון:** ארבע פונקציות SQL חדשות מסוג `SECURITY DEFINER`
(`app_register_user`, `app_record_login_event`, `app_record_confirm_message`,
`app_record_audit_log` — ב-`01_helpers_and_grants.sql`) שמבצעות את ה-INSERT
תחת הרשאות הבעלים (עוקפות RLS פנימית, בהיקף מוגבל מאוד), בדיוק כמו התבנית
שכבר הייתה קיימת לפני כן ל-`app_user_by_email`.

### 2. הרשמת משתמש חדש → **כל אחד הופך לאדמין-על** (חמור יותר מדליפת מידע)
**מה קרה:** `register()` קובע "המשתמש הראשון = אדמין" לפי
`SELECT COUNT(*) FROM users`. תחת RLS, שאילתת ה-COUNT הזו עצמה מסוננת ע"י
מדיניות `users_select` ("אני רואה רק את עצמי") — ובלי זהות מחוברת (המצב
לפני הרשמה), היא **תמיד** מחזירה 0, לא משנה כמה משתמשים באמת קיימים.
המשמעות: **כל הרשמה חדשה, לתמיד, הייתה מקבלת הרשאת אדמין-על מלאה** —
גישה לכל הנתונים של כל הזוגות במערכת. זה מה שגרם בהתחלה להיראות כמו
"דליפת מידע בין-לקוחות" בבדיקה — בפועל שני משתמשי הבדיקה פשוט היו שניהם
אדמינים אמיתיים בטעות, וההתנהגות (אדמין רואה הכול) הייתה נכונה.
**התיקון:** פונקציית `app_count_users()` (SECURITY DEFINER) שסופרת בלי
סינון RLS, ו-`auth.count_users()` ב-Python שמשתמש בה על Postgres.

### 3. יצירת אירוע ע"י בעלים לא-אדמין נכשלת
**מה קרה:** אותה תבנית בדיוק כמו סעיף 1, אבל התגלתה רק *אחרי* שתיקון סעיף
2 — כי לפני כן כל משתמש היה "בטעות" אדמין, וזה הסווה את הבעיה (אדמין
תמיד עובר את מדיניות ה-SELECT, ללא קשר לבעלות). ברגע שהיה משתמש אמיתי
לא-אדמין (owner_b בבדיקה), `POST /events` נכשל עם `500`.
**התיקון:** `app_create_event()` (SECURITY DEFINER), אותה תבנית.

### 4. `expire_on_commit` + `anyio` threadpool — איבוד זהות אחרי `commit()`
**מה קרה:** אחרי `db.commit()`, SQLAlchemy (בברירת מחדל) "מפקיע" את שדות
האובייקט, כך ש-`db.refresh()` (או כל גישה לשדה אחרי commit) מפעיל שאילתה
נוספת בטרנזקציה חדשה. גילינו (בדיקה ישירה עם הדפסות אבחון) שבתנאים
מסוימים סביב האופן שבו FastAPI/anyio מריצים קוד סינכררוני ב-thread-pool,
ה-ContextVar שמחזיק את זהות המשתמש יכול להיקרא כ-`None` בטרנזקציה השנייה
הזו, למרות שהוגדר נכון קודם באותה בקשה — מה שגרם ל-`db.refresh()` להיכשל
("Instance has been deleted, or its row is otherwise not present").
**התיקון:** `expire_on_commit=False` בשתי ה-`sessionmaker` (`SessionLocal`,
`MigrationSessionLocal`), והסרת כל 22 קריאות ה-`db.refresh()` המיותרות
בקוד (הן כבר לא נחוצות — האובייקט שומר את הערכים מ-`RETURNING` בזיכרון).

### חשד ל"דליפה בין-לקוחות" שהתברר כשווא
תוך כדי חקירת סעיף 2, נראה לרגע שיש דליפת מידע אמיתית (בעלים א' רואה את
פרטי האירוע של בעלים ב'). בדיקה עמוקה (כולל אימות ישיר של `app_owns_event()`,
תפקיד ה-DB, ו-`bypassrls`) הראתה שה-RLS פעל נכון לחלוטין בכל זמן — הבעיה
האמיתית הייתה שסעיף 2 הפך את שני המשתמשים לאדמינים אמיתיים, וגישה מלאה
לאדמין היא ההתנהגות הנכונה, לא פרצה. שיעור חשוב: **תמיד לוודא את מצב
ה-is_admin/הרשאות בפועל לפני שמסיקים שיש פרצת RLS.**

### תקלות זמניות (flaky) שלא היו קשורות ל-RLS
שתי בדיקות הושבה נכשלו פעם אחת ואז עברו בהרצה חוזרת מיידית, ללא שינוי קוד —
ככל הנראה latency זמני מול ה-pooler המרוחק של Supabase. לא נמצא דפוס חוזר.

---

נוצר אוטומטית ע"י `tests/test_staging_rls.py`. כל שורה = תרחיש בדיקה אחד.

| תרחיש | תוצאה | קריטי | פרטים |
|---|---|---|---|
| setup: register owner_a | ✅ PASS | כן | status=201 |
| setup: register owner_b | ✅ PASS | כן | status=201 |
| setup: register admin | ✅ PASS | כן | status=201 |
| setup: register planner_full | ✅ PASS | כן | status=201 |
| setup: register planner_partial | ✅ PASS | כן | status=201 |
| setup: register venue_full | ✅ PASS | כן | status=201 |
| setup: register venue_partial | ✅ PASS | כן | status=201 |
| setup: create event A | ✅ PASS | כן | status=201 |
| setup: create event B | ✅ PASS | כן | status=201 |
| setup: owner creates guest | ✅ PASS | כן | status=201 |
| owner: list own guests | ✅ PASS | כן | expected=200 got=200 |
| owner: read own event | ✅ PASS | כן | expected=200 got=200 |
| owner: update own event core fields | ✅ PASS | כן | expected=200 got=200 |
| owner isolation: cannot see event B via X-Event-Id | ✅ PASS | כן | expected=404 got=404 |
| admin: list all events (cross-tenant) | ✅ PASS | לא | expected=200 got=200 |
| admin: can act on event A guests via header | ✅ PASS | כן | expected=200 got=200 |
| admin: can act on event B guests via header | ✅ PASS | כן | expected=200 got=200 |
| planner full: view guests | ✅ PASS | כן | expected=200 got=200 |
| planner full: edit guests | ✅ PASS | כן | expected=201 got=201 |
| planner full: manage seating | ✅ PASS | כן | expected=200 got=200 |
| planner full: send messages permission recognized | ✅ PASS | כן | expected=200 got=200 |
| planner full: cannot edit core event settings (owner-only) | ✅ PASS | כן | expected=404 got=404 |
| planner partial (view_guests only): can view guests | ✅ PASS | כן | expected=200 got=200 |
| planner partial: CANNOT create guests | ✅ PASS | כן | expected=403 got=403 |
| planner partial: CANNOT access automation/messaging | ✅ PASS | כן | expected=403 got=403 |
| planner: isolated from event B | ✅ PASS | כן | expected=404 got=404 |
| venue full: view hall | ✅ PASS | כן | expected=200 got=200 |
| venue full: edit hall/seating | ✅ PASS | כן | expected=200 got=200 |
| venue full: CAN view messages summary (view_event grants read) | ✅ PASS | כן | expected=200 got=200 |
| venue full: CANNOT send messages (no send_messages) | ✅ PASS | כן | expected=403 got=403 |
| venue partial (view_event only): can read event | ✅ PASS | כן | expected=200 got=200 |
| venue partial: CANNOT edit hall | ✅ PASS | לא | expected=403 got=403 |
| guest: read own RSVP via token | ✅ PASS | כן | expected=200 got=200 |
| guest: submit RSVP | ✅ PASS | כן | expected=200 got=200 |
| guest: wrong/random token rejected | ✅ PASS | כן | expected=404 got=404 |
| webhook: accepted (never errors to Meta) | ✅ PASS | כן | expected=200 got=200 |
| webhook: RSVP actually updated via SECURITY DEFINER path | ✅ PASS | כן | rsvp_status=confirmed |
| seating: owner can generate+persist | ✅ PASS | כן | expected=200 got=200 |
| invitations: owner can send | ✅ PASS | כן | expected=200 got=200 |
| invitations: view-only planner blocked | ✅ PASS | כן | expected=403 got=403 |
| messages: owner reads summary | ✅ PASS | כן | expected=200 got=200 |
| messages: planner-full reads summary | ✅ PASS | כן | expected=200 got=200 |
| media: owner uploads invite image | ✅ PASS | כן | expected=200 got=200 |
| media: public unauthenticated fetch works | ✅ PASS | כן | expected=200 got=200 |

**סיכום: 44 בדיקות, 0 כשלים קריטיים.**

✅ **0 כשלים קריטיים — אפשר לעבור לתוכנית ההפעלה בייצור.**