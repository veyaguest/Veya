"""מאגר האולמות — לוגיקת עזר (בלי FastAPI): רישום אוטומטי וחיפוש.

המאגר נבנה משני כיוונים: (1) בכל פעם שזוג שומר שם+כתובת אולם באירוע, קוראים
ל-``record_venue`` והוא מוסיף/מעדכן רשומה במאגר המשותף; (2) המאגר הארצי מיובא
בייבוא מבוקר (``app/venue_catalog.py``). כשזוג מקליד שם אולם, ``search_venues``
מציע התאמות עם העיר והכתובת — כדי לחסוך הקלדה ולהפעיל ניווט אוטומטי.
אין קריאות רשת/LLM, אין תלות ב-API בתשלום.
"""
from bisect import bisect_left
from types import SimpleNamespace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import cache, models
from app.venue_text import (
    GENERIC_WORDS, city_key, edit_distance, name_key, normalize, strip_prefix, tokens, typo_budget,
)

# --- caching (שלב 1) ---
# venues הוא מידע ציבורי שמשתנה לעיתים רחוקות (שם/כתובת אולם) — TTL ארוך
# יחסית, אבל עם invalidation מפורש בכל כתיבה כדי שהשינוי ייראה מיד ולא רק
# אחרי שה-TTL פג. כל מפתחות המטמון של venues מתחילים ב-"venues:" כדי
# שאפשר יהיה לנקות את כולם יחד עם invalidate_prefix.
VENUE_CACHE_TTL_SECONDS = 300  # 5 דקות

# סוג המקום כפי שמוצג לזוג ליד ההצעה (קוד → תווית). "אחר"/לא ידוע — בלי תווית.
KIND_LABELS = {
    "hall": "אולם אירועים", "garden": "גן אירועים", "complex": "אולם וגן", "boutique": "אולם בוטיק",
    "restaurant": "מסעדה", "hotel": "מלון", "loft": "לופט", "villa": "וילה", "conference": "מרכז כנסים",
    "synagogue": "אולם בית כנסת", "community": "אולם קהילתי",
}


def _dedup_key(name: str) -> str:
    """שם מנורמל לדדופ: אותיות קטנות + כיווץ רווחים. ריק => אין מפתח."""
    return " ".join((name or "").strip().lower().split())


def record_venue(db: Session, name: str, address: str) -> None:
    """מוסיף/מעדכן אולם במאגר לפי שם. לא מבצע commit — הקורא אחראי לכך.

    - שם ריק => מתעלמים (אין מה לשמור).
    - קיים אולם עם אותו שם מנורמל => מעלים usage_count, ומעדכנים כתובת אם
      התקבלה כתובת חדשה לא-ריקה (הכי עדכני מנצח).
    - אחרת => יוצרים רשומה חדשה.
    """
    name = (name or "").strip()
    address = (address or "").strip()
    key = _dedup_key(name)
    if not key:
        return
    existing = _pick_existing(db, key, address)
    if existing:
        # None (שורות ישנות) = נספר כשימוש אחד; 0 (אדמין/מאגר ארצי) = עוד לא נבחר.
        existing.usage_count = (1 if existing.usage_count is None else existing.usage_count) + 1
        # אולם שאומת במאגר המנוהל, או שהגיע מהמאגר הארצי — הכתובת שלו נקבעה ע"י
        # VEYA, וזוג שהקליד כתובת אחרת לא דורס אותה.
        if address and not existing.verified and (existing.source or "") != "import":
            existing.address = address
    else:
        db.add(models.Venue(name=name, address=address, dedup_key=key, source="auto"))
    # המאגר השתנה (שימוש חדש/רשומה חדשה) — מנקים את מטמון החיפוש/הרשימה כדי
    # שהזוג/האדמין הבא יראו את המידע העדכני, לא נתונים ישנים מהמטמון.
    cache.invalidate_prefix("venues:")


def _pick_existing(db: Session, key: str, address: str):
    """השורה במאגר שמייצגת את האולם שהזוג שמר.

    במאגר הארצי יכולים להיות כמה מקומות באותו שם ביישובים שונים — הם נשמרים
    עם מפתח ``"<שם> · <יישוב>"`` (ראו ``venue_catalog._free_dedup_key``).
    בוחרים את זה שהכתובת שהזוג הקליד מתאימה לו; אחרת את השורה בשם המדויק.
    """
    rows = db.scalars(
        select(models.Venue).where(
            or_(models.Venue.dedup_key == key, models.Venue.dedup_key.like(f"{key} · %"))
        )
    ).all()
    if not rows:
        return None
    addr = normalize(address)
    if addr:
        for v in rows:
            if v.city and normalize(v.city) in addr:
                return v
            if v.address and normalize(v.address) and normalize(v.address) in addr:
                return v
    return next((v for v in rows if v.dedup_key == key), rows[0])


# ── חיפוש ────────────────────────────────────────────────────────────────────
# המאגר הארצי הוא אלפי שורות — קטן מספיק לאינדקס בזיכרון (כמה MB), וחיפוש בו
# זהה ב-SQLite (פיתוח) וב-Postgres (ייצור) בלי הרחבות DB (pg_trgm). האינדקס
# נבנה פעם ב-TTL או אחרי כל כתיבה למאגר (invalidate_prefix("venues:")).

# משקלים: התאמה בשם חשובה מהתאמה בעיר, שחשובה מהתאמה בכתובת.
_W = {"name": (3.0, 2.2, 1.5), "city": (1.2, 0.9, 0.6), "address": (0.8, 0.6, 0.0)}


def _field_tokens(*texts) -> set:
    out = set()
    for t in texts:
        for tok in tokens(t):
            out.update(strip_prefix(tok))
    return out


