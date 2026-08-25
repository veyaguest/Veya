#!/usr/bin/env python3
"""מייצר את רשימת הבנקים של VEYA מתוך הנתונים הרשמיים של **בנק ישראל**.

למה סקריפט ולא רשימה שנכתבה ביד: רשימת הבנקים בישראל זזה — בנקים מתמזגים
(אוצר החייל/פאג"י/יו-בנק לתוך הבינלאומי), נפתחים (אש ישראל, וואן זירו) ומשנים
שם. רשימה מומצאת או מועתקת מהאינטרנט מתיישנת בשקט, ובטופס שמפנה אליו כסף
אמיתי זו טעות יקרה. לכן הרשימה **נגזרת** משני מאגרים רשמיים, והסקריפט הזה
ניתן להרצה חוזרת כדי לרענן אותה.

    python3 tools/fetch_israeli_banks.py

שני המקורות (שניהם של בנק ישראל, דרך data.gov.il):

1. **"סניפים לסליקה"** — "גופים המאפשרים ביצוע העברות כספיות אליהם ומהם".
   זה המאגר התפעולי: מי שנמצא בו הוא מי שאפשר באמת להעביר אליו כסף. הוא
   הבסיס לרשימה, כי זו בדיוק השאלה של הטופס — לאן נעביר את המתנות.
2. **"רשימת תאגידים בנקאיים בישראל"** — המרשם הרשמי, כולל שדה ``Category``
   ("בנקים רגילים" / "בנקי חוץ" / "מוסדות כספיים" / "חברות שרותים משותפות").
   הוא מספק את הסיווג — מי מבין הגופים האלה הוא בכלל *בנק*.

## למה צריך סינון בכלל

מאגר הסליקה **אינו** רשימת בנקים. הוא כולל גם סולקים (ישראכרט, מקס), גופי
תשלומים חוץ-בנקאיים, ותשתיות שוק (בנק ישראל עצמו, שב"א, מרכז סליקה בנקאי).
אף אחד מהם אינו מקום שאדם פרטי מנהל בו חשבון עו"ש, ולכן אסור שיופיעו בטופס.

הסינון נגזר משדות של בנק ישראל — לא מרשימת החרגות שנכתבה לפי תחושה:

* ``close_date`` מלא            → סניף סגור, לא נספר.
* ``branch_type == 'חוץ בנקאי'`` → תווית של בנק ישראל עצמו לגוף לא-בנקאי.
* ``Category`` שאינו בנק        → "מוסדות כספיים"/"חברות שרותים משותפות".
* אין סניף קמעונאי **וגם** לא רשום כתאגיד בנקאי → סולק. זה הכלל שמוציא את
  ישראכרט ומקס, ובכל זאת **משאיר** את בנק אש: גם לו יש רק "יחידת ביצוע"
  (הוא חדש ועדיין בלי סניפים), אבל הוא רשום במרשם כ"בנקים רגילים".

היחיד שנשאר ידני הוא ``INFRASTRUCTURE`` — שלוש תשתיות שוק שאין להן שדה
שמסמן אותן ככאלה. כל אחת מתועדת בשמה ובסיבתה, וזו רשימת *החרגה* מנומקת,
לא רשימת בנקים מומצאת.

## לוגואים

הסקריפט **לא** מוריד לוגואים. סמלי הבנקים הם סימני מסחר רשומים, והורדה
שלהם מאתרי הבנקים אינה רישיון לשימוש בהם. השדה ``logo`` נשאר ריק, והממשק
מציג במקומו את קוד הבנק — שהוא ממילא המזהה שהזוג משווה מול אישור ניהול
החשבון שלו. אם וכאשר יתקבל אישור שימוש, אפשר למלא את השדה בלי לגעת בלוגיקה.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

CKAN = "https://data.gov.il/api/3/action/datastore_search"
CLEARING_BRANCHES = "b3f7616d-1c65-497d-afd5-d5ba972bfc1d"   # "סניפים לסליקה" – עברית
BANKING_CORPS = "ebb61778-e34c-4e67-8fcf-0e643d9cf8c2"       # "רשימת תאגידים בנקאיים" – עברית

DATASET_PAGE = "https://data.gov.il/dataset/branches_for_payments"
REGISTRY_PAGE = "https://data.gov.il/dataset/375"

# סיווגי בנק ישראל שנחשבים "בנק" לצורך חשבון של אדם פרטי.
BANK_CATEGORIES = {"בנקים רגילים", "בנקי חוץ"}

# סוגי סניף שמעידים על נוכחות קמעונאית אמיתית (להבדיל מ"יחידת ביצוע",
# שהיא יחידה תפעולית פנימית בלבד).
RETAIL_BRANCH_TYPES = {"רגיל", "מיוחד", "סניף דיגיטלי"}

# תשתיות שוק — לא מקום שאדם פרטי מנהל בו חשבון. אין במאגר שדה שמסמן אותן,
# ולכן זו ההחרגה הידנית היחידה. כל שורה מתועדת בסיבתה.
INFRASTRUCTURE = {
    99: "בנק ישראל — הבנק המרכזי; לא מנהל חשבונות לאנשים פרטיים",
    59: 'שירותי בנק אוטומטיים (שב"א) — מתג הכספומטים, לא בנק',
    50: "מרכז סליקה בנקאי (מס״ב) — תשתית סליקה בין־בנקאית",
}


def fetch(resource_id: str) -> list[dict]:
    """שולף מאגר שלם מ-CKAN בעמודים של 1000."""
    out: list[dict] = []
    offset = 0
    while True:
        url = f"{CKAN}?resource_id={resource_id}&limit=1000&offset={offset}"
        with urllib.request.urlopen(url, timeout=120) as fh:
            payload = json.load(fh)
        if not payload.get("success"):
            raise SystemExit(f"CKAN החזיר כישלון עבור {resource_id}")
        result = payload["result"]
        out.extend(result["records"])
        if len(out) >= result["total"]:
            return out
        offset += 1000


def display_name(legal: str) -> str:
    """שם לתצוגה — בלי סיומת התאגיד. גזירה מכנית, לא ניסוח מחדש."""
    name = legal.strip()
    for suffix in (' בע"מ', " בע״מ", " בעמ"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def build() -> tuple[list[dict], list[tuple]]:
    branches = fetch(CLEARING_BRANCHES)
    corps = fetch(BANKING_CORPS)

    category = {int(c["Bank_Code"]): c["Category"] for c in corps}
    registry_name = {int(c["Bank_Code"]): c["Bank_Name"] for c in corps}

    # רק סניפים פתוחים, ורק כאלה שבנק ישראל לא תייג כחוץ-בנקאיים.
    live = [
        b for b in branches
        if not (b.get("close_date") or "").strip() and b.get("branch_type") != "חוץ בנקאי"
    ]

    types: dict[int, set] = defaultdict(set)
    clearing_name: dict[int, str] = {}
    retail_count: dict[int, int] = defaultdict(int)
    for b in live:
        code = int(b["id"])
        types[code].add(b.get("branch_type"))
        clearing_name[code] = b["name"]
        if b.get("branch_type") in RETAIL_BRANCH_TYPES:
            retail_count[code] += 1

    banks, rejected = [], []
    for code in sorted(types):
        cat = category.get(code)
        if code in INFRASTRUCTURE:
            rejected.append((code, clearing_name[code], INFRASTRUCTURE[code]))
            continue
        if cat is not None and cat not in BANK_CATEGORIES:
            rejected.append((code, clearing_name[code], f"סיווג בנק ישראל: {cat}"))
            continue
        if not (types[code] & RETAIL_BRANCH_TYPES) and cat is None:
            rejected.append(
                (code, clearing_name[code], "אין סניף קמעונאי ולא רשום כתאגיד בנקאי — סולק/גוף תשלומים")
            )
            continue
        legal = registry_name.get(code, clearing_name[code])
        banks.append(
            {
                "code": code,
                "name": display_name(legal),
                "legal_name": legal,
                "_retail": retail_count.get(code, 0),
            }
        )

    # סדר התצוגה: לפי מספר הסניפים הקמעונאיים בפועל — כך הבנקים שרוב הציבור
    # מחזיק בהם חשבון נמצאים בראש הרשימה. סדר נגזר מנתונים, לא מהעדפה.
    banks.sort(key=lambda b: (-b["_retail"], b["code"]))
    for b in banks:
        b.pop("_retail")
    return banks, rejected


HEADER = "רשימת הבנקים נוצרה אוטומטית מנתוני בנק ישראל — אין לערוך ידנית."


def write_python(banks: list[dict], path: Path, stamp: str) -> None:
    rows = "\n".join(
        f'    Bank(code={b["code"]}, name={b["name"]!r}, legal_name={b["legal_name"]!r}),'
        for b in banks
    )
    path.write_text(
        f'''"""{HEADER}

