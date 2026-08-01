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

# מילות שלילה. **קריטי:** בלעדיהן "לא יושב ליד משה" היה מתפרש כ-together
# (הטריגר "ליד" נמצא, ה"לא" שלפניו מתעלמים ממנו) — כלומר המנוע היה מנסה
# להושיב יחד בדיוק את מי שביקשו להפריד. רשימת טריגרים שטוחה לעולם לא תכסה
# את כל הנטיות בעברית ("לא יושב"/"לא יושבת"/"לא יושבים"/"שלא ישב"), ולכן
# הפתרון הוא זיהוי שלילה כללי ולא עוד ביטוי ברשימה.
_NEGATIONS = {"לא", "אל", "אין", "אסור", "ללא", "שלא", "בלי", "נמנע", "נא"}

# כמה מילים אחורה מהטריגר מחפשים שלילה. חלון קצר בכוונה: "לא אכפת לי,
# שישבו ליד משה" — ה"לא" שייך למשפט אחר ולא אמור להפוך את המשמעות.
_NEGATION_WINDOW = 4

# מילים שמסמנות סוף שם-היעד (מה שאחריהן אינו חלק מהשם).
STOP_WORDS = ["כי", "בגלל", "כדי", "אבל", "שהם", "שהוא", "שהיא", "מפני"]

# מילים שמתארות **אזור באולם**, לא אדם. הטריגר "רחוק מ" מופיע גם ב-
# AVOID_TRIGGERS וגם בביטויי העדפת-אזור ("רחוק מהרעש"), ולכן בלי הרשימה הזו
# "רחוק מהרעש" היה נקרא גם כיחס avoid ליעד בשם "הרעש" — יחס מזויף שמלכלך את
# רשימת האילוצים ואת תור ההבהרות. אזור מטופל ב-parse_preferences בלבד.
_ZONE_WORDS = {
    "רעש", "הרעש", "מוזיקה", "המוזיקה", "רמקול", "רמקולים", "הרמקול",
    "הרמקולים", "במה", "הבמה", "דיג'יי", "הדיג'יי", "דיגיי", "הדיגיי",
    "די.ג'יי", "dj", "רחבה", "הרחבה", "ריקודים", "הריקודים", "בר", "הבר",
    "כניסה", "הכניסה", "יציאה", "היציאה", "שירותים", "השירותים",
}

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
        # שלילה הופכת "לשבת יחד" ל"לא לשבת יחד". זה מכסה את כל הנטיות
        # ("לא יושב ליד" / "לא יושבת ליד" / "שלא ישבו ליד" / "אסור ליד")
        # בלי להוסיף כל ניסוח לרשימה. אי-זיהוי כאן אינו "החמצה" אלא
        # **היפוך משמעות** — המנוע היה מקרב את מי שביקשו להרחיק.
        if rel_type == "together" and _has_negation_before(seg, trigger_pos):
            rel_type = "avoid"
        target = _clean_target(seg[trigger_pos + trigger_len:])
        if not target:
            continue
        # "רחוק מהרעש" / "ליד הבר" מתארים אזור באולם, לא אדם — הם מטופלים
        # ב-parse_preferences. בלי הבדיקה הזו נוצר יחס avoid ליעד "הרעש".
        if _is_zone_target(target):
            continue
        relations.append({"type": rel_type, "target_text": target})
    return relations


def _has_negation_before(segment: str, trigger_pos: int) -> bool:
    """האם יש מילת שלילה בסמוך *לפני* הטריגר, באותו סעיף?

    מסתכלים רק על ``_NEGATION_WINDOW`` המילים שקדמו לטריגר — שלילה רחוקה
    שייכת בדרך כלל למשפט אחר ("לא אכפת לי, שישבו ליד משה").
    """
    words = segment[:trigger_pos].split()
    window = words[-_NEGATION_WINDOW:]
    for i, raw in enumerate(window):
        word = raw.strip(".,;:!?\"'()־-")
        if word not in _NEGATIONS:
            continue
        # "בלי בעיה לשבת ליד X" — הסכמה, לא שלילה.
        nxt = window[i + 1].strip(".,;:!?\"'()־-") if i + 1 < len(window) else ""
        if word == "בלי" and nxt.startswith("בעי"):
            continue
        return True
    return False


def _is_zone_target(target: str) -> bool:
    """האם שם-היעד מתאר אזור באולם ולא אדם/משפחה/קבוצה."""
    tokens = [t.strip("\"'.,־-") for t in target.split()]
    meaningful = [t for t in tokens if t]
    if not meaningful:
        return False
    # מספיק שהמילה הראשונה היא אזור ("הרעש והמוזיקה", "הבר").
    return meaningful[0].lower() in _ZONE_WORDS


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
    """מפרק את הערת ההושבה של מוזמן ומתאים שמות. מחזיר constraints_parsed.

    קורא **רק** מ-``seating_notes`` — הערה פנימית (``notes_raw``) לעולם לא
    מנותחת לאילוצים.
    """
    note = guest.get("seating_notes") or ""
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


