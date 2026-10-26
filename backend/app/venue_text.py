"""נרמול טקסט לשמות מקומות אירועים — משותף לחיפוש באפליקציה ולבניית המאגר.

למה מודול נפרד: אותם כללים בדיוק צריכים לרוץ גם כשבונים את קובץ המאגר
(זיהוי כפילויות, ``backend/data/venues/research/build_dataset.py``) וגם כשזוג
מקליד שם אולם (``app/venues.py``). אם הכללים יתפצלו — אולם שזוהה ככפול בבנייה
יופיע פעמיים בחיפוש, או שהקלדה "נכונה" לא תמצא אותו.

אין כאן תלות ב-DB או ב-FastAPI — פונקציות טהורות בלבד.
"""
from __future__ import annotations

import re
import unicodedata

_NIQQUD = re.compile(r"[֑-ׇ]")
_QUOTES = re.compile(r"[\"'`´׳״“”„‘’]")
_SEPARATORS = re.compile(r"[\-–—_./\\,;:!?()\[\]{}|+&*#@~]+")
_SPACES = re.compile(r"\s+")
_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_HEB = re.compile(r"[א-ת]")
_LATIN = re.compile(r"[A-Za-z]")

# מילים כלליות שלא מבדילות בין מקומות ("אולמי X" ו-"X" הם אותו מקום).
# מנורמלות (בלי אותיות סופיות), כי משווים אחרי normalize().
GENERIC_WORDS = frozenset({
    "אולמ", "אולמי", "אולמות", "אולמ", "גנ", "גני", "אירועימ", "ארועימ", "לאירועימ", "מתחמ",
    "מרכז", "בית", "אחוזת", "events", "event", "hall", "halls", "garden", "gardens", "the",
    "venue", "venues", "בעמ", "מ", "בע", "מלונ", "מלונית", "hotel", "hotels", "resort", "tlv",
})

# קיצורים/כתיבים חלופיים של יישובים → שם תקני אחד (אחרי normalize).
_CITY_ALIASES = {
    "תל אביב": "תל אביב יפו", "תא": "תל אביב יפו", "יפו": "תל אביב יפו", "tel aviv": "תל אביב יפו",
    "פת": "פתח תקוה", "פתח תקווה": "פתח תקוה", "ראשלצ": "ראשונ לציונ", "ראשונ": "ראשונ לציונ",
    "נצרת עילית": "נופ הגליל", "ירושלימ": "ירושלימ", "באר שבע": "באר שבע", "בש": "באר שבע",
    "מודיעינ מכבימ רעות": "מודיעינ", "קרית": "קריית", "פרדס חנה": "פרדס חנה כרכור",
    "כרכור": "פרדס חנה כרכור", "דלית אל כרמל": "דאלית אל כרמל", "מעלות": "מעלות תרשיחא",
    "זכרונ יעקב": "זכרונ יעקב", "זיכרונ יעקב": "זכרונ יעקב", "כפר יונה": "כפר יונה",
}


def normalize(text: str | None) -> str:
    """אותיות קטנות, בלי ניקוד וגרשיים, אותיות סופיות → רגילות, מפרידים → רווח.

    "אולמי ג'רמיה – Jeremiah" → "אולמי גרמיה jeremiah"
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    s = _NIQQUD.sub("", s)
    s = _QUOTES.sub("", s)
    s = s.translate(_FINALS)
    s = _SEPARATORS.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def tokens(text: str | None) -> list[str]:
    return normalize(text).split()


def city_key(city: str | None) -> str:
    """מפתח יישוב להשוואה: "קרית ביאליק" == "קריית ביאליק", "תל אביב" == "תל אביב-יפו"."""
    s = normalize(city)
    s = _CITY_ALIASES.get(s, s)
    s = s.replace("קרית ", "קריית ")
    s = s.replace("יי", "י").replace("וו", "ו")
    return s


def name_key(name: str | None, city: str | None = None) -> str:
    """מפתח שם לזיהוי כפילויות: בלי מילים כלליות ובלי שם היישוב שבתוך השם.

    "אולמי הנסיכה באר שבע" ו-"הנסיכה" (באר שבע) → "הנסיכה". מחזיר את השם המנורמל
    המלא כשאחרי הסינון לא נשאר כלום ("אולם אירועים" נשאר "אולמ אירועימ").
    """
    toks = tokens(name)
    city_toks = set(tokens(city)) | set(city_key(city).split()) if city else set()
    kept = [t for t in toks if t not in GENERIC_WORDS and t not in city_toks]
    if not kept:
        return " ".join(toks)
    return " ".join(kept).replace("יי", "י").replace("וו", "ו")


def meaningful_tokens(key: str) -> set[str]:
    """מילים בעלות משמעות במפתח (בלי מילים כלליות ובלי מילים של אות-שתיים)."""
    return {t for t in key.split() if t not in GENERIC_WORDS and len(t) >= 3}


def split_bilingual(name: str) -> tuple[str, list[str]]:
    """"טאי אירועים TAI" → ("טאי אירועים", ["TAI"]). שם בשפה אחת חוזר כמו שהוא.

    משמש רק כשחלק אחד בעברית וחלק אחר באותיות לטיניות — כדי שהשם המוצג יהיה
    עברי והאנגלי יישמר ככינוי לחיפוש.
    """
    name = _SPACES.sub(" ", (name or "").strip())
    if not (_HEB.search(name) and _LATIN.search(name)):
        return name, []
    parts = name.split(" ")
    he = [p for p in parts if not _LATIN.search(p)]
    la = [p for p in parts if _LATIN.search(p)]
    he_name = " ".join(he).strip(" -–")
    la_name = " ".join(la).strip(" -–")
    if not he_name or not _HEB.search(he_name):
        return name, []
    return he_name, ([la_name] if la_name else [])


def edit_distance(a: str, b: str, limit: int = 3) -> int:
    """מרחק לוונשטיין עם קטיעה מוקדמת — מעל ``limit`` מחזיר limit+1."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def typo_budget(token: str) -> int:
    """כמה שגיאות כתיב נסלחות למילה באורך הזה (מילים קצרות — אפס)."""
    n = len(token)
    if n <= 3:
        return 0
    if n <= 6:
        return 1
    return 2


_HEB_PREFIXES = ("וה", "שה", "וב", "ול", "ומ", "מה", "בה", "לה", "ה", "ב", "ל", "מ", "ו", "ש", "כ")


def strip_prefix(token: str) -> list[str]:
    """אותיות שימוש בתחילת מילה: "באשדוד" → ["באשדוד", "אשדוד"]. רק למילים עבריות ארוכות."""
    out = [token]
    if len(token) >= 4 and _HEB.match(token):
        for p in _HEB_PREFIXES:
            if token.startswith(p) and len(token) - len(p) >= 3:
                out.append(token[len(p):])
    return out