def _build_index(db: Session) -> dict:
    rows = db.scalars(
        select(models.Venue).where(
            # אולם שהוסתר או שעדיין טיוטה במאגר המנוהל — לא מוצע לזוגות.
            or_(models.Venue.status == "active", models.Venue.status.is_(None)),
        )
    ).all()
    entries, vocab = [], set()
    for v in rows:
        names = [v.name, v.name_en or ""] + list(v.aliases or [])
        e = SimpleNamespace(
            id=v.id, name=v.name, address=v.address or "", city=v.city or "",
            venue_kind=v.venue_kind or "", region=v.region or "",
            usage=v.usage_count or 0, priority=v.priority or 0, verified=bool(v.verified),
            source=v.source or "auto",
            nnames=[normalize(n) for n in names if n],
            toks={"name": _field_tokens(*names), "city": _field_tokens(v.city),
                  "address": _field_tokens(v.address)},
            dkey=(name_key(v.name, v.city), city_key(v.city)),
        )
        for f in e.toks.values():
            vocab |= f
        entries.append(e)
    by_len: dict = {}
    by_first: dict = {}
    for tok in vocab:
        by_len.setdefault(len(tok), []).append(tok)
        by_first.setdefault(tok[0], []).append(tok)
    return {"entries": entries, "vocab": vocab, "sorted": sorted(vocab), "by_len": by_len, "by_first": by_first}


def _prefixed(index: dict, prefix: str) -> list:
    """כל המילים באוצר שמתחילות ב-prefix — חיפוש בינארי ברשימה ממוינת."""
    words = index["sorted"]
    i = bisect_left(words, prefix)
    out = []
    while i < len(words) and words[i].startswith(prefix):
        out.append(words[i])
        i += 1
    return out


def _token_matches(index: dict, qtok: str) -> dict:
    """לכל מילה באוצר המילים של המאגר: 0=מדויק, 1=תחילית, 2=שגיאת כתיב."""
    out: dict = {}
    variants = strip_prefix(qtok)
    for q in variants:
        if q in index["vocab"]:
            out[q] = 0
    if len(qtok) >= 2:
        for q in variants:
            for tok in _prefixed(index, q):
                out.setdefault(tok, 1)
    budget = typo_budget(qtok)
    if budget:
        for n in range(len(qtok) - budget, len(qtok) + budget + 1):
            for tok in index["by_len"].get(n, ()):
                # אות ראשונה או שנייה זהה — שגיאה בשתיהן יחד נדירה, וזה חוסך את רוב החישובים
                if tok not in out and (tok[0] == qtok[0] or tok[1:2] == qtok[1:2]) \
                        and edit_distance(qtok, tok, budget) <= budget:
                    out[tok] = 2
        # הקלדה חלקית עם שגיאה: "נסיקה" מול "הנסיכה" — משווים לתחילית באורך המילה
        if len(qtok) >= 4:
            for tok in index["by_first"].get(qtok[0], ()):
                if tok not in out and len(tok) > len(qtok) and edit_distance(qtok, tok[:len(qtok)], 1) <= 1:
                    out[tok] = 2
    return out


def _score(e, qtoks: list, matches: list, qnorm: str) -> float:
    total, name_hit = 0.0, False
    for qt, m in zip(qtoks, matches):
        best = 0.0
        for field, toks in e.toks.items():
            for tok in toks:
                kind = m.get(tok)
                if kind is not None:
                    w = _W[field][kind]
                    if w > best:
                        best = w
                        if field == "name":
                            name_hit = True
        if best == 0.0:
            if qt in GENERIC_WORDS:
                continue  # "אולם"/"גן" לא חובה להתאים
            return 0.0
        total += best
    if not name_hit:
        total *= 0.5  # התאמה רק בעיר/כתובת — מוצגת, אבל אחרי התאמות בשם
    for n in e.nnames:
        if n == qnorm:
            total += 5
            break
        if n.startswith(qnorm):
            total += 3
            break
    total += 0.3 * e.verified + 0.02 * min(e.usage, 50) + 0.05 * e.priority
    return total


def search_venues(db: Session, query: str, limit: int = 8) -> list:
    """מחזיר אולמות מתאימים לחיפוש: לפי שם, שם חלופי (כולל אנגלית), עיר וכתובת.

    סלחני לשגיאות כתיב ולאותיות שימוש ("באשדוד"), בלי כפילויות בתוצאות (אותו
    מקום שהגיע גם מאירוע וגם מהמאגר). מחרוזת ריקה => ריק. ממוטמן לפי (query, limit).
    """
    q = (query or "").strip()
    if not q:
        return []

    def _load() -> list:
        index = cache.get_or_set("venues:index", VENUE_CACHE_TTL_SECONDS, lambda: _build_index(db))
        qnorm = normalize(q)
        qtoks = qnorm.split()
        if not qtoks:
            return []
        matches = [_token_matches(index, t) for t in qtoks]
        scored = []
        for e in index["entries"]:
            sc = _score(e, qtoks, matches, qnorm)
            if sc > 0:
                scored.append((sc, e))
        scored.sort(key=lambda p: (-p[0], -p[1].usage, p[1].name))
        out, seen = [], set()
        for _, e in scored:
            if e.dkey in seen:
                continue
            # שורה ישנה בלי עיר וכתובת, כשיש כבר תוצאה באותו שם עם פרטים — מיותרת
            if not e.city and not e.address and any(k[0] == e.dkey[0] for k in seen):
                continue
            seen.add(e.dkey)
            out.append(e)
            if len(out) >= limit:
                break
        return out

    key = f"venues:search:{q.lower()}:{limit}"
    return cache.get_or_set(key, VENUE_CACHE_TTL_SECONDS, _load)
