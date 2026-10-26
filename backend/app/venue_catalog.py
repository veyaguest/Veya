"""ייבוא מבוקר של המאגר הארצי (``backend/data/venues/venues_il.json``) לטבלת ``venues``.

עקרונות (כל אחד נבדק ב-``tests/test_venue_catalog.py``):

1. **ניתן לחזרה.** כל רשומה בקובץ נושאת ``import_key`` יציב. הרצה שנייה מעדכנת
   את אותה שורה — לא יוצרת כפולה (וגם אינדקס ייחודי ב-DB מגן על כך).
2. **לא נוגעים במה שלא שלנו.** שורות שנוצרו מאירוע של זוג (``source=auto``),
   מהאדמין או משותף — לא משתנות לעולם. אם רשומה מהקובץ נראית כמו אחת מהן
   (אותו שם באותו יישוב), היא **לא** נוספת שוב ולא דורסת — רק נרשמת בדוח
   ``matched_existing`` כדי שאדמין יחליט. שורה ישנה באותו שם *בלי* עיר/כתובת
   לא חוסמת (אולי זה מקום אחר באותו שם) — מייבאים ומסמנים ב-``possible_duplicates``.
3. **לא דורסים עריכה של אדמין.** שורה מיובאת שאדמין ערך אחרי הייבוא האחרון
   (``updated_at > imported_at``) — הייבוא מדלג עליה.
4. **לא נוגעים באירועים.** אירועים שומרים שם+כתובת אולם אצלם (אין FK), כך
   שהייבוא לא יכול לשנות בחירה קיימת של אף זוג. גם ``usage_count`` לא נוגעים.
5. **סגור לא מוצע.** מקום שדווח כסגור נכנס/עובר ל-``status=hidden``. מקום
   שהוסתר ע"י אדמין לא "חוזר לחיים" בייבוא.
6. **Dry-run כברירת מחדל** בכלים: מחשבים את כל השינויים בטרנזקציה ומבטלים.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache, models
from app.venue_text import city_key, name_key, normalize

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "venues" / "venues_il.json"

KINDS = ("hall", "garden", "complex", "boutique", "restaurant", "hotel", "loft", "villa",
         "conference", "synagogue", "community", "other")
_IL_BBOX = (29.3, 33.5, 34.2, 35.95)  # lat_min, lat_max, lng_min, lng_max

# שדות שהייבוא "מחזיק" בשורה מיובאת. כל השאר (status, priority, verified,
# usage_count, תמונות, partnership, contact_*) — של האדמין בלבד.
IMPORT_OWNED = ("name", "name_en", "aliases", "city", "region", "address", "venue_kind",
                "capacity_min", "capacity_max", "phone", "website", "lat", "lng", "source_url",
                "verification", "operating_status", "internal_notes", "is_open")


def _dedup_key(name: str) -> str:
    # אותה נוסחה כמו app.venues._dedup_key (לא מייבאים כדי למנוע תלות מעגלית).
    return " ".join((name or "").strip().lower().split())


def _clip(value: Any, n: int) -> str:
    return str(value or "").strip()[:n]


def _full_address(street: Optional[str], city: Optional[str]) -> str:
    """הכתובת שנשמרת ב-``address`` משמשת לניווט — רחוב + יישוב (בלי כפילות)."""
    street = (street or "").strip()
    city = (city or "").strip()
    if not street:
        return ""
    if city and normalize(city) not in normalize(street):
        return f"{street}, {city}"
    return street


def validate(rec: dict) -> tuple[Optional[dict], Optional[str]]:
    """רשומה מהקובץ → ערכי עמודות, או (None, סיבה) אם הרשומה לא תקינה."""
    name = _clip(rec.get("name"), 120)
    key = _clip(rec.get("import_key"), 80)
    if not name:
        return None, "חסר שם"
    if not key:
        return None, "חסר import_key"
    kind = rec.get("venue_kind") or "other"
    if kind not in KINDS:
        kind = "other"
    cmin, cmax = rec.get("capacity_min"), rec.get("capacity_max")
    cmin = cmin if isinstance(cmin, int) and 0 <= cmin <= 10000 else None
    cmax = cmax if isinstance(cmax, int) and 0 < cmax <= 10000 else None
    if cmin is not None and cmax is not None and cmin > cmax:
        cmin = cmax = None
    website = _clip(rec.get("website"), 300)
    if website and not re.match(r"^https?://", website):
        website = ""
    lat, lng = rec.get("lat"), rec.get("lng")
    if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))
            and _IL_BBOX[0] <= lat <= _IL_BBOX[1] and _IL_BBOX[2] <= lng <= _IL_BBOX[3]):
        lat = lng = None
    aliases = [a.strip()[:120] for a in (rec.get("aliases") or []) if isinstance(a, str) and a.strip()][:20]
    status = rec.get("operating_status") or "unknown"
    sources = rec.get("sources") or []
    notes = rec.get("notes") or ""
    city = _clip(rec.get("city"), 80)
    return {
        "import_key": key,
        "name": name,
        "name_en": _clip(rec.get("name_en"), 120),
        "aliases": aliases or None,
        "city": city,
        "region": _clip(rec.get("region"), 40),
        "address": _clip(_full_address(rec.get("address"), city), 200),
        "venue_kind": kind,
        "capacity_min": cmin,
        "capacity_max": cmax,
        "phone": _clip(rec.get("phone"), 30),
        "website": website,
        "lat": lat,
        "lng": lng,
        "source_url": _clip(sources[0].get("url") if sources else "", 500),
        "verification": _clip(rec.get("verification"), 30),
        "operating_status": _clip(status, 30),
        "internal_notes": _clip(f"מאגר ארצי ({rec.get('last_checked') or ''}): {notes}" if notes else "", 4000),
        "is_open": status != "closed_reported",
        "_checked": rec.get("last_checked"),
    }, None


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def import_catalog(db: Session, records: Iterable[dict], *, dry_run: bool = True,
                   now: Optional[datetime] = None, sample: int = 25) -> dict:
    """מייבא רשומות מאגר. מחזיר דוח; ב-dry_run מבטל את כל השינויים בסוף.

    הקורא אחראי ל-commit כש-``dry_run=False`` (כדי לאפשר רישום audit באותה טרנזקציה).
    """
    now = now or datetime.utcnow()
    rows = db.scalars(select(models.Venue)).all()
    by_import = {v.import_key: v for v in rows if v.import_key}
    taken_keys = {v.dedup_key for v in rows}
    # אינדקס "אותו מקום" לפי (שם מנורמל, יישוב) — לשורות מיובאות ולשורות קיימות אחרות.
    by_place: dict = {}
    by_name_only: dict = {}
    for v in rows:
        place_city = v.city or _city_from_address(v.address)
        by_place.setdefault((name_key(v.name, place_city), city_key(place_city)), v)
        by_name_only.setdefault(name_key(v.name), []).append(v)

    report: dict = {"dry_run": dry_run, "total": 0, "created": 0, "updated": 0, "unchanged": 0,
                    "hidden_closed": 0, "skipped_admin_edited": 0, "invalid": [], "matched_existing": [], "possible_duplicates": [],
                    "created_sample": []}
    records_list = list(records)
    touched: set = set()
    for rec in records_list:
        report["total"] += 1
        vals, err = validate(rec)
        if err:
            report["invalid"].append({"import_key": rec.get("import_key"), "name": rec.get("name"), "reason": err})
            continue
        checked = vals.pop("_checked")
        place = (name_key(vals["name"], vals["city"]), city_key(vals["city"]))
        row = by_import.get(vals["import_key"])
        if row is None:
            other = by_place.get(place)
            if other is not None and (other.source or "") == "import":
                row = other  # אותו מקום, מפתח השתנה (למשל נוסף לו מזהה OSM) — מעדכנים
            elif other is not None:
                # אותו מקום כבר קיים (נוצר מאירוע/אדמין) — לא מוסיפים שוב ולא דורסים.
                if len(report["matched_existing"]) < 500:
                    report["matched_existing"].append({
                        "import_key": vals["import_key"], "name": vals["name"], "city": vals["city"],
                        "existing_id": other.id, "existing_name": other.name, "existing_source": other.source or "auto",
                    })
                continue
            else:
                weak = _name_only_match(by_name_only.get(name_key(vals["name"]), []), vals)
                if weak is not None and len(report["possible_duplicates"]) < 500:
                    # שורה ישנה באותו שם בלי עיר/כתובת — לא ברור אם זה אותו מקום (יש
                    # כמה "אולמי X" בארץ). מייבאים, ומסמנים לאדמין למיזוג ידני.
                    report["possible_duplicates"].append({
                        "import_key": vals["import_key"], "name": vals["name"], "city": vals["city"],
                        "existing_id": weak.id, "existing_name": weak.name, "existing_source": weak.source or "auto",
                    })

        if row is None:
            key = _free_dedup_key(vals, taken_keys)
            taken_keys.add(key)
            row = models.Venue(dedup_key=key, usage_count=0, source="import", verified=False, priority=0,
                               status="hidden" if vals["operating_status"] == "closed_reported" else "active",
                               created_at=now)
            for f, v in vals.items():
                setattr(row, f, v)
            row.imported_at = now
            row.last_checked_at = _parse_date(checked) or now
            db.add(row)
            by_import[vals["import_key"]] = row
            by_place[place] = row
            report["created"] += 1
            if row.status == "hidden":
                report["hidden_closed"] += 1
            if len(report["created_sample"]) < sample:
                report["created_sample"].append({"name": row.name, "city": row.city, "kind": row.venue_kind})
            continue

        if (row.source or "") != "import":
            continue  # לא אמור לקרות (מפתח ייבוא על שורה לא-מיובאת) — לא נוגעים
        touched.add(row)
        if row.updated_at and row.imported_at and row.updated_at > row.imported_at:
            report["skipped_admin_edited"] += 1
            continue
        changed = False
        for f in IMPORT_OWNED:
            if getattr(row, f) != vals[f]:
                setattr(row, f, vals[f])
                changed = True
        if row.import_key != vals["import_key"]:
            row.import_key = vals["import_key"]
            changed = True
        if vals["operating_status"] == "closed_reported" and row.status != "hidden":
            row.status = "hidden"
            report["hidden_closed"] += 1
            changed = True
        if changed:
            new_key = _dedup_key(row.name)
            if not row.dedup_key.startswith(new_key):
                taken_keys.discard(row.dedup_key)
                row.dedup_key = _free_dedup_key(vals, taken_keys)
                taken_keys.add(row.dedup_key)
            row.imported_at = now
            row.updated_at = now
            row.last_checked_at = _parse_date(checked) or now
            report["updated"] += 1
        else:
            report["unchanged"] += 1

    # שורות מיובאות שכבר לא בקובץ (מקום הוסר/מוזג במחקר) — לא נמחקות אוטומטית;
    # רק מדווחות, כדי שאדמין יחליט (להסתיר/למזג).
    seen_keys = {r.get("import_key") for r in records_list}
    stale = [v for v in rows if v.import_key and (v.source or "") == "import" and v.import_key not in seen_keys
             and v not in touched]
    report["not_in_file_count"] = len(stale)
    report["not_in_file"] = [{"id": v.id, "name": v.name, "city": v.city} for v in stale[:100]]
    db.flush()
    if dry_run:
        db.rollback()
    else:
        cache.invalidate_prefix("venues:")
    report["invalid_count"] = len(report["invalid"])
    report["matched_existing_count"] = len(report["matched_existing"])
    report["possible_duplicates_count"] = len(report["possible_duplicates"])
    return report


def _free_dedup_key(vals: dict, taken: set) -> str:
    """מפתח הדדופ הקיים הוא ייחודי לפי שם בלבד; שני אולמות באותו שם ביישובים
    שונים ("אולמי הנסיכה" בב"ש ובאשדוד) מקבלים סיומת יישוב, ובמקרה קיצון גם את
    מפתח הייבוא. ``record_venue`` מכיר את הסיומת (ראו ``venues._candidates``)."""
    base = _dedup_key(vals["name"])
    for key in (base, f"{base} · {_dedup_key(vals['city'])}" if vals["city"] else None,
                f"{base} · {vals['import_key']}"):
        if key and key not in taken:
            return key
    return f"{base} · {vals['import_key']} · {len(taken)}"


def _city_from_address(address: Optional[str]) -> str:
    """לשורות ישנות בלי עיר: "הרצל 5, תל אביב" → "תל אביב" (החלק האחרון אחרי פסיק)."""
    if not address or "," not in address:
        return ""
    return address.rsplit(",", 1)[1].strip()


def _name_only_match(cands: list, vals: dict):
    """שורה קיימת (לא מיובאת) באותו שם, בלי עיר ובלי כתובת שסותרת — כנראה אותו מקום.
    זוג שהקליד רק "אולמי X" בלי כתובת; לא נוסיף לידו עוד "אולמי X" מהקובץ."""
    for v in cands:
        if (v.source or "") == "import":
            continue
        if v.city or _city_from_address(v.address):
            continue
        if not (v.address or "").strip() or (vals["city"] and normalize(vals["city"]) in normalize(v.address)):
            return v
    return None


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None
