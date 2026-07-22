# VEYA · מודל הרשאות חבר-אירוע (מפיק/אולם)

מסמך זה משלים את [RLS_REPORT.md](RLS_REPORT.md): שם מתועדת הכנת ה-DB
להפעלת RLS; כאן מתועד **מודל ההרשאות** שנאכף פעמיים — פעם אחת בקוד השרת
(שכבת ה-API) ופעם שנייה במסד הנתונים (RLS, כשיופעל) — ולמה זה בטוח.

**עדכון סטטוס: הפער שתועד ב-RLS_REPORT.md כבעיה #9 ("פער עיצובי פתוח") —
נסגר.** כל endpoint רגיש בודק כעת הרשאה ספציפית, לא רק "האם המשתמש חבר
פעיל באירוע".

---

## מי מקבל גישה למה — התמונה הכללית

- **אדמין** (`is_admin`) — גישה מלאה לכל אירוע, תמיד. לא תלוי בשום רשימת הרשאות.
- **בעל האירוע** (הזוג, `owner_id`) — גישה מלאה לאירוע/ים שלו, תמיד.
- **מפיק/אולם (`EventMember`)** — רק לפי הרשאות ספציפיות שהוענקו לו ע"י
  הבעלים (דרך `/events/{id}/members`). בלי הרשאה מסוימת = בלי גישה לפעולה
  הזו, גם אם הוא "חבר פעיל" באירוע.
- **מוזמן** — רק דרך הטוקן האישי שלו בקישור `/confirm/{token}` (ה-RSVP שלו
  בלבד, לעולם לא נתוני מוזמנים אחרים).

## רשימת ההרשאות הקיימות

מוגדרות ב-`backend/app/schemas.py`:

| הרשאה | לאיזה תפקיד | פירוש |
|---|---|---|
| `view_guests` | מפיק | לראות את רשימת המוזמנים |
| `edit_guests` | מפיק | להוסיף/לערוך/למחוק מוזמנים, לייבא רשימה |
| `manage_seating` | מפיק | לנהל שיבוץ הושבה (הרצת מנוע, שיבוץ ידני) |
| `send_messages` | מפיק | לשלוח הזמנות/תזכורות, לנהל אוטומציה ותבניות |
| `view_reports` | מפיק | לראות דוחות/סיכומי RSVP |
| `view_event` | אולם | לראות את פרטי האירוע הבסיסיים |
| `view_seating` | אולם | לראות את מפת ההושבה (בלי לערוך) |
| `edit_seating` | אולם | לערוך את מפת ההושבה/האולם |
| `manage_venue_data` | אולם | לערוך פרטי אולם (כתובת, מגבלות) |

מפיק מקבל תמיד מתוך `PLANNER_PERMISSIONS`, אולם מתוך `VENUE_PERMISSIONS` —
אי אפשר "לערבב" (לא ניתן להעניק `edit_guests` לחבר מסוג אולם). זה נאכף גם
ב-`event_members.py::_permissions_for_role` (אפליקציה) וגם במבנה ה-RLS.

## איך זה נאכף — שתי שכבות, אותו כלל

**שכבה 1 — API (Python):** `app/deps.py::EventAccess`, שנקרא עם קבוצת
הרשאות מ-`app/permissions.py` בכל endpoint רגיש. מספיקה הרשאה *אחת* מתוך
הקבוצה. בעלים/אדמין תמיד עוברים קודם, בלי לבדוק רשימות.

**שכבה 2 — RLS (Postgres, מוכן אך לא מופעל):** `app_has_any_event_permission`
ב-`backend/rls/01_helpers_and_grants.sql`, עם אותה סמנטיקה בדיוק — נקרא
מתוך ה-`ARRAY[...]` בכל מדיניות ב-`backend/rls/02_policies.sql`.

**למה שתיהן, ולא רק אחת:** ה-API הוא שכבת ההגנה המהירה והמדויקת (יודעת
בדיוק על איזה endpoint מדובר). ה-RLS הוא רשת ביטחון ברמת מסד הנתונים —
מגנה גם אם יתגלה יום אחד באג בשכבת ה-API (endpoint חדש שנשכח לחדד, שאילתת
SQL ישירה שעוקפת את ה-router). שתי השכבות חייבות **להישאר מסונכרנות**:
קבוצת ההרשאות שה-API בודקת חייבת להיות **תת-קבוצה של (או שווה ל)** מה
שה-RLS מרשה בפועל — אחרת ה-API "יפתח" משהו שה-DB לא מרשה, וזה יישבר בשקט
ברגע שה-RLS יופעל (בדיוק הבאג שתוקן קודם ב-webhook וב-`audit_logs`).

**זה נבדק אוטומטית:** `backend/tests/test_permission_alignment.py` קורא את
`02_policies.sql` וממש משווה, שורה-שורה, לקבועים ב-`app/permissions.py`.
מריצים עם:
```bash
python tests/test_permission_alignment.py
```
טסט שנכשל = מישהו שינה צד אחד (SQL או Python) בלי לעדכן את השני.

## טבלת פעולה → הרשאה נדרשת

