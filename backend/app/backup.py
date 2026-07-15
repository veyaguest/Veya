"""גיבוי אוטומטי של מסד הנתונים (SQLite).

לחתונה אין "פעם שנייה" — אובדן קובץ ה-DB = אובדן כל נתוני האירוע. לכן בכל
עליית שרת אנו שומרים עותק מתוארך של הקובץ תחת ``backend/backups/`` ושומרים
רק את N העותקים האחרונים. פשוט, זול, ונותן הגנה אמיתית.

שחזור מגיבוי (לבעלים): לעצור את השרת, להעתיק את קובץ הגיבוי הרצוי מתוך
``backend/backups/`` חזרה ל-``backend/veya.db`` (להחליף את הקיים), ולהפעיל שוב.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from app.database import engine

# כמה עותקי גיבוי לשמור (הישנים נמחקים).
MAX_BACKUPS = 14


def _sqlite_path() -> Path | None:
    """נתיב קובץ ה-SQLite, או None אם לא עובדים עם SQLite (למשל Postgres)."""
    if engine.url.get_backend_name() != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database)


def create_backup() -> Path | None:
    """יוצר עותק מתוארך של ה-DB ומנקה עותקים ישנים. מחזיר את נתיב הגיבוי."""
    src = _sqlite_path()
    if src is None or not src.exists():
        return None

    backups_dir = src.resolve().parent / "backups"
    backups_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backups_dir / f"{src.stem}-{stamp}{src.suffix}"
    # copy2 שומר גם את זמני הקובץ; אם כבר קיים גיבוי לאותה שנייה — לא כופלים.
    if not dest.exists():
        shutil.copy2(src, dest)

    _prune_old(backups_dir, src.stem, src.suffix)
    return dest


def _prune_old(backups_dir: Path, stem: str, suffix: str) -> None:
    """שומר רק את MAX_BACKUPS הגיבויים החדשים; מוחק את הישנים."""
    backups = sorted(
        backups_dir.glob(f"{stem}-*{suffix}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[MAX_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass
