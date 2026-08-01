"""בודק שכל עמודה במודלים באמת מגיעה ל-DB קיים.

הרקע: אין Alembic בפרויקט. מיגרציות נעשות ב-``app/main.py`` דרך
``_EXTRA_COLUMNS`` + ``_ensure_columns()`` שרצות בכל עלייה. ``create_all``
**לא** מוסיף עמודות לטבלה שכבר קיימת — ולכן עמודה שנוספה למודל בלי רשומה
מקבילה ב-``_EXTRA_COLUMNS`` שוברת כל שאילתה על הטבלה בכל DB קיים
(זה בדיוק מה שקרה ל-``events.groom_parents_line``).

הבדיקה מדמה DB "ישן": יוצרת סכימה מלאה, מפילה עמודות נבחרות, ומריצה את
מנגנון המיגרציה — ואז מוודאת שכל עמודות המודל חזרו.

הרצה: ``python tests/test_schema_migrations.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app import main, models  # noqa: E402,F401
from app.database import Base  # noqa: E402


def _fresh_engine():
    """מנוע SQLite בזיכרון עם הסכימה המלאה של המודלים."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return engine


def test_derive_column_ddl_is_safe() -> None:
    """ה-DDL הנגזר לעולם לא NOT NULL, ולא מנסה DEFAULT לפונקציה."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            ddl = main.derive_column_ddl(column)
            upper = ddl.upper()
            assert "NOT NULL" not in upper, (
                f"{table.name}.{column.name}: ADD COLUMN עם NOT NULL נכשל על "
                f"טבלה עם שורות — {ddl}"
            )
            # ברירת מחדל שהיא פונקציה (מחולל טוקן וכו') לא מקבלת DEFAULT ב-DDL.
            default = getattr(column, "default", None)
            if default is not None and getattr(default, "is_callable", False):
                assert "DEFAULT" not in upper, (
                    f"{table.name}.{column.name}: ברירת מחדל מחושבת לא יכולה "
                    f"להיות DEFAULT ב-DDL — {ddl}"
                )
    print("✓ derive_column_ddl בטוח לכל עמודות המודל")


def test_every_model_column_survives_migration() -> None:
    """DB 'ישן' שחסרות בו עמודות — מנגנון המיגרציה משלים את כולן.

    מפילים כל עמודה שאינה חלק מהסכימה המקורית (כלומר כל מה שמופיע ב-
    ``_EXTRA_COLUMNS``), מריצים את המיגרציה, ומוודאים שאין פער.
    """
    engine = _fresh_engine()
    inspector = inspect(engine)

    dropped: list[str] = []
    with engine.begin() as conn:
        for table_name, columns in main._EXTRA_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            table = Base.metadata.tables[table_name]
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            # SQLite לא מרשה DROP COLUMN לעמודה שמשתתפת במפתח זר או באינדקס
            # (למשל events.owner_id). מדלגים עליהן — הן ממילא לא הבעיה שאנחנו
            # מגנים מפניה, וההשלמה שלהן נבדקת דרך missing_migrations בהמשך.
            undroppable = {
                c.name for c in table.columns if c.foreign_keys or c.index or c.unique
            }
            for name in columns:
                if name in existing and name not in undroppable:
                    conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {name}"))
                    dropped.append(f"{table_name}.{name}")
    assert dropped, "הבדיקה לא הפילה אף עמודה — משהו במנגנון השתנה"

    # מריצים את המיגרציה מול המנוע הזמני (אותו קוד, מנוע אחר).
    original = main.migrations_engine
    try:
        main.migrations_engine = engine
        main._ensure_columns()
        gaps = main.missing_migrations()
    finally:
        main.migrations_engine = original

    assert gaps == {}, f"עמודות שלא הושלמו אחרי מיגרציה: {gaps}"

    after = inspect(engine)
    for table_name, table in Base.metadata.tables.items():
        have = {c["name"] for c in after.get_columns(table_name)}
        missing = [c.name for c in table.columns if c.name not in have]
        assert not missing, f"{table_name}: עמודות חסרות אחרי מיגרציה — {missing}"

    print(f"✓ {len(dropped)} עמודות הופלו והושלמו חזרה במלואן")


def test_safety_net_covers_a_forgotten_entry() -> None:
    """הרגרסיה עצמה: עמודה שנוספה למודל ו**נשכחה** ב-``_EXTRA_COLUMNS``.

    זה בדיוק המקרה של ``events.groom_parents_line``. לפני התיקון, DB קיים
    נשאר בלי העמודה וכל שאילתה על הטבלה נכשלה. אחרי התיקון, רשת הביטחון
    ב-``_ensure_columns`` מוסיפה אותה בכל זאת.
    """
    engine = _fresh_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE guests DROP COLUMN seating_notes"))

    original_engine = main.migrations_engine
    original_guests = main._EXTRA_COLUMNS["guests"]
    try:
        main.migrations_engine = engine
        # מדמים "שכחו להוסיף רשומה": מסירים אותה מהמפה הידנית.
        main._EXTRA_COLUMNS["guests"] = {
            k: v for k, v in original_guests.items() if k != "seating_notes"
        }
        before = main.missing_migrations()
        assert "guests" in before and "seating_notes" in before["guests"], (
            "missing_migrations לא זיהה עמודה חסרה — הבדיקה לא בודקת כלום"
        )
        main._ensure_columns()
    finally:
        main._EXTRA_COLUMNS["guests"] = original_guests
        main.migrations_engine = original_engine

    have = {c["name"] for c in inspect(engine).get_columns("guests")}
    assert "seating_notes" in have, (
        "רשת הביטחון לא הוסיפה עמודה שנשכחה — הבאג שתוקן יכול לחזור"
    )
    print("✓ רשת הביטחון משלימה עמודה שנשכחה ב-_EXTRA_COLUMNS")


def test_seating_notes_is_migrated() -> None:
    """הפרדת ההערות: seating_notes חייבת להגיע ל-DB קיים."""
    assert "seating_notes" in main._EXTRA_COLUMNS["guests"], (
        "guests.seating_notes חסרה ב-_EXTRA_COLUMNS — אירועים קיימים לא "
        "יקבלו את שדה הערות ההושבה"
    )
    assert "seating_notes" in Base.metadata.tables["guests"].columns
    print("✓ guests.seating_notes מכוסה במיגרציה")


if __name__ == "__main__":
    test_derive_column_ddl_is_safe()
    test_every_model_column_survives_migration()
    test_safety_net_covers_a_forgotten_entry()
    test_seating_notes_is_migrated()
    print("OK — סכימת המודלים והמיגרציות מיושרות.")