| Endpoint (router) | פעולה | הרשאה נדרשת (מספיקה אחת) | קבוע ב-`permissions.py` |
|---|---|---|---|
| `GET /guests`, `/group-suggestions`, `/group-notes` | צפייה במוזמנים | `view_guests`/`edit_guests`/`manage_seating`/`view_seating`/`edit_seating` | `GUESTS_VIEW` |
| `POST/PATCH/DELETE /guests`, `/bulk-group`, `/group-notes` (PUT), ייבוא | עריכת מוזמנים | `edit_guests`/`manage_seating`/`edit_seating` | `GUESTS_WRITE` |
| `POST /seating/generate`, `/seating/assign` | שיבוץ הושבה | `manage_seating`/`edit_seating` | `SEATING_WRITE` |
| `POST /seating/recommend-seat`, `GET /seating/reserve` | צפייה בהמלצות/רזרבה | (זהה ל-`GUESTS_VIEW`) | `GUESTS_VIEW` |
| `GET /hall` | צפייה במפת אולם | `view_seating`/`edit_seating`/`manage_seating`/`manage_venue_data` | `HALL_VIEW` |
| `PUT /hall` | עריכת מפת אולם | `edit_seating`/`manage_seating`/`manage_venue_data` | `HALL_WRITE` |
| `POST /constraints/analyze`, `GET/POST /constraints/clarifications` | הבהרות שם עמום | `edit_guests`/`manage_seating` | `CLARIFICATIONS` |
| כל `automation.py` (תבניות/חוקים/תור/מסלול RSVP) | ניהול אוטומציה | `send_messages` בלבד | `AUTOMATION` |
| `GET /messaging/summary`, `/template`, `/log`, תצוגה מקדימה | צפייה בהודעות/RSVP | `send_messages`/`view_reports`/`view_event` | `MESSAGES_VIEW` |
| `POST /messaging/invitations/send`, `/reminders/send`, `PUT /template`, סימולציית תשובה | שליחת הודעות | `send_messages` בלבד | `MESSAGES_WRITE` |
| `GET /stats` (דשבורד) | סיכום כללי | כל הרשאה מוכרת (רשימה מלאה) | `EVENTS_VIEW` |
| `GET /event` | צפייה בפרטי האירוע | כל חבר-אירוע פעיל (בלי בדיקת הרשאה ספציפית) | — (בכוונה, ראו למטה) |
| `PATCH /event` (שם/תאריך/אולם/תמונה) | **עריכת ליבת האירוע** | **בעלים/אדמין בלבד — אין הרשאת חבר שפותחת זאת** | `owner_only=True` |
| `GET /event/audit` | יומן אבטחה | כל חבר-אירוע פעיל | — (בכוונה, תואם `audit_logs_select`) |
| `GET/POST/PATCH/DELETE /events/{id}/members` | ניהול חברי-אירוע | בעלים/אדמין בלבד | — (ללא שינוי, לא ניתן לחבר לנהל את עצמו) |

### למה `PATCH /event` הוא owner-only, ולא הרשאה נפרדת

זו החלטת עיצוב מפורשת שהתקבלה תוך כדי המשימה: אין ב-`schemas.py` הרשאה
כמו "event_manage" שהייתה מיועדת לפתוח עריכת שם בני הזוג/תאריך/סוג האירוע
למפיק או אולם — ובצדק: אלה פרטי הליבה של האירוע של **הזוג**, לא תחום
האחריות של מפיק/אולם (שהאחריות שלהם היא הושבה/הודעות/מוזמנים/פרטי אולם —
שכל אחד מהם *כן* קיבל הרשאה ייעודית עבורו). לכן `PATCH /event` נשאר
תמיד owner/admin בלבד, בלי קשר לאילו הרשאות הוענקו לחבר-אירוע.

### הערה על `events_update` ב-RLS מול `PATCH /event` באפליקציה

שדות כמו `table_positions`/`hall_elements` (נשמרים דרך `hall.py`),
`rsvp_track_active`/`message_template` (דרך `automation.py`/`messaging.py`)
ו-`group_notes` (דרך `guests.py`) יושבים כולם על שורת ה-`events` — לכן
מדיניות ה-RLS `events_update` חייבת להרשות UPDATE על השורה למי שיש לו
`manage_seating`/`edit_seating`/`manage_venue_data`/`send_messages`/
`edit_guests`. זה **לא** אומר שחבר כזה יכול לערוך את שם בני הזוג — RLS
הוא ברמת-שורה ולא ברמת-עמודה, אז ההגנה העדינה-לפי-שדה היא באחריות שכבת
ה-API (ה-`owner_only` שמונע גישה ל-`PATCH /event` בכלל). זו מגבלה ידועה
ומתועדת, לא פרצה.

## סטטוס בדיקה מול RLS אמיתי

**עודכן:** כל התרחישים בטבלה למעלה — כולל מפיק/אולם עם הרשאות מלאות
וחלקיות — נבדקו בפועל מול Supabase staging אמיתי (לא רק SQLite/API בלבד),
ועברו במלואם (44/44, 0 כשלים, יציב על 2 הרצות). ראו STAGING_TEST_REPORT.md
לפירוט המלא, כולל 4 באגים אמיתיים שהבדיקה הזו גילתה ותיקנה (בעיקר
אינטראקציה בין `INSERT ... RETURNING` למדיניות ה-SELECT, שלא ניתן לגלות
מול SQLite בכלל).
