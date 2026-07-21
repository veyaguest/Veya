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


# מילות פתיחה שמסמנות "משפחה שלמה" — היעד הוא שם משפחה, לא אדם בודד.
_FAMILY_PREFIXES = ("משפחת", "משפחה", "למשפחת", "למשפחה", "משפ'", "משפ")


def match_all_ids(target: str, all_guests: list[dict], self_id: int) -> list[int]:
    """מרחיב שם-יעד ל*כל* המוזמנים התואמים (בשונה מ-resolve_name שבוחר אחד):

    - "משפחת כהן" / "משפחה כהן" → כל מי ששם המשפחה מופיע בשמו המלא.
    - שם מלא ("רותי כהן") → כל ההתאמות המדויקות.
    - שם פרטי בלבד ("דני") → כל המוזמנים שיש להם המילה הזו בשם.

    all_guests: [{id, full_name}] · self_id: המוזמן שכתב את ההערה (מוחרג תמיד).
    """
    t = " ".join((target or "").split())
    if not t:
        return []
    toks = t.split()
    others = [g for g in all_guests if g["id"] != self_id]

    # "משפחת X" → כל בני המשפחה (שם המשפחה מופיע בשם המלא).
    if toks[0] in _FAMILY_PREFIXES and len(toks) >= 2:
        surname_toks = toks[1:]
        ids = [
            g["id"] for g in others
            if all(s in g["full_name"].split() for s in surname_toks)
        ]
        return sorted(set(ids))

    # שם מלא מדויק — אם יש התאמות, מחזירים את כולן.
    exact = [g["id"] for g in others if " ".join(g["full_name"].split()) == t]
    if exact:
        return sorted(set(exact))

    # שם חלקי / שם פרטי בלבד → כל ההתאמות (כל ה"דנים" באולם).
    ids: list[int] = []
    for g in others:
        gtoks = g["full_name"].split()
        if len(toks) >= 2:
            if all(tok in gtoks for tok in toks):
                ids.append(g["id"])
        elif toks[0] in gtoks:
            ids.append(g["id"])
    return sorted(set(ids))


