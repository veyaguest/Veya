"""מנוע השיבוץ הדטרמיניסטי של VEYA (שלב 3).

מבוסס על ה-POC (`veya_seating_poc.py`): שיבוץ חמדני ראשוני (Greedy) ואחריו
שיפור מקומי (Local Search). המנוע כאן עובד על מוזמנים אמיתיים מה-DB.

עיקרון נעול (CLAUDE.md): ה-LLM אחראי לפרשנות טקסט ולשיח בלבד — חישוב השיבוץ
עצמו נשאר דטרמיניסטי, כדי שחוקים קשיחים לעולם לא ייכשלו בגלל "הזיה" של מודל שפה.

מושגים:
- "party" (חבורה) = רשומת מוזמן אחת. תופסת `party_size` כיסאות ותמיד יושבת יחד
  (משפחה לא מתפצלת בין שולחנות).
- חוקים קשיחים (חובה): קיבולת שולחן, כל חבורה משובצת פעם אחת, זוגות אסורים
  ("לא לשבת יחד") לא באותו שולחן.
- חוקים רכים (ניקוד): מושיבים יחד אנשים מאותו צד (חתן/כלה) ומאותה קבוצה
  (משפחה/חברים/עבודה), כדי שהשולחנות יהיו קוהרנטיים.
- העדפות מיקום (ניקוד רך-חזק, מודע-מיקום): כשמסופקים מיקומי השולחנות באולם
  ומרכזי האזורים (רחבה/בר/כניסה/רעש), מוזמן שביקש "קרוב לרחבה"/"רחוק מהרעש"/
  נגישות מקבל ניקוד גבוה לשולחנות המתאימים. זה לעולם לא גובר על חוק קשיח.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

from app.event_terms import side_axis_label

# ניקוד חוקים רכים: תגמול על זוג חבורות באותו שולחן. ברירת מחדל = חתונה
# (ולכל סוג אירוע שלא הוגדר לו משקל ייעודי — אף פעם לא נוגעים בחוויית החתונה).
SAME_SIDE_BONUS = 3    # אותו צד (חתן/כלה)
SAME_GROUP_BONUS = 2   # אותה קבוצה (משפחה קרובה/חברים/עבודה...)
TOGETHER_BONUS = 15    # בקשת "לשבת עם" מפורשת (PRD 7.4) — קבוע לכל סוג אירוע: בקשה
                        # מפורשת של המארגן/ת נשקלת באותה חוזקה בכל סוג אירוע.

# משקלי "אותו צד"/"אותה קבוצה" לפי event_type — ל-Event-first architecture.
# עקרון: חתונה נשארת בדיוק כמו שהייתה (SAME_SIDE_BONUS/SAME_GROUP_BONUS
# למעלה) כדי לא לפגוע בחוויית החתונה הקיימת. שאר הסוגים ברירת המחדל שלהם
# זהה לחתונה, חוץ מ-business: שם "הצד" (מארח א/ב) כמעט לא רלוונטי לאירוע
# עסקי, ואילו "הקבוצה" (מחלקה/עובדים/לקוחות) היא הציר המשמעותי לישיבה
# יחד — לכן מקבל דגש הפוך. שאר ההתאמות העדינות יותר (bar/bat_mitzvah,
# brit, henna, family) נשארות פתוחות להחלטת מוצר עתידית לפי משוב אמיתי —
# ראו open-questions.md.
SEATING_WEIGHTS_BY_EVENT_TYPE: dict[str, dict[str, int]] = {
    "business": {"same_side": 1, "same_group": 4},
}


def get_seating_weights(event_type: str | None) -> dict[str, int]:
    """מחזיר {same_side, same_group} למשקלי הניקוד הרך, לפי event_type.

    ברירת המחדל (לכל סוג שלא הוגדר לו במפורש) זהה לחתונה — שינוי עדין
    למשקל קיים דורש עדכון מפורש ב-SEATING_WEIGHTS_BY_EVENT_TYPE, לא ניחוש.
    """
    defaults = {"same_side": SAME_SIDE_BONUS, "same_group": SAME_GROUP_BONUS}
    return {**defaults, **SEATING_WEIGHTS_BY_EVENT_TYPE.get(event_type or "wedding", {})}


# ניקוד העדפת מיקום/נגישות מסופקת (מנורמל 0..1 לפי מרחק יחסי באולם).
STRONG_PREF_WEIGHT = 10.0
# סף שבו נחשיב העדפת מיקום כ"סופקה" לצורך ההסבר למשתמש (0=גרוע, 1=מושלם).
SATISFY_THRESHOLD = 0.55

LOCAL_SEARCH_ITERATIONS = 4000


@dataclass
class Party:
    """חבורה = רשומת מוזמן אחת שיושבת יחד."""

    id: int
    name: str
    side: str
    group: str
    size: int


@dataclass
class SeatingResult:
    tables: list[dict]          # [{table_number, seats_used, capacity, parties: [...]}]
    total_people: int
    num_tables: int
    seats_per_table: int
    score: int
    hard_ok: bool               # True אם אין הפרת חוק קשיח
    unseated: list[int]         # מזהי חבורות שלא הצלחנו לשבץ (אמור להיות ריק)


def _capacity_needed(parties: list[Party], seats_per_table: int) -> int:
    """מספר שולחנות מינימלי שמבטיח קיבולת מספקת + עודף קטן (כמו במציאות)."""
    total_people = sum(p.size for p in parties)
    base = math.ceil(total_people / seats_per_table) if total_people else 0
    return base + 1 if base else 0


def _seats_used(members: list[Party]) -> int:
    return sum(p.size for p in members)


def _has_forbidden(members: list[Party], candidate: Party, forbidden: set) -> bool:
    """האם הושבת candidate ליד מישהו מ-members מפרה זוג אסור?"""
    for seated in members:
        if (min(seated.id, candidate.id), max(seated.id, candidate.id)) in forbidden:
            return True
    return False


def _violates_hard(assignment: dict, caps: dict, forbidden: set) -> bool:
    """קיבולת שולחן (פר-שולחן) + זוגות אסורים באותו שולחן."""
    for tid, members in assignment.items():
        if _seats_used(members) > caps[tid]:
            return True
        ids = [p.id for p in members]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if (min(ids[i], ids[j]), max(ids[i], ids[j])) in forbidden:
                    return True
    return False


# ---------------------------------------------------------------------------
# מודעות-מיקום: המרת מרחקים לניקוד אזור.
# ---------------------------------------------------------------------------

def _zone_norms(positions: dict, zones: dict) -> dict:
    """לכל אזור (רחבה/בר/כניסה/רעש), מרחק *מנורמל* [0..1] מכל שולחן למרכז
    האזור הקרוב אליו (0 = הכי קרוב, 1 = הכי רחוק). מנורמל לפי המרחק המרבי,
    כך שהניקוד חסר-יחידות ולא תלוי בגודל האולם."""
    norms: dict[str, dict] = {}
    for key, centers in (zones or {}).items():
        if not centers:
            continue
        raw = {}
        for tid, (x, y) in positions.items():
            raw[tid] = min(math.hypot(x - cx, y - cy) for cx, cy in centers)
        dmax = max(raw.values()) if raw else 0.0
        norms[key] = {tid: (raw[tid] / dmax if dmax > 0 else 0.0) for tid in raw}
    return norms


def _pref_contrib(pref: dict, tid, norms: dict) -> float:
    """כמה שולחן tid מספק העדפה בודדת (0..1). near → קרוב עדיף; far → רחוק עדיף.
    'accessible' (נגישות) ממופה לקרבה לכניסה — הכי נוח להגעה."""
    zone = pref["zone"]
    key = "entrance" if zone == "accessible" else zone
    zn = norms.get(key)
    if not zn or tid not in zn:
        return 0.0
    nd = zn[tid]
    return (1.0 - nd) if pref["dir"] == "near" else nd


def _pref_score_map(parties, tids, norms, preferences) -> dict:
    """ניקוד העדפה מצטבר לכל (party_id, table): סכום ההעדפות × המשקל."""
    m: dict[tuple, float] = {}
    if not preferences:
        return m
    for p in parties:
        prefs = preferences.get(p.id)
        if not prefs:
            continue
        for tid in tids:
            s = sum(_pref_contrib(pr, tid, norms) for pr in prefs)
            if s:
                m[(p.id, tid)] = STRONG_PREF_WEIGHT * s
    return m


def _table_violates(members: list[Party], cap: int, forbidden: set) -> bool:
    """חוק קשיח לשולחן בודד: קיבולת + זוג אסור. משמש לבדיקה נקודתית ומהירה."""
    if _seats_used(members) > cap:
        return True
    ids = [p.id for p in members]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if (min(ids[i], ids[j]), max(ids[i], ids[j])) in forbidden:
                return True
    return False


def _table_score(members: list[Party], tid, together: set, pref_score: dict, weights: dict) -> float:
    """ניקוד רך לשולחן בודד — צד/קבוצה/'לשבת עם' + העדפות מיקום."""
    s = 0.0
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            a, b = members[i], members[j]
            if a.side == b.side and a.side != "shared":
                s += weights["same_side"]
            if a.group == b.group and a.group != "other":
                s += weights["same_group"]
            if (min(a.id, b.id), max(a.id, b.id)) in together:
                s += TOGETHER_BONUS
    if pref_score:
        for p in members:
            s += pref_score.get((p.id, tid), 0.0)
    return s


def _score(assignment: dict, together: set, pref_score: dict, weights: dict) -> float:
    """ניקוד כולל: סכום ניקוד כל השולחנות."""
    return sum(_table_score(m, tid, together, pref_score, weights) for tid, m in assignment.items())


def _greedy(parties, tids, caps, forbidden, pref_score) -> dict:
    """שיבוץ חמדני ראשוני: חבורות גדולות קודם. מבין השולחנות האפשריים בוחר את
    זה שממקסם את העדפת המיקום של החבורה, ואז את הכי הרבה מקום פנוי."""
    assignment: dict = {t: [] for t in tids}
    remaining = dict(caps)
    for party in sorted(parties, key=lambda p: p.size, reverse=True):
        feasible = [
            t for t in tids
            if remaining[t] >= party.size and not _has_forbidden(assignment[t], party, forbidden)
        ]
        if not feasible:
            continue  # אין מקום — יסומן כ-unseated
        best_t = max(feasible, key=lambda t: (pref_score.get((party.id, t), 0.0), remaining[t]))
        assignment[best_t].append(party)
        remaining[best_t] -= party.size
    return assignment


def _local_search(assignment, caps, forbidden, together, pref_score, rng, weights) -> None:
    """שיפור מקומי (in-place): חילופי/העברות חבורות בין שולחנות כל עוד לא נשבר
    חוק קשיח והניקוד לא יורד. משלב swap (החלפה) ו-move (העברה למקום פנוי).

    ביצועים: כל צעד נוגע רק בשני שולחנות, לכן בודקים חוקיות ומחשבים ניקוד רק
    להם (דלתא מקומית) במקום לסרוק את כל המפה — קריטי ל-200 אורחים בפחות משנייה."""
    tids = list(assignment.keys())
    if len(tids) < 2:
        return

    def tscore(tid):
        return _table_score(assignment[tid], tid, together, pref_score, weights)

    for _ in range(LOCAL_SEARCH_ITERATIONS):
        t1 = rng.choice(tids)
        if not assignment[t1]:
            continue
        i1 = rng.randrange(len(assignment[t1]))
        p1 = assignment[t1][i1]
        t2 = rng.choice(tids)
        if t2 == t1:
            continue
        before = tscore(t1) + tscore(t2)

        if rng.random() < 0.5 and assignment[t2]:
            # החלפה בין שתי חבורות — שני השולחנות עלולים להפר חוק קשיח.
            i2 = rng.randrange(len(assignment[t2]))
            p2 = assignment[t2][i2]
            assignment[t1][i1], assignment[t2][i2] = p2, p1
            if (
                _table_violates(assignment[t1], caps[t1], forbidden)
                or _table_violates(assignment[t2], caps[t2], forbidden)
                or tscore(t1) + tscore(t2) < before
            ):
                assignment[t1][i1], assignment[t2][i2] = p1, p2  # ביטול
        else:
            # העברת חבורה למקום פנוי — רק שולחן היעד עלול להפר קיבולת/זוג אסור.
            assignment[t1].pop(i1)
            assignment[t2].append(p1)
            if (
                _table_violates(assignment[t2], caps[t2], forbidden)
                or tscore(t1) + tscore(t2) < before
            ):
                assignment[t2].pop()  # ביטול
                assignment[t1].insert(i1, p1)


def _reasons_for(party, members, tid, norms, preferences, event_type: str | None = "wedding") -> list[str]:
    """הסבר קצר בעברית למה החבורה שובצה כאן — העדפות שסופקו + קרבה לקבוצה/צד."""
    reasons: list[str] = []
    prefs = preferences.get(party.id) if preferences else None
    if prefs:
        for pr in prefs:
            if _pref_contrib(pr, tid, norms) >= SATISFY_THRESHOLD:
                reasons.append(pr["reason"])
    same_group = any(
        o.id != party.id and o.group == party.group and party.group != "other"
        for o in members
    )
    same_side = any(
        o.id != party.id and o.side == party.side and party.side != "shared"
        for o in members
    )
    if same_group:
        reasons.append("יושבים ליד בני הקבוצה שלכם")
    elif same_side:
        reasons.append(f"יושבים בצד המתאים ({side_axis_label(event_type)})")
    return reasons[:3]


def recommend_seats(
    guest: dict,
    tables: list[dict],
    forbidden_pairs: Optional[list[tuple[int, int]]] = None,
    together_pairs: Optional[list[tuple[int, int]]] = None,
    zones: Optional[dict] = None,
    guest_prefs: Optional[list[dict]] = None,
    include_reserve: bool = True,
    top_n: int = 3,
    event_type: str | None = "wedding",
) -> list[dict]:
    """ממליץ על השולחנות המתאימים ביותר לשבץ בהם מוזמן בודד (מצב יום האירוע).

    דטרמיניסטי לחלוטין — אותו קלט נותן אותה תשובה. ה-LLM לא מעורב: אותם משקלים
    בדיוק כמו במנוע השיבוץ (צד/קבוצה/"לשבת עם" + העדפות מיקום). לא משבץ — רק
    מדרג מועמדים כשירים ומצרף "למה". שולחן פסול (אין מקום / זוג אסור) נשמט.

    guest: {id, side, group_type, party_size}
    tables: [{table_number, name, capacity, is_reserve, x, y,
              members: [{id, side, group_type, size}]}]
    zones / guest_prefs: כמו במנוע — לניקוד העדפות מיקום מההערות.
    """
    forbidden: set = set()
    for a, b in (forbidden_pairs or []):
        forbidden.add((min(a, b), max(a, b)))
    together: set = set()
    for a, b in (together_pairs or []):
        together.add((min(a, b), max(a, b)))

    gid = guest["id"]
    gside = guest.get("side", "shared")
    ggroup = guest.get("group_type", "other")
    gsize = max(1, int(guest.get("party_size", 1)))
    weights = get_seating_weights(event_type)

    # נורמות אזור לניקוד העדפות מיקום — רק אם יש מיקומי שולחנות והעדפות.
    positions = {
        int(t["table_number"]): (float(t.get("x", 0)), float(t.get("y", 0)))
        for t in tables
        if "x" in t and "y" in t
    }
    norms = _zone_norms(positions, zones or {}) if (positions and guest_prefs) else {}

    out: list[dict] = []
    for t in tables:
        tnum = int(t["table_number"])
        is_reserve = bool(t.get("is_reserve", False))
        if is_reserve and not include_reserve:
            continue
        members = t.get("members", [])
        used = sum(int(m.get("size", 1)) for m in members)
        cap = int(t.get("capacity", 12))
        free = cap - used
        if free < gsize:
            continue  # אין מספיק מקום — פסול
        if any(
            (min(gid, int(m["id"])), max(gid, int(m["id"]))) in forbidden
            for m in members
        ):
            continue  # זוג "לא לשבת יחד" — פסול (חוק קשיח)

        score = 0.0
        for m in members:
            mid = int(m["id"])
            if m.get("side") == gside and gside != "shared":
                score += weights["same_side"]
            if m.get("group_type") == ggroup and ggroup != "other":
                score += weights["same_group"]
            if (min(gid, mid), max(gid, mid)) in together:
                score += TOGETHER_BONUS

        reasons: list[str] = []
        if guest_prefs and norms:
            for pr in guest_prefs:
                contrib = _pref_contrib(pr, tnum, norms)
                if contrib:
                    score += STRONG_PREF_WEIGHT * contrib
                if contrib >= SATISFY_THRESHOLD:
                    reasons.append(pr["reason"])
        if any(m.get("group_type") == ggroup and ggroup != "other" for m in members):
            reasons.append("יושבים ליד בני הקבוצה שלכם")
        elif any(m.get("side") == gside and gside != "shared" for m in members):
            reasons.append(f"יושבים בצד המתאים ({side_axis_label(event_type)})")
        if is_reserve:
            reasons.append("שולחן רזרבה פנוי")

        out.append(
            {
                "table_number": tnum,
                "table_name": str(t.get("name", "")),
                "is_reserve": is_reserve,
                "free_seats": free,
                "score": round(score, 2),
                "reasons": reasons[:3],
            }
        )

    # דירוג: ניקוד חברתי גבוה קודם; בשוויון מעדיפים שולחן פעיל (לא לבזבז רזרבה),
    # אז יותר מקום פנוי, אז מספר שולחן נמוך — הכל דטרמיניסטי.
    out.sort(key=lambda r: (-r["score"], r["is_reserve"], -r["free_seats"], r["table_number"]))
    return out[:top_n]


def generate_seating(
    guests: list[dict],
    seats_per_table: int,
    num_tables: Optional[int] = None,
    forbidden_pairs: Optional[list[tuple[int, int]]] = None,
    together_pairs: Optional[list[tuple[int, int]]] = None,
    tables_meta: Optional[list[dict]] = None,
    zones: Optional[dict] = None,
    preferences: Optional[dict] = None,
    seed: int = 42,
    event_type: str | None = "wedding",
) -> SeatingResult:
    """מייצר שיבוץ הושבה דטרמיניסטי.

    guests: [{id, full_name, side, group_type, party_size}]
    seats_per_table: כיסאות לשולחן (ברירת מחדל, כשאין קיבולת פר-שולחן)
    num_tables: מספר שולחנות (אם None — מחושב אוטומטית עם עודף קטן)
    forbidden_pairs: זוגות מזהי-מוזמנים שאסור באותו שולחן (חוק קשיח)
    together_pairs: זוגות שכדאי להושיב יחד (בונוס רך)
    tables_meta: מיקומי השולחנות האמיתיים באולם — [{table_number, x, y, capacity}].
        אם מסופק (ולא ריק) → מצב "מודע-מיקום": משתמשים בשולחנות שהונחו בפועל
        (מספר, מיקום וקיבולת), במקום להמציא שולחנות אבסטרקטיים.
    zones: מרכזי אזורים — {"dance_floor"|"bar"|"entrance"|"loud": [(x,y), ...]}
    preferences: {party_id: [{zone, dir, priority, reason}, ...]}
    """
    rng = random.Random(seed)  # דטרמיניסטי — אותה קלט נותן אותו פלט

    parties = [
        Party(
            id=g["id"],
            name=g.get("full_name", ""),
            side=g.get("side", "shared"),
            group=g.get("group_type", "other"),
            size=max(1, int(g.get("party_size", 1))),
        )
        for g in guests
    ]

    forbidden: set = set()
    for a, b in (forbidden_pairs or []):
        forbidden.add((min(a, b), max(a, b)))

    together: set = set()
    for a, b in (together_pairs or []):
        pair = (min(a, b), max(a, b))
        if pair not in forbidden:  # חוק קשיח גובר על העדפה רכה
            together.add(pair)

    total_people = sum(p.size for p in parties)

    if not parties:
        return SeatingResult([], 0, 0, seats_per_table, 0, True, [])

    position_aware = bool(tables_meta)
    if position_aware:
        # שולחנות אמיתיים שהונחו במפה — מספר, קיבולת ומיקום פר-שולחן.
        tids = [int(t["table_number"]) for t in tables_meta]
        caps = {int(t["table_number"]): int(t.get("capacity") or seats_per_table) for t in tables_meta}
        positions = {int(t["table_number"]): (float(t["x"]), float(t["y"])) for t in tables_meta}
        norms = _zone_norms(positions, zones or {})
        pref_score = _pref_score_map(parties, tids, norms, preferences)
    else:
        # מצב אבסטרקטי (אין עדיין פריסת אולם): ממציאים מספר שולחנות שמכיל את כולם.
        min_tables = _capacity_needed(parties, seats_per_table)
        n_tables = num_tables if num_tables and num_tables > 0 else min_tables
        if n_tables * seats_per_table < total_people:
            n_tables = min_tables
        tids = list(range(n_tables))
        caps = {t: seats_per_table for t in tids}
        norms = {}
        pref_score = {}

    weights = get_seating_weights(event_type)
    assignment = _greedy(parties, tids, caps, forbidden, pref_score)
    _local_search(assignment, caps, forbidden, together, pref_score, rng, weights)
    score = _score(assignment, together, pref_score, weights)

    seated_ids = {p.id for members in assignment.values() for p in members}
    unseated = [p.id for p in parties if p.id not in seated_ids]
    hard_ok = not _violates_hard(assignment, caps, forbidden) and not unseated

    tables_out: list[dict] = []
    if position_aware:
        # שומרים על מספרי השולחן האמיתיים; מדלגים על שולחנות שנשארו ריקים.
        for tid in sorted(tids):
            members = assignment[tid]
            if not members:
                continue
            tables_out.append(
                {
                    "table_number": tid,
                    "seats_used": _seats_used(members),
                    "capacity": caps[tid],
                    "parties": [
                        {
                            "id": p.id, "full_name": p.name, "party_size": p.size,
                            "side": p.side, "group_type": p.group,
                            "reasons": _reasons_for(p, members, tid, norms, preferences, event_type),
                        }
                        for p in members
                    ],
                }
            )
    else:
        # פלט מסודר: מספרי שולחן מ-1, ומדלגים על שולחנות ריקים.
        table_number = 1
        for tid in sorted(tids):
            members = assignment[tid]
            if not members:
                continue
            tables_out.append(
                {
                    "table_number": table_number,
                    "seats_used": _seats_used(members),
                    "capacity": caps[tid],
                    "parties": [
                        {"id": p.id, "full_name": p.name, "party_size": p.size,
                         "side": p.side, "group_type": p.group, "reasons": []}
                        for p in members
                    ],
                }
            )
            table_number += 1

    return SeatingResult(
        tables=tables_out,
        total_people=total_people,
        num_tables=len(tables_out),
        seats_per_table=seats_per_table,
        score=int(round(score)),
        hard_ok=hard_ok,
        unseated=unseated,
    )
