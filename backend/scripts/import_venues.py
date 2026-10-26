"""ייבוא המאגר הארצי לבסיס הנתונים המקומי (פיתוח/בדיקות).

    python3 scripts/import_venues.py            # תצוגה מקדימה בלבד — לא משנה כלום
    python3 scripts/import_venues.py --apply    # כותב למסד שב-DATABASE_URL

בייצור הייבוא נעשה מפאנל האדמין (מאגר אולמות → "ייבוא המאגר הארצי"), דרך ה-API
עם הרשאת venues.edit — לא מהכלי הזה, ולא עם פרטי גישה למסד.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models, venue_catalog  # noqa: E402,F401  (models — רישום הטבלאות)
from app.database import SessionLocal  # noqa: E402


def main() -> None:
    apply = "--apply" in sys.argv
    from app.database import DATABASE_URL

    # כלי פיתוח בלבד: לא כותבים לעולם למסד מרוחק מכאן (ייצור = דרך האדמין).
    local = DATABASE_URL.startswith("sqlite") or "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL
    if apply and not local:
        sys.exit("DATABASE_URL מצביע על מסד מרוחק — ייבוא לייצור נעשה מפאנל האדמין בלבד.")
    data = venue_catalog.load_catalog()
    db = SessionLocal()
    try:
        report = venue_catalog.import_catalog(db, data["venues"], dry_run=not apply)
        if apply:
            db.commit()
    finally:
        db.close()
    short = {k: v for k, v in report.items() if not isinstance(v, list)}
    print(json.dumps(short, ensure_ascii=False, indent=1))
    for k in ("invalid", "matched_existing", "possible_duplicates"):
        for item in report[k][:10]:
            print(k, item)
    if not apply:
        print("\nתצוגה מקדימה בלבד. להחלה: --apply")


if __name__ == "__main__":
    main()