def build_pairs_from_guests(
    guests: list[dict],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """בונה ישירות מהערות המוזמנים את זוגות ה-avoid (קשיח) וה-together (רך),
    כשכל שם-יעד מורחב ל*כל* המוזמנים התואמים — שם פרטי כולל את כל בעלי השם,
    ו"משפחת X" כולל את כל בני המשפחה.

    נגזר טרי מ-notes_raw (לא מסתמך על constraints_parsed השמור), כדי שכללי
    "לא לשבת יחד" / "לשבת יחד" ייאכפו תמיד בסידור האוטומטי.

    guests: [{id, full_name, notes_raw}] · מחזיר: (forbidden_pairs, together_pairs)
    """
    name_dicts = [{"id": g["id"], "full_name": g.get("full_name", "")} for g in guests]
    forbidden: set[tuple[int, int]] = set()
    together: set[tuple[int, int]] = set()
    for g in guests:
        for rel in parse_relations(g.get("notes_raw") or ""):
            ids = match_all_ids(rel["target_text"], name_dicts, g["id"])
            bucket = forbidden if rel["type"] == "avoid" else together
            for m in ids:
                bucket.add((min(g["id"], m), max(g["id"], m)))
    return sorted(forbidden), sorted(together)


# ---------------------------------------------------------------------------
# העדפות מיקום ונגישות (שלב "הושבה חכמה") — מבוסס-כללים, בלי LLM.
#
# מזהה מההערות ביטויים כמו "ליד הרחבה" / "רחוק מהרעש" / "מבוגרים" / "בהריון"
# והופך אותם ל"העדפות" מובנות: {zone, dir, priority, reason}. אלו אינן חוקים
# קשיחים — הן ניקוד רך-חזק שמנוע השיבוץ שוקלל לפי מיקום השולחן באולם.
#
# zone: "dance_floor" | "bar" | "entrance" | "loud" | "accessible"
# dir:  "near" (רוצים קרוב) | "far" (רוצים רחוק)
# ---------------------------------------------------------------------------

_NEAR_DANCE = [
    "ליד הרחבה", "קרוב לרחבה", "על יד הרחבה", "ליד רחבת", "קרוב לרחבת",
    "רחבת הריקודים", "אוהבים לרקוד", "אוהבת לרקוד", "אוהב לרקוד",
    "רוצים לרקוד", "רוצה לרקוד", "ליד הריקודים", "קרוב לריקודים",
]
_NEAR_BAR = ["ליד הבר", "קרוב לבר", "על יד הבר", "צמוד לבר", "קרובים לבר"]
_NEAR_ENTRANCE = [
    "ליד הכניסה", "קרוב לכניסה", "ליד היציאה", "קרוב ליציאה",
    "צריך לצאת מוקדם", "צריכים לצאת מוקדם", "עוזבים מוקדם", "עוזב מוקדם",
    "יוצאים מוקדם", "יוצא מוקדם", "יוצאת מוקדם",
]
_FAR_LOUD = [
    "רחוק מהרעש", "רחוק מרעש", "רחוק מהמוזיקה", "רחוק ממוזיקה",
    "רחוק מהרמקולים", "רחוק מהרמקול", "רחוק מהבמה", "רחוק מהדיג'יי",
    "רחוק מהדי.ג'יי", "רחוק מהדיג׳יי", "לא ליד הרמקולים", "לא ליד הרעש",
    "מקום שקט", "פינה שקטה", "רוצים שקט", "רוצה שקט", "צריכים שקט", "צריך שקט",
]
_WHEELCHAIR = [
    "כיסא גלגלים", "כסא גלגלים", "כיסה גלגלים", "נגישות", "נגיש", "נכה",
    "מוגבל בניידות", "מוגבלת בניידות", "הליכון", "קביים", "מתקשה בהליכה",
]
_ELDERLY = [
    "מבוגר", "מבוגרת", "מבוגרים", "קשיש", "קשישה", "קשישים", "קשישות",
    "סבא", "סבתא", "גיל שלישי", "הורים מבוגרים",
]
_PREGNANT = ["בהריון", "בהיריון", "הרה", "אישה בהריון"]


def parse_preferences(note: str) -> list[dict]:
    """מפרק הערה חופשית להעדפות מיקום/נגישות מובנות (ללא כפילויות)."""
    prefs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    if not note:
        return prefs

    def add(zone: str, direction: str, reason: str) -> None:
        key = (zone, direction)
        if key in seen:
            return
        seen.add(key)
        prefs.append({"zone": zone, "dir": direction, "priority": "strong", "reason": reason})

    def has(triggers: list[str]) -> bool:
        return any(t in note for t in triggers)

    if has(_NEAR_DANCE):
        add("dance_floor", "near", "קרוב לרחבת הריקודים, כפי שביקשתם")
    if has(_NEAR_BAR):
        add("bar", "near", "קרוב לבר, כפי שביקשתם")
    if has(_NEAR_ENTRANCE):
        add("entrance", "near", "קרוב לכניסה, לנוחות יציאה")
    if has(_FAR_LOUD):
        add("loud", "far", "רחוק מהרעש והמוזיקה, כפי שביקשתם")
    if has(_WHEELCHAIR):
        add("accessible", "near", "נגיש וקרוב לכניסה")
    if has(_ELDERLY):
        add("loud", "far", "מותאם למבוגרים — רחוק מהרעש")
        add("accessible", "near", "מותאם למבוגרים — נגיש וקרוב לכניסה")
    if has(_PREGNANT):
        add("loud", "far", "מותאם למי שבהריון — רחוק מהרעש")
        add("accessible", "near", "נגיש וקרוב לכניסה")
    return prefs


def guest_preferences(
    notes_raw: Optional[str],
    guest_note: Optional[str],
    group_note: Optional[str],
) -> list[dict]:
    """מאחד העדפות ממספר מקורות: הערת הבעלים, הערת המוזמן, והערת הקבוצה.

    ללא כפילויות לפי (zone, dir). מקור "group" מקבל ניסוח שמסביר שזו העדפת קבוצה.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for text, src in ((notes_raw, "guest"), (guest_note, "guest"), (group_note, "group")):
        for p in parse_preferences(text or ""):
            key = (p["zone"], p["dir"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(p)
            item["source"] = src
            if src == "group":
                item["reason"] = "לפי הערת הקבוצה — " + item["reason"]
            out.append(item)
    return out
