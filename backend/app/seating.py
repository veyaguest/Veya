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
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

# ניקוד חוקים רכים: תגמול על זוג חבורות באותו שולחן.
SAME_SIDE_BONUS = 3    # אותו צד (חתן/כלה)
SAME_GROUP_BONUS = 2   # אותה קבוצה (משפחה קרובה/חברים/עבודה...)
TOGETHER_BONUS = 15    # בקשת "לשבת עם" מפורשת (PRD 7.4)

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


def _table_of(assignment: dict[int, list[Party]]) -> dict[int, int]:
    """מיפוי party_id -> table_number."""
    return {p.id: t for t, members in assignment.items() for p in members}


def _seats_used(members: list[Party]) -> int:
    return sum(p.size for p in members)


def _has_forbidden(members: list[Party], candidate: Party, forbidden: set) -> bool:
    """האם הושבת candidate ליד מישהו מ-members מפרה זוג אסור?"""
    for seated in members:
        if (min(seated.id, candidate.id), max(seated.id, candidate.id)) in forbidden:
            return True
    return False


def _violates_hard(assignment: dict, capacity: int, forbidden: set) -> bool:
    """קיבולת שולחן + זוגות אסורים באותו שולחן."""
    for members in assignment.values():
        if _seats_used(members) > capacity:
            return True
        ids = [p.id for p in members]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if (min(ids[i], ids[j]), max(ids[i], ids[j])) in forbidden:
                    return True
    return False


def _score(assignment: dict, together: set) -> int:
    """ניקוד חוקים רכים: תגמול לזוגות חבורות באותו שולחן לפי צד/קבוצה,
    ובונוס גדול לבקשת 'לשבת עם' מפורשת."""
    score = 0
    for members in assignment.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a.side == b.side and a.side != "shared":
                    score += SAME_SIDE_BONUS
                if a.group == b.group and a.group != "other":
                    score += SAME_GROUP_BONUS
                if (min(a.id, b.id), max(a.id, b.id)) in together:
                    score += TOGETHER_BONUS
    return score


def _greedy(parties: list[Party], n_tables: int, capacity: int, forbidden: set) -> dict:
    """שיבוץ חמדני ראשוני: חבורות גדולות קודם, לשולחן עם הכי הרבה מקום פנוי."""
    assignment: dict[int, list[Party]] = {t: [] for t in range(n_tables)}
    remaining = {t: capacity for t in range(n_tables)}

    # חבורות גדולות קודם — קשה יותר לשבץ אותן מאוחר יותר.
    for party in sorted(parties, key=lambda p: p.size, reverse=True):
        candidates = sorted(remaining, key=lambda t: -remaining[t])
        for t in candidates:
            if remaining[t] >= party.size and not _has_forbidden(assignment[t], party, forbidden):
                assignment[t].append(party)
                remaining[t] -= party.size
                break
    return assignment


def _local_search(
    assignment: dict, capacity: int, forbidden: set, together: set, rng: random.Random
) -> int:
    """שיפור מקומי: חילופי חבורות בין שולחנות כל עוד לא נשבר חוק קשיח והניקוד לא יורד."""
    best = _score(assignment, together)
    tables = list(assignment.keys())
    if len(tables) < 2:
        return best

    for _ in range(LOCAL_SEARCH_ITERATIONS):
        t1, t2 = rng.sample(tables, 2)
        if not assignment[t1] or not assignment[t2]:
            continue
        i1 = rng.randrange(len(assignment[t1]))
        i2 = rng.randrange(len(assignment[t2]))
        p1, p2 = assignment[t1][i1], assignment[t2][i2]

        # חילוף ניסיוני
        assignment[t1][i1], assignment[t2][i2] = p2, p1

        if _violates_hard(assignment, capacity, forbidden):
            assignment[t1][i1], assignment[t2][i2] = p1, p2  # ביטול
            continue

        new = _score(assignment, together)
        if new >= best:
            best = new
        else:
            assignment[t1][i1], assignment[t2][i2] = p1, p2  # ביטול
    return best


def generate_seating(
    guests: list[dict],
    seats_per_table: int,
    num_tables: Optional[int] = None,
    forbidden_pairs: Optional[list[tuple[int, int]]] = None,
    together_pairs: Optional[list[tuple[int, int]]] = None,
    seed: int = 42,
) -> SeatingResult:
    """מייצר שיבוץ הושבה דטרמיניסטי.

    guests: [{id, full_name, side, group_type, party_size}]
    seats_per_table: כיסאות לשולחן
    num_tables: מספר שולחנות (אם None — מחושב אוטומטית עם עודף קטן)
    forbidden_pairs: זוגות מזהי-מוזמנים שאסור באותו שולחן (חוק קשיח)
    together_pairs: זוגות שכדאי להושיב יחד (בונוס רך)
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

    # מספר שולחנות: לפי בקשת המשתמש, אך תמיד מספיק כדי להכיל את כולם.
    min_tables = _capacity_needed(parties, seats_per_table)
    n_tables = num_tables if num_tables and num_tables > 0 else min_tables
    if n_tables * seats_per_table < total_people:
        n_tables = min_tables  # התעלמות מקלט שאי אפשר להכיל בו את כולם

    assignment = _greedy(parties, n_tables, seats_per_table, forbidden)
    score = _local_search(assignment, seats_per_table, forbidden, together, rng)

    seated_ids = {p.id for members in assignment.values() for p in members}
    unseated = [p.id for p in parties if p.id not in seated_ids]
    hard_ok = not _violates_hard(assignment, seats_per_table, forbidden) and not unseated

    # פלט מסודר: מספרי שולחן מ-1, ומדלגים על שולחנות ריקים.
    tables_out: list[dict] = []
    table_number = 1
    for t in sorted(assignment.keys()):
        members = assignment[t]
        if not members:
            continue
        tables_out.append(
            {
                "table_number": table_number,
                "seats_used": _seats_used(members),
                "capacity": seats_per_table,
                "parties": [
                    {"id": p.id, "full_name": p.name, "party_size": p.size,
                     "side": p.side, "group_type": p.group}
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
        score=score,
        hard_ok=hard_ok,
        unseated=unseated,
    )
