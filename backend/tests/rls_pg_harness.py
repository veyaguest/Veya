"""Postgres זמני להרצת בדיקות RLS אמיתיות (שלא ניתן להוכיח מול SQLite — RLS
הוא no-op שם, ראו ``app/database.py::IS_POSTGRES``).

משתמש ב-``pgserver`` (כבר מותקן ב-venv): שרת Postgres מוטמע, בלי Docker
ובלי התקנה על המערכת — עולה על תיקייה זמנית ונסגר איתה. עוזר-בדיקה בלבד:
**אסור לו לייבא ``app.models``/``app.database``** — מודולים אלה קובעים
engine לפי ``DATABASE_URL`` בזמן הייבוא, וכל שאר קובצי הבדיקה בסוויטה כבר
עלולים לייבא אותם מול SQLite; ייבוא כאן היה "נועל" את זה לתהליך ה-pytest
הראשי. במקום זאת, יצירת הסכמה + הרצת קובצי ה-RLS נעשית בתוך תהליך-בת נפרד
(ראו ``_rls_identity_worker.py``), שמקבל את משתני הסביבה הנכונים *לפני*
שהוא מייבא משהו מ-``app``.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass

import pgserver

# הסיסמה המדויקת שמוגדרת ב-CREATE ROLE בתוך rls/01_helpers_and_grants.sql.
# זו סביבת בדיקה זמנית ומבודדת (תיקייה זמנית שנמחקת בסוף) — אין כאן שום
# רגישות אבטחתית בשימוש בסיסמת ה-placeholder המתועדת.
VEYA_APP_PASSWORD = "CHANGE_ME_STRONG_PASSWORD"


@dataclass
class PgHarness:
    server: object
    datadir: str
    admin_dsn: str
    veya_app_dsn: str

    def cleanup(self) -> None:
        try:
            self.server.cleanup()
        finally:
            shutil.rmtree(self.datadir, ignore_errors=True)


def start_ephemeral_postgres() -> PgHarness:
    """מרים Postgres זמני ומחזיר DSN גם ל-superuser וגם לתפקיד ``veya_app``
    (עדיין לא קיים בפועל בשלב הזה — ייווצר כשמריצים את קובצי ה-RLS)."""
    datadir = tempfile.mkdtemp(prefix="veya_rls_pgtest_")
    server = pgserver.get_server(datadir)
    admin_dsn = server.get_uri()
    veya_app_dsn = admin_dsn.replace("postgres:@", f"veya_app:{VEYA_APP_PASSWORD}@")
    return PgHarness(server=server, datadir=datadir, admin_dsn=admin_dsn, veya_app_dsn=veya_app_dsn)
