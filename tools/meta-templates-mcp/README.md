# veya-meta-templates — ניהול תבניות WhatsApp דרך Claude

שרת MCP מקומי שמחבר את Claude Code ל-WhatsApp Business Management API של Meta, כדי לנהל
את תבניות ההודעות בשיחה בעברית: לראות תבניות, לבדוק סטטוס אישור, ליצור, לערוך, ולוודא
שהן תואמות לקוד של VEYA.

## מה הוא עושה ומה לא

| עושה | לא עושה |
|---|---|
| מציג תבניות, סטטוס, נוסח, משתנים וכפתורים | **לא שולח הודעות WhatsApp** — אין בו כלי שליחה |
| משווה לקוד (`whatsapp_templates.TEMPLATES`, `veya_inv_pilot`) ולמסמך `docs/whatsapp-templates.md` | לא נוגע ב-Render, ב-`WHATSAPP_MODE` או בתהליך השליחה |
| בודק טיוטה לפי הכללים של Meta ושל VEYA | לא מוחק תבניות |
| יוצר ועורך תבניות — **רק בשני שלבים ועם אישור** | לא משנה הגדרות חשבון, מספר טלפון או webhook |

**יצירה ועריכה:** `prepare_*` מכין ומציג (בלי לכתוב ל-Meta) → אתם מאשרים בצ'אט →
`submit_*` עם מזהה הטיוטה ושם התבנית. Claude Code גם מבקש אישור על כל קריאה לכלי.
`veya_inv_pilot` נעולה לעריכה.

## הכלים

| כלי | כותב ל-Meta? |
|---|---|
| `meta_connection_status` — טוקן, הרשאות, תוקף, חשבון ומספר | לא |
| `list_templates` · `get_template` · `get_template_status` | לא |
| `check_veya_alignment` — האם התבניות ב-Meta מתאימות לקוד ולמסמך | לא |
| `validate_template_draft` — בדיקה מקומית בלבד | לא |
| `prepare_template_create` · `prepare_template_update` — תצוגה ו-draft_id | לא |
| `submit_template_create` · `submit_template_update` | **כן — רק אחרי אישור** |
| `explain_meta_error` — הסבר שגיאה או סיבת דחייה | לא |

## הגדרה חד-פעמית (הבעלים)

### 1. טוקן ב-Meta (בערך 5 דקות)

ב-[Business Settings](https://business.facebook.com/settings) של העסק:

1. **Users → System users → Add.** שם: `veya-templates` · תפקיד: **Employee** (לא Admin).
2. בחרו את המשתמש → **Assign assets → WhatsApp accounts** → החשבון של VEYA →
   ההרשאה לניהול תבניות בלבד (אם אין אפשרות חלקית — Full control).
3. **Accounts → Apps** → האפליקציה של VEYA → **Assign people** → `veya-templates`
   (בלי זה האפליקציה לא תופיע ביצירת הטוקן).
4. חזרה ל-**System users** → `veya-templates` → **Generate new token**:
   - App: האפליקציה של VEYA
   - Token expiration: **Never**
   - Permissions: **רק** `whatsapp_business_management`
5. העתיקו את הטוקן (מוצג פעם אחת בלבד). **לא מדביקים אותו בצ'אט ולא בשום קובץ.**

> טוקן נפרד מהטוקן של השליחה: לכלי הזה אין צורך ב-`whatsapp_business_messaging`,
> ולכן גם אם הטוקן ידלוף — אי אפשר לשלוח איתו הודעות.

### 2. שמירה ב-Keychain

מעתיקים את הטוקן (Cmd+C), ואז ב-Terminal (לא בצ'אט) מריצים:

```bash
security add-generic-password -U -s veya-meta-templates -a veya -w "$(pbpaste | tr -d '[:space:]')" && pbcopy < /dev/null && echo "OK - saved"
```

הפקודה לוקחת את הטוקן מהלוח, שומרת אותו ב-Keychain ומרוקנת את הלוח. הטוקן לא מוצג
ולא נשמר בהיסטוריה של ה-Terminal.

> לא להשתמש ב-`-w` בלי ערך (הדבקה בשאלה של המחשב): macOS חותך שם קלט אחרי 128 תווים,
> וטוקן של Meta ארוך יותר — Meta מחזירה "The access token could not be decrypted".

החלפת טוקן — אותה פקודה. מחיקה:

```bash
security delete-generic-password -s veya-meta-templates -a veya
```

### 3. הפעלה ב-Claude Code

פותחים שיחה חדשה בתיקיית `veya` ומאשרים את השרת `veya-meta-templates` כש-Claude Code
שואל (ההגדרה ב-`.mcp.json`, בלי סודות). אחר כך: "בדוק את החיבור ל-Meta".

את מזהה חשבון ה-WhatsApp (WABA) לא צריך להזין — הכלי מזהה אותו מהטוקן.

## בדיקות

```bash
backend/venv/bin/python -m pytest tools/meta-templates-mcp -q
```

בלי רשת ובלי Keychain — Meta מדומה.

## פרטים טכניים

- Python 3.9 מה-venv של ה-backend, בלי תלויות חדשות (רק `httpx`). ה-SDK הרשמי של MCP
  דורש 3.10+, ולכן הפרוטוקול (stdio, JSON-RPC) ממומש ב-`server.py`.
- גרסת Graph API — כמו בשרת (`whatsapp_meta.DEFAULT_GRAPH_VERSION`); אפשר לעקוף עם
  `VEYA_META_GRAPH_VERSION`. חשבון מסוים: `VEYA_META_WABA_ID` או הפרמטר `waba_id`.
- הטוקן לא מוחזר מאף כלי ולא נכתב ללוג, ומוסר מכל טקסט שגיאה. מספרי טלפון — 4 ספרות אחרונות.
- תבנית עם Header תמונה: הקובץ המקומי מועלה ל-Meta (Resumable Upload) רק ב-`submit_*`.