def _group_matches(target: str, others: list[dict], event_type: str | None) -> list[int]:
    """מרחיב שם-**קבוצה** מהלקסיקון לכל המוזמנים שמשויכים לקבוצה הזו.

    מממש את "הפרדה בין קבוצות" / "התנגשות דרך קשר קבוצתי": הערת הושבה
    כמו "לא ליד עובדים" או "יחד עם משפחת האב" צריכה לחול על כל בני הקבוצה,
    לא רק על מי שבמקרה קוראים לו כך.

    Event-first: התוויות נשאבות מהלקסיקון לפי ``event_type`` — אירוע עסקי
    מקבל עובדים/לקוחות/ספקים, בר מצווה מקבל משפחת האב/האם/כיתה — בלי
    רשימת מונחים חתונתית קשיחה.
    """
    from app.event_terms import get_event_terms  # ייבוא מקומי — הימנעות ממעגל

    t = " ".join((target or "").split()).strip(" \t.-\"'")
    if not t:
        return []
    lowered = t.lower()
    terms = get_event_terms(event_type)
    for key, label in terms.group_options:
        if key == "other":
            continue  # "אחר" אינה קבוצה משמעותית להרחקה/קירוב
        label_norm = label.lower()
        # התאמה דו-כיוונית: "עובדים" מול התווית "עובדים", וגם "צוות/חוגים"
        # מול "צוות". נדרשת מילה שלמה כדי ש"משפחה" לא יבלע "משפחת כהן".
        if lowered == label_norm or label_norm in lowered or lowered in label_norm:
            return sorted({g["id"] for g in others if g.get("group_type") == key})
    return []


def match_all_ids(
    target: str,
    all_guests: list[dict],
    self_id: int,
    event_type: str | None = None,
) -> list[int]:
    """מרחיב שם-יעד ל*כל* המוזמנים התואמים (בשונה מ-resolve_name שבוחר אחד):

    - שם קבוצה מהלקסיקון ("עובדים", "משפחת האב") → כל בני הקבוצה.
    - "משפחת כהן" / "משפחה כהן" → כל מי ששם המשפחה מופיע בשמו המלא.
    - שם מלא ("רותי כהן") → כל ההתאמות המדויקות.
    - שם פרטי בלבד ("דני") → כל המוזמנים שיש להם המילה הזו בשם.

    all_guests: [{id, full_name, group_type}] · self_id: כותב ההערה (מוחרג).
    event_type: לשאיבת תוויות הקבוצות מהלקסיקון (None => חתונה).
    """
    t = " ".join((target or "").split())
    if not t:
        return []
    toks = t.split()
    others = [g for g in all_guests if g["id"] != self_id]

    # קבוצה קודם: "משפחת האב" היא תווית קבוצה בבר מצווה, ורק אם אין קבוצה
    # כזו נופלים לפרשנות "שם משפחה" הרגילה.
    group_ids = _group_matches(t, others, event_type)
    if group_ids:
        return group_ids

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
    event_type: str | None = None,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """בונה ישירות מהערות המוזמנים את זוגות ה-avoid (קשיח) וה-together (רך),
    כשכל שם-יעד מורחב ל*כל* המוזמנים התואמים — שם פרטי כולל את כל בעלי השם,
    ו"משפחת X" כולל את כל בני המשפחה.

    נגזר טרי מ-seating_notes (לא מסתמך על constraints_parsed השמור), כדי
    שכללי "לא לשבת יחד" / "לשבת יחד" ייאכפו תמיד בסידור האוטומטי. ההערה
    הפנימית (notes_raw) לא נקראת כאן במכוון.

    guests: [{id, full_name, seating_notes}] · מחזיר: (forbidden, together)
    """
    name_dicts = [
        {
            "id": g["id"],
            "full_name": g.get("full_name", ""),
            "group_type": g.get("group_type", "other"),
        }
        for g in guests
    ]
    forbidden: set[tuple[int, int]] = set()
    together: set[tuple[int, int]] = set()
    for g in guests:
        for rel in parse_relations(g.get("seating_notes") or ""):
            ids = match_all_ids(rel["target_text"], name_dicts, g["id"], event_type)
            bucket = forbidden if rel["type"] == "avoid" else together
            for m in ids:
                bucket.add((min(g["id"], m), max(g["id"], m)))
    # חוק קשיח גובר: אם זוג הופיע גם כ"יחד" (למשל דרך קבוצה) וגם כ"לא יחד"
    # (בקשה מפורשת), האיסור מנצח — אחרת בקשה רכה הייתה מסתירה חוק.
    together -= forbidden
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
    seating_notes: Optional[str],
    guest_note: Optional[str],
    group_note: Optional[str],
) -> list[dict]:
    """מאחד העדפות אזור/נגישות ממספר מקורות.

    - ``seating_notes`` — הערת ההושבה שהבעלים כתב/ה על המוזמן.
    - ``guest_note`` — מה שהמוזמן עצמו כתב בדף אישור ההגעה ("כיסא גלגלים",
      "יש לנו תינוק"). נשאר מקור לגיטימי גם אחרי הפרדת ההערות: זו בקשת
      נגישות של המוזמן עצמו, לא הערה תפעולית של הבעלים.
    - ``group_note`` — העדפת הקבוצה כולה ("רחוק מהרעש").

    ההערה הפנימית (``notes_raw``) **לא** נכללת כאן במכוון.
    ללא כפילויות לפי (zone, dir). מקור "group" מקבל ניסוח שמסביר שזו העדפת קבוצה.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for text, src in ((seating_notes, "guest"), (guest_note, "guest"), (group_note, "group")):
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