מקור: בנק ישראל דרך data.gov.il —
  · "סניפים לסליקה"                  {DATASET_PAGE}
  · "רשימת תאגידים בנקאיים בישראל"   {REGISTRY_PAGE}

נוצר: {stamp} · לרענון: ``python3 tools/fetch_israeli_banks.py``
הכללים שלפיהם נבחרו הבנקים מתועדים בסקריפט עצמו.
"""
from __future__ import annotations

from typing import NamedTuple


class Bank(NamedTuple):
    code: int
    name: str
    legal_name: str


#: מקור הנתונים, לתצוגה ולתיעוד.
SOURCE = "בנק ישראל · data.gov.il"
SOURCE_UPDATED = "{stamp}"

BANKS: tuple[Bank, ...] = (
{rows}
)

BY_CODE: dict[int, Bank] = {{b.code: b for b in BANKS}}
''',
        encoding="utf-8",
    )


def write_typescript(banks: list[dict], path: Path, stamp: str) -> None:
    rows = "\n".join(
        f'  {{ code: {b["code"]}, name: {json.dumps(b["name"], ensure_ascii=False)},'
        f' legalName: {json.dumps(b["legal_name"], ensure_ascii=False)} }},'
        for b in banks
    )
    path.write_text(
        f'''/* {HEADER}
 *
 * מקור: בנק ישראל דרך data.gov.il —
 *   · "סניפים לסליקה"                {DATASET_PAGE}
 *   · "רשימת תאגידים בנקאיים בישראל" {REGISTRY_PAGE}
 *
 * נוצר: {stamp} · לרענון: `python3 tools/fetch_israeli_banks.py`
 * הכללים שלפיהם נבחרו הבנקים מתועדים בסקריפט עצמו.
 */

export type Bank = {{
  /** קוד הבנק כפי שבנק ישראל מגדיר אותו — 12 = הפועלים, 10 = לאומי. */
  code: number
  /** שם לתצוגה, בלי סיומת התאגיד. */
  name: string
  /** השם המשפטי המלא, כפי שמופיע במרשם. */
  legalName: string
}}

/** מקור הנתונים — מוצג למשתמש מתחת לבורר הבנקים. */
export const BANKS_SOURCE = 'בנק ישראל'
export const BANKS_UPDATED = '{stamp}'

/** מסודר לפי מספר הסניפים בפועל: הבנקים הגדולים בראש. */
export const BANKS: readonly Bank[] = [
{rows}
]

export const BANK_BY_CODE: ReadonlyMap<number, Bank> = new Map(BANKS.map((b) => [b.code, b]))
''',
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    stamp = date.today().isoformat()
    banks, rejected = build()

    write_python(banks, root / "backend" / "app" / "banks_data.py", stamp)
    write_typescript(banks, root / "frontend" / "src" / "data" / "banks.ts", stamp)

    print(f"נכתבו {len(banks)} בנקים (מקור: בנק ישראל, {stamp})\n")
    for b in banks:
        print(f"  {b['code']:>3}  {b['name']}")
    print(f"\nהוחרגו {len(rejected)}:")
    for code, name, why in rejected:
        print(f"  {code:>3}  {name} — {why}")


if __name__ == "__main__":
    sys.exit(main())
