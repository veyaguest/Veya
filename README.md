# VEYA

מערכת SaaS לניהול מוזמנים, אישורי הגעה (RSVP) וסידורי הושבה לאירועים —
Event-first architecture: מערכת אחת שמתאימה את עצמה לפי `event_type`
(חתונה, בר/בת מצווה, חינה, ברית, אירוע עסקי ועוד), לא מערכת חתונות שהתרחבה.
ראו `.claude/skills/veya-master/references/architecture.md`.

- מסמך דרישות מלא: `VEYA_PRD.md`
- הקשר והחלטות טכניות: `CLAUDE.md`
- POC של מנוע השיבוץ: `veya_seating_poc.py`

## מבנה הפרויקט

```
backend/    # שרת ה-API (Python + FastAPI)
frontend/   # ממשק המשתמש (React + TypeScript + Vite)
```

## דרישות מקדימות

- Python 3.9+ (מותקן)
- Node.js 20+ (מותקן בתיקייה אישית: `/Users/mac/.local/node`, כבר נוסף ל-PATH ב-`~/.zshrc`)

## הרצה מקומית

צריך שני חלונות טרמינל — אחד ל-Backend ואחד ל-Frontend.

### 1. Backend (פורט 8000)

```bash
cd backend
python3 -m venv venv          # פעם ראשונה בלבד
./venv/bin/pip install -r requirements.txt   # פעם ראשונה בלבד
./venv/bin/uvicorn app.main:app --reload --port 8000
```

בדיקה: פתח בדפדפן http://localhost:8000/health — אמור להחזיר `{"status":"ok"}`.

### 2. Frontend (פורט 5173)

```bash
cd frontend
npm install                   # פעם ראשונה בלבד
npm run dev
```

בדיקה: פתח בדפדפן http://localhost:5173 — אמור להציג "המערכת מחוברת ✓".

## מסד נתונים

בשלב הפיתוח משתמשים ב-SQLite (קובץ `backend/veya.db`, נוצר אוטומטית).
מעבר ל-PostgreSQL בהמשך = שינוי `DATABASE_URL` בקובץ `backend/.env` בלבד
(ראה `backend/.env.example`).
