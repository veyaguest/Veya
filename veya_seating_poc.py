"""
VEYA - POC למנוע שיבוץ הושבה
=============================
בדיקת היתכנות: האם אלגוריתם היוריסטי (ללא ספריית Solver חיצונית)
מסוגל לשבץ 150-200 אורחים לשולחנות תוך שמירה על 100% מהחוקים הקשיחים,
תוך כמה שניות, עם ניקוד סביר על החוקים הרכים?

הערה: OR-Tools לא זמין בסביבה הזו (אין גישת רשת) - זו דווקא הזדמנות טובה
לבדוק אם היוריסטיקה פשוטה (Greedy + Local Search) מספיקה בלי תלות בספרייה חיצונית.
"""

import random
import time
from collections import defaultdict

random.seed(42)

# ---------------------------------------------------------------
# 1. יצירת דאטה סינתטי - מדמה רשימת מוזמנים אמיתית
# ---------------------------------------------------------------

FIRST_NAMES = ["דני", "יוני", "אבי", "ענבר", "שרה", "משה", "רותי", "אורי", "מיכל",
               "יעל", "גיל", "נועה", "עידו", "טל", "רון", "הדר", "אלון", "שירה",
               "עומר", "ליאור", "נדב", "קרן", "אסף", "דנה", "יובל", "ניצן"]
LAST_NAMES = ["כהן", "לוי", "מזרחי", "אבוטבול", "ביטון", "פרץ", "אזולאי", "דהן", "גבאי"]
GROUPS = ["close_family", "extended_family", "friends", "work", "other"]
SIDES = ["groom", "bride", "shared"]

def generate_guests(n_guests=180):
    guests = []
    # יוצרים "יחידות חברתיות" (קבוצות שכדאי לשבץ יחד) - חברים מגיעים בקבוצות של 2-6
    guest_id = 0
    social_units = []
    while guest_id < n_guests:
        unit_size = random.choice([1, 1, 2, 2, 3, 4, 5, 6])  # רוב היחידות קטנות-בינוניות
        unit_size = min(unit_size, n_guests - guest_id)
        group = random.choice(GROUPS)
        side = random.choice(SIDES)
        unit = []
        for _ in range(unit_size):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            g = {
                "id": guest_id,
                "name": name,
                "side": side,
                "group": group,
                "social_unit": len(social_units),
            }
            guests.append(g)
            unit.append(guest_id)
            guest_id += 1
        social_units.append(unit)
    return guests, social_units

def generate_hard_constraints(guests, n_exclude_pairs=8):
    """אילוצי 'לא לשבת יחד' - מדמה הערות כמו 'דני ויוני בריב'"""
    excludes = set()
    ids = [g["id"] for g in guests]
    while len(excludes) < n_exclude_pairs:
        a, b = random.sample(ids, 2)
        excludes.add(tuple(sorted((a, b))))
    return excludes

