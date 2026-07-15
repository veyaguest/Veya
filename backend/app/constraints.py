"""פרסור הערות חופשיות לאילוצי הושבה (שלב 4) — מבוסס-כללים.

עיקרון נעול (CLAUDE.md): הפרסור הופך טקסט חופשי לאילוצים מובנים, אבל חישוב
השיבוץ עצמו נשאר דטרמיניסטי. כאן אין LLM — מנוע כללים שמזהה ביטויים עבריים
נפוצים. בהמשך אפשר להחליף את ה"מוח" ב-LLM בלי לשנות את שאר הצינור.

זרימת העבודה:
1. `analyze_guest` מפרק את ההערה של מוזמן לרשימת "יחסים" (avoid / together)
   ומנסה להתאים כל שם-יעד למוזמן קיים.
2. אם שם עמום (למשל "דני" כשיש כמה) — הסטטוס הוא "ambiguous" ונדרשת הבהרה.
3. `build_forbidden_pairs` אוסף את יחסי ה-avoid שנפתרו לזוגות אסורים,
   שמוזנים ישירות למנוע השיבוץ.
"""
from __future__ import annotations

import re
from typing import Optional

# ביטויי "לא לשבת יחד" (חוק קשיח). נבדקים ראשונים כי הם מכילים את ביטויי ה-together.
AVOID_TRIGGERS = [
    "לא לשבת ביחד עם",
    "לא רוצים לשבת עם",
    "לא רוצה לשבת עם",
    "לא לשבת ליד",
    "לא לשבת עם",
    "מסוכסכת עם",
    "מסוכסך עם",
    "להרחיק מ",
    "בריב עם",
    "לא ליד",
    "רחוק מ",
    "לא עם",
    "רב עם",
]

# ביטויי "לשבת יחד" (העדפה רכה).
TOGETHER_TRIGGERS = [
    "רוצים לשבת עם",
    "רוצה לשבת עם",
    "לשבת ביחד עם",
    "לשבת ליד",
    "לשבת עם",
    "ביחד עם",
    "קרובים ל",
    "יחד עם",
    "קרוב ל",
    "ליד",
]

# מילים שמסמנות סוף שם-היעד (מה שאחריהן אינו חלק מהשם).
STOP_WORDS = ["כי", "בגלל", "כדי", "אבל", "שהם", "שהוא", "שהיא", "מפני"]

# מפרידים בין סעיפים בהערה.
_SEGMENT_SPLIT = re.compile(r"[,.;\n·|/]+|\s-\s|\bוגם\b")


def _clean_target(text: str) -> str:
    """מנקה את שם-היעד: מסיר רווחים, 'את' מוביל, וקוטע במילת-עצירה."""
    t = " ".join(text.split())
    if t.startswith("את "):
        t = t[3:]
    words = t.split()
    kept: list[str] = []
    for w in words:
        if w in STOP_WORDS:
            break
        kept.append(w)
        if len(kept) >= 4:  # שם-יעד סביר עד 4 מילים
            break
    return " ".join(kept).strip(" \t.-")


def parse_relations(note: str) -> list[dict]:
    """מפרק הערה לרשימת יחסים גולמיים: [{type, target_text}]."""
    relations: list[dict] = []
    if not note:
        return relations
    for segment in _SEGMENT_SPLIT.split(note):
        seg = segment.strip()
        if not seg:
            continue
        rel_type = None
        trigger_pos = -1
        trigger_len = 0
        # avoid קודם — קדימות לביטוי השלילי (שמכיל את החיובי).
        for kind, triggers in (("avoid", AVOID_TRIGGERS), ("together", TOGETHER_TRIGGERS)):
            for trig in triggers:
                pos = seg.find(trig)
                if pos != -1:
                    rel_type = kind
                    trigger_pos = pos
                    trigger_len = len(trig)
                    break
            if rel_type:
                break
        if not rel_type:
            continue
        target = _clean_target(seg[trigger_pos + trigger_len:])
        if target:
            relations.append({"type": rel_type, "target_text": target})
    return relations


def resolve_name(target: str, all_guests: list[dict], self_id: int) -> dict:
    """מתאים שם-יעד למוזמן. מחזיר סטטוס: resolved / ambiguous / unresolved."""
    t = " ".join(target.split())
    ttoks = t.split()
    if not ttoks:
        return {"status": "unresolved", "target_guest_id": None, "candidates": []}

    others = [g for g in all_guests if g["id"] != self_id]

    # 1) התאמת שם-מלא מדויקת
    exact = [g["id"] for g in others if " ".join(g["full_name"].split()) == t]
    if len(exact) == 1:
        return {"status": "resolved", "target_guest_id": exact[0], "candidates": exact}
    if len(exact) > 1:
        return {"status": "ambiguous", "target_guest_id": None, "candidates": exact}

    # 2) התאמה לפי מילים (שם פרטי בלבד, או תת-קבוצת מילים)
    matches: list[int] = []
    for g in others:
        gtoks = g["full_name"].split()
        if len(ttoks) >= 2:
            if all(tok in gtoks for tok in ttoks):
                matches.append(g["id"])
        else:
            if ttoks[0] in gtoks:
                matches.append(g["id"])

    if len(matches) == 1:
        return {"status": "resolved", "target_guest_id": matches[0], "candidates": matches}
    if len(matches) > 1:
        return {"status": "ambiguous", "target_guest_id": None, "candidates": matches}
    return {"status": "unresolved", "target_guest_id": None, "candidates": []}


def analyze_guest(guest: dict, all_guests: list[dict]) -> dict:
    """מפרק את ההערה של מוזמן ומתאים שמות. מחזיר constraints_parsed."""
    note = guest.get("notes_raw") or ""
    relations = []
    for rel in parse_relations(note):
        res = resolve_name(rel["target_text"], all_guests, guest["id"])
        relations.append(
            {
                "type": rel["type"],
                "target_text": rel["target_text"],
                "status": res["status"],
                "target_guest_id": res["target_guest_id"],
                "candidates": res["candidates"],
            }
        )
    return {"raw": note, "relations": relations}


def _pairs_of_type(guests: list[dict], rel_type: str) -> list[tuple[int, int]]:
    """אוסף זוגות (id,id) מיחסים שנפתרו מהסוג המבוקש, ללא כפילויות."""
    pairs: set[tuple[int, int]] = set()
    for g in guests:
        parsed = g.get("constraints_parsed") or {}
        for rel in parsed.get("relations", []):
            if rel.get("type") != rel_type:
                continue
            tgt = rel.get("target_guest_id")
            if rel.get("status") == "resolved" and tgt is not None:
                pairs.add((min(g["id"], tgt), max(g["id"], tgt)))
    return sorted(pairs)


def build_forbidden_pairs(guests: list[dict]) -> list[tuple[int, int]]:
    """זוגות אסורים (חוק קשיח) מיחסי avoid שנפתרו."""
    return _pairs_of_type(guests, "avoid")


def build_together_pairs(guests: list[dict]) -> list[tuple[int, int]]:
    """זוגות "לשבת יחד" (העדפה) מיחסי together שנפתרו."""
    return _pairs_of_type(guests, "together")
