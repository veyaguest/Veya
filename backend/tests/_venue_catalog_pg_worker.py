"""מאגר האולמות מול Postgres אמיתי (pgserver) — תהליך-בת, מדפיס JSON בשורה האחרונה.

1. מדמה את הייצור: טבלת venues *בלי* העמודות החדשות + שורה ישנה של זוג.
2. מריץ את המיגרציה האמיתית (``_ensure_columns`` + ``_ensure_unique_indexes``).
3. מייבא את קובץ המאגר האמיתי כ-``veya_app`` (התפקיד שהאפליקציה רצה בו —
   לא superuser, לא עוקף RLS), פעמיים — הפעם השנייה לא יוצרת כלום.
4. בודק שהאינדקס הייחודי חוסם כפילות ברמת המסד, ושהשורה הישנה לא השתנתה.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NEW_COLS = ["name_en", "aliases", "region", "lat", "lng", "source_url", "import_key", "imported_at",
            "verification", "operating_status", "last_checked_at"]


def main() -> None:
    import psycopg2
    from sqlalchemy import func, select

    from app import database, main as app_main, models, venue_catalog, venues

    out: dict = {}
    database.Base.metadata.create_all(bind=database.migrations_engine)
    seed = database.MigrationSessionLocal()  # שורה ישנה של זוג (לפני הייבוא)
    seed.add(models.Venue(name="אגדת דשא", address="הדקל 1, פרדס חנה-כרכור", dedup_key="אגדת דשא",
                          usage_count=7, source="auto"))
    seed.commit()
    seed.close()
    admin = psycopg2.connect(os.environ["MIGRATIONS_DATABASE_URL"])
    admin.autocommit = True
    cur = admin.cursor()
    for col in NEW_COLS:  # מצב הייצור לפני השינוי
        cur.execute(f'ALTER TABLE venues DROP COLUMN IF EXISTS "{col}"')
    rls_dir = Path(__file__).resolve().parent.parent / "rls"
    cur.execute((rls_dir / "01_helpers_and_grants.sql").read_text())

    added = app_main._ensure_columns()
    app_main._ensure_unique_indexes()
    out["columns_added"] = sorted(c for t, c in added if t == "venues")
    cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_venues_import_key'")
    out["unique_index"] = bool(cur.fetchone())

    data = venue_catalog.load_catalog()
    db = database.SessionLocal()  # DATABASE_URL = veya_app
    try:
        out["role"] = db.execute(select(func.current_user())).scalar()
        r1 = venue_catalog.import_catalog(db, data["venues"], dry_run=False)
        db.commit()
        r2 = venue_catalog.import_catalog(db, data["venues"], dry_run=False)
        db.commit()
        out["first"] = {k: r1[k] for k in ("created", "updated", "unchanged", "matched_existing_count", "invalid_count")}
        out["second"] = {k: r2[k] for k in ("created", "updated", "unchanged")}
        out["imported_rows"] = db.scalar(select(func.count(models.Venue.id)).where(models.Venue.source == "import"))
        old = db.scalar(select(models.Venue).where(models.Venue.dedup_key == "אגדת דשא"))
        out["old_row_untouched"] = (old.address, old.usage_count, old.source) == ("הדקל 1, פרדס חנה-כרכור", 7, "auto")
        hits = venues.search_venues(db, "ויטראז")
        out["search_hit"] = [h.name for h in hits][:3]
    finally:
        db.close()

    try:
        cur.execute("CREATE TEMP TABLE v_dup AS SELECT * FROM venues WHERE import_key IS NOT NULL LIMIT 1")
        cur.execute("UPDATE v_dup SET id = (SELECT max(id) + 1 FROM venues), dedup_key = dedup_key || ' dup'")
        cur.execute("INSERT INTO venues SELECT * FROM v_dup")
        out["db_blocks_duplicate_key"] = False
    except psycopg2.errors.UniqueViolation:
        out["db_blocks_duplicate_key"] = True
    admin.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