def generate_tables(n_guests, seats_per_table=10):
    n_tables = -(-n_guests // seats_per_table) + 2  # קצת עודף קיבולת, כמו במציאות
    return [{"id": i, "capacity": seats_per_table} for i in range(n_tables)]


# ---------------------------------------------------------------
# 2. פונקציית ניקוד (חוקים רכים) + בדיקת חוקים קשיחים
# ---------------------------------------------------------------

def violates_hard_constraints(assignment, excludes, guests_by_id):
    """בודק: קיבולת שולחן + זוגות אסורים"""
    table_of = {g_id: t_id for t_id, members in assignment.items() for g_id in members}
    for t_id, members in assignment.items():
        if len(members) > TABLE_CAPACITY[t_id]:
            return True
    for a, b in excludes:
        if table_of.get(a) == table_of.get(b):
            return True
    return False

def score_assignment(assignment, guests_by_id, social_units, excludes):
    """ניקוד חוקים רכים, בהתאם לחלק 7.4 ב-PRD"""
    score = 0
    table_of = {g_id: t_id for t_id, members in assignment.items() for g_id in members}

    # +10 חברים/יחידה חברתית יחד
    for unit in social_units:
        if len(unit) < 2:
            continue
        tables_used = set(table_of[g_id] for g_id in unit)
        if len(tables_used) == 1:
            score += 10 * len(unit)
        else:
            # פיזור יחידה חברתית על פני יותר מדי שולחנות = קנס קל
            score -= 5 * (len(tables_used) - 1)

    # -20 הפרת "לא לשבת יחד" (לא אמור לקרות, זה hard, אבל שומרים כבדיקת שפיות)
    for a, b in excludes:
        if table_of.get(a) == table_of.get(b):
            score -= 20

    return score


# ---------------------------------------------------------------
# 3. שלב א' - שיבוץ ראשוני חמדני (Greedy) לפי יחידות חברתיות
# ---------------------------------------------------------------

def greedy_initial_assignment(guests, social_units, tables, excludes):
    assignment = defaultdict(list)  # table_id -> [guest_ids]
    remaining_capacity = {t["id"]: t["capacity"] for t in tables}
    guests_by_id = {g["id"]: g for g in guests}

    # יחידות גדולות קודם - קשה יותר לשבץ אותן מאוחר יותר
    units_sorted = sorted(social_units, key=len, reverse=True)

    for unit in units_sorted:
        placed = False
        # מנסים למצוא שולחן עם מקום פנוי שלא יוצר הפרת exclude
        candidate_tables = sorted(
            remaining_capacity.keys(),
            key=lambda t_id: -remaining_capacity[t_id]
        )
        for t_id in candidate_tables:
            if remaining_capacity[t_id] >= len(unit):
                # בדיקת exclude מול מי שכבר יושב שם
                conflict = False
                for g_id in unit:
                    for seated in assignment[t_id]:
                        pair = tuple(sorted((g_id, seated)))
                        if pair in excludes:
                            conflict = True
                            break
                    if conflict:
                        break
                if not conflict:
                    assignment[t_id].extend(unit)
                    remaining_capacity[t_id] -= len(unit)
                    placed = True
                    break
        if not placed:
            # פיצול היחידה כמוצא אחרון (עדיף מלהשאיר מוזמן בלי שולחן)
            for g_id in unit:
                for t_id in sorted(remaining_capacity.keys(), key=lambda t: -remaining_capacity[t]):
                    if remaining_capacity[t_id] >= 1:
                        conflict = any(
                            tuple(sorted((g_id, seated))) in excludes
                            for seated in assignment[t_id]
                        )
                        if not conflict:
                            assignment[t_id].append(g_id)
                            remaining_capacity[t_id] -= 1
                            break
    return dict(assignment)


# ---------------------------------------------------------------
# 4. שלב ב' - שיפור מקומי (Local Search / חילופים)
# ---------------------------------------------------------------

def local_search_improve(assignment, guests, social_units, excludes, iterations=3000):
    guests_by_id = {g["id"]: g for g in guests}
    best_score = score_assignment(assignment, guests_by_id, social_units, excludes)

    table_ids = list(assignment.keys())

    for _ in range(iterations):
        t1, t2 = random.sample(table_ids, 2)
        if not assignment[t1] or not assignment[t2]:
            continue
        g1 = random.choice(assignment[t1])
        g2 = random.choice(assignment[t2])

        # מבצעים חילוף ניסיוני
        assignment[t1].remove(g1)
        assignment[t2].remove(g2)
        assignment[t1].append(g2)
        assignment[t2].append(g1)

        if violates_hard_constraints(assignment, excludes, guests_by_id):
            # ביטול החילוף - שובר חוק קשיח
            assignment[t1].remove(g2)
            assignment[t2].remove(g1)
            assignment[t1].append(g1)
            assignment[t2].append(g2)
            continue

        new_score = score_assignment(assignment, guests_by_id, social_units, excludes)
        if new_score >= best_score:
            best_score = new_score  # שומרים את השיפור
        else:
            # מבטלים - לא השתפר
            assignment[t1].remove(g2)
            assignment[t2].remove(g1)
            assignment[t1].append(g1)
            assignment[t2].append(g2)

    return assignment, best_score


# ---------------------------------------------------------------
# הרצה
# ---------------------------------------------------------------

if __name__ == "__main__":
    N_GUESTS = 180
    guests, social_units = generate_guests(N_GUESTS)
    excludes = generate_hard_constraints(guests, n_exclude_pairs=8)
    tables = generate_tables(N_GUESTS, seats_per_table=10)
    TABLE_CAPACITY = {t["id"]: t["capacity"] for t in tables}
    guests_by_id = {g["id"]: g for g in guests}

    print(f"=== VEYA Seating POC ===")
    print(f"מוזמנים: {N_GUESTS} | יחידות חברתיות: {len(social_units)} | שולחנות: {len(tables)} | קיבולת לשולחן: 10")
    print(f"אילוצי 'לא ביחד': {len(excludes)}")
    print()

    t0 = time.time()
    assignment = greedy_initial_assignment(guests, social_units, tables, excludes)
    t1 = time.time()

    initial_score = score_assignment(assignment, guests_by_id, social_units, excludes)
    initial_violated = violates_hard_constraints(assignment, excludes, guests_by_id)

    print(f"--- שלב 1: שיבוץ חמדני ראשוני ---")
    print(f"זמן: {t1-t0:.3f} שניות | ניקוד: {initial_score} | הפרת חוק קשיח: {initial_violated}")

    t2 = time.time()
    assignment, final_score = local_search_improve(assignment, guests, social_units, excludes, iterations=3000)
    t3 = time.time()

    final_violated = violates_hard_constraints(assignment, excludes, guests_by_id)

    print(f"\n--- שלב 2: שיפור Local Search (3000 איטרציות) ---")
    print(f"זמן: {t3-t2:.3f} שניות | ניקוד: {final_score} | הפרת חוק קשיח: {final_violated}")
    print(f"\n=== סה\"כ זמן ריצה: {t3-t0:.3f} שניות ===")

    # בדיקת שפיות: כל אורח משובץ פעם אחת, אף שולחן לא חורג מקיבולת
    all_seated = [g_id for members in assignment.values() for g_id in members]
    print(f"\n--- בדיקות שפיות ---")
    print(f"כל האורחים משובצים: {len(all_seated) == N_GUESTS} ({len(all_seated)}/{N_GUESTS})")
    print(f"אין כפילויות: {len(all_seated) == len(set(all_seated))}")
    over_capacity = [t_id for t_id, m in assignment.items() if len(m) > TABLE_CAPACITY[t_id]]
    print(f"שולחנות שחרגו מקיבולת: {len(over_capacity)}")

    # דוגמת פלט - הצגת 3 שולחנות ראשונים
    print(f"\n--- דוגמת פלט (3 שולחנות ראשונים) ---")
    for t_id in list(assignment.keys())[:3]:
        names = [guests_by_id[g_id]["name"] for g_id in assignment[t_id]]
        print(f"שולחן {t_id} ({len(names)}/{TABLE_CAPACITY[t_id]}): {', '.join(names)}")
