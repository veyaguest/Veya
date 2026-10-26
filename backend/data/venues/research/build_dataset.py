"""בניית קובץ המאגר מממצאי המחקר: ניקוי, שיוך אזור, זיהוי כפילויות ודוח.

שימוש:  cd backend && python3 data/venues/research/build_dataset.py

קלט:
  research/candidates.jsonl     — ממצאי חיפוש ברשת (add.py), יומן גולמי
  research/osm_candidates.jsonl — OpenStreetMap (osm_extract.py)
  research/localities.json      — יישובים וקואורדינטות (לשיוך אזור)
  research/manual_merges.json   — החלטות מיזוג/הפרדה ידניות (אופציונלי)
פלט (תיקיית backend/data/venues):
  venues_il.json          — קובץ הייבוא (רשומה לכל מקום ייחודי)
  venues_il.csv           — אותו מידע לעיון/תחזוקה ב-Excel
  duplicates_report.csv   — כל מיזוג שבוצע + חשדות לכפילות שלא מוזגו
  stats.json              — ספירות לפי מקור/אזור/סטטוס/שדות חסרים

כללי זהירות (לפי הבריף):
  - לא ממזגים רק בגלל שם דומה. מיזוג אוטומטי רק כשהשם המנורמל זהה באותו יישוב,
    או כשיש אותו אתר/טלפון/מזהה OSM. שמות דומים → דוח לבדיקה בלבד.
  - שני מקומות בשמות שונים באותה כתובת = מתחם עם כמה אולמות → נשארים נפרדים.
  - שום שדה לא "משלימים" מניחוש: מה שלא נמצא נשאר null.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent
sys.path.insert(0, str(HERE.parents[2]))  # backend/ — כדי לייבא את app.venue_text
from app.venue_text import (  # noqa: E402
    city_key, edit_distance, meaningful_tokens, name_key, normalize, split_bilingual,
)

BUILD_DATE = "2026-10-26"

# ── אזורים ───────────────────────────────────────────────────────────────────
REGION_ANCHORS = {
    "צפון": ["נהריה", "עכו", "כרמיאל", "צפת", "טבריה", "קריית שמונה", "עפולה", "נצרת", "נוף הגליל",
             "בית שאן", "קצרין", "מעלות-תרשיחא", "סכנין", "שפרעם", "מגדל העמק", "יקנעם עילית", "ראש פינה",
             "חצור הגלילית", "מטולה", "טמרה", "מג'ד אל-כרום", "אום אל-פחם", "עראבה", "רמת ישי", "קריית טבעון"],
    "חיפה והקריות": ["חיפה", "קריית אתא", "קריית ביאליק", "קריית מוצקין", "קריית ים", "נשר", "טירת כרמל",
                     "עתלית", "דלית אל-כרמל", "עוספיא", "יגור"],
    "שרון": ["נתניה", "הרצליה", "רעננה", "כפר סבא", "הוד השרון", "כפר יונה", "טייבה", "טירה", "קדימה-צורן",
             "אבן יהודה", "חדרה", "קיסריה", "פרדס חנה-כרכור", "זכרון יעקב", "אור עקיבא", "בנימינה-גבעת עדה",
             "תל מונד", "באקה אל-גרביה"],
    "מרכז": ["תל אביב-יפו", "רמת גן", "גבעתיים", "בני ברק", "חולון", "בת ים", "פתח תקווה", "ראשון לציון",
             "אור יהודה", "קריית אונו", "יהוד-מונוסון", "גבעת שמואל", "רמת השרון", "ראש העין", "אלעד", "שוהם",
             "מודיעין-מכבים-רעות", "לוד", "רמלה", "כפר קאסם", "אזור"],
    "שפלה": ["רחובות", "נס ציונה", "יבנה", "גדרה", "קריית עקרון", "מזכרת בתיה", "אשדוד", "קריית מלאכי",
             "גן יבנה", "באר יעקב"],
    "ירושלים והסביבה": ["ירושלים", "בית שמש", "מבשרת ציון", "אבו גוש", "צור הדסה", "מוצא עילית"],
    "דרום": ["באר שבע", "אשקלון", "קריית גת", "שדרות", "נתיבות", "אופקים", "דימונה", "ערד", "ירוחם",
             "מצפה רמון", "רהט", "עומר", "להבים", "מיתר", "תל שבע"],
    "אילת והערבה": ["אילת", "יטבתה"],
}

# שמות אזור (לא יישוב) ויישובים שחסרים בטבלת היישובים של OSM → אזור. ממלא רק
# את שדה האזור; שדה ה"יישוב" נשאר כמו שנמצא במקור (לא ממציאים יישוב מדויק).
AREA_REGIONS = {
    "עמק חפר": "שרון", "פארק תעשיות עמק חפר": "שרון", "השרון": "שרון", "קדימה-צורן": "שרון",
    "בנימינה-גבעת עדה": "שרון", "וינגייט": "שרון", "עמק יזרעאל": "צפון", "כנרת": "צפון", "גלבוע": "צפון",
    "גליל": "צפון", "גליל מערבי": "צפון", "רמת הגולן": "צפון", "סח'נין": "צפון", "יקנעם עילית": "צפון",
    "כפר הגלילי": "צפון", "מצפה הושעיה": "צפון", "עין שרה": "צפון", "איירפורט סיטי": "מרכז",
    "קריית שדה התעופה": "מרכז", "צומת ראם": "שפלה", "שפלה": "שפלה", "עין חמד": "ירושלים והסביבה",
    "הרי ירושלים": "ירושלים והסביבה", "עמק האלה": "ירושלים והסביבה", "צומת האלה": "ירושלים והסביבה",
    "גוש עציון": "יהודה ושומרון", "מדבר יהודה": "יהודה ושומרון", "מצפה צבאים": "יהודה ושומרון",
}

# מקורות שהם האתר של המקום עצמו / מאגר פתוח / גוף ציבורי — לא פורטל פרסום.
OPEN_DOMAINS = {"openstreetmap.org"}
NEWS_DOMAINS = {"globes.co.il", "ynet.co.il", "haaretz.co.il", "kul-alarab.com", "panet.com"}


def _domain(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _digits(phone: str | None) -> str:
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("972"):
        d = "0" + d[3:]
    return d if len(d) >= 9 else ""


def _source_type(url: str, website: str | None) -> str:
    dom = _domain(url)
    if dom in OPEN_DOMAINS:
        return "osm"
    if website and dom and dom == _domain(website):
        return "official"
    if dom.endswith("muni.il") or dom.endswith("gov.il") or dom in ("cityofdavid.org.il",):
        return "public"
    if dom in NEWS_DOMAINS:
        return "news"
    if dom == "facebook.com":
        return "social"
    return "portal"


def load_localities() -> tuple[dict, list]:
    locs = json.loads((HERE / "localities.json").read_text(encoding="utf-8"))
    by_key: dict = {}
    for L in locs:
        if L["place"] in ("suburb", "neighbourhood"):
            continue
        by_key.setdefault(city_key(L["name"]), L)
    return by_key, locs


def make_region_lookup(by_key: dict):
    anchors = []
    for region, cities in REGION_ANCHORS.items():
        for c in cities:
            L = by_key.get(city_key(c))
            if L and L.get("lat") is not None:
                anchors.append((region, L["lat"], L["lon"], city_key(c)))
    direct = {a[3]: a[0] for a in anchors}

    def region_for(city: str | None) -> str | None:
        if not city:
            return None
        if city in AREA_REGIONS:
            return AREA_REGIONS[city]
        k = city_key(city)
        if k in direct:
            return direct[k]
        L = by_key.get(k)
        if not L or L.get("lat") is None:
            return None
        if not L.get("in_il_boundary", True):
            return "יהודה ושומרון"
        cos = math.cos(math.radians(L["lat"]))
        best = min(anchors, key=lambda a: math.hypot(a[1] - L["lat"], (a[2] - L["lon"]) * cos))
        return best[0]

    return region_for


def load_raw() -> list[dict]:
    rows = []
    for fname, channel in (("candidates.jsonl", "web_search"), ("osm_candidates.jsonl", "osm")):
        p = HERE / fname
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                r = json.loads(line)
                r.setdefault("channel", channel)
                r["_row"] = f"{fname}:{i + 1}"
                rows.append(r)
    return rows


def clean(r: dict, by_key: dict) -> dict:
    """רשומה גולמית אחת → צורה אחידה (בלי מיזוג)."""
    name, extra = split_bilingual(r["name"])
    aliases = set(extra) | set(r.get("aliases") or [])
    city = (r.get("city") or "").strip().replace("–", "-") or None
    if city:
        L = by_key.get(city_key(city))
        if L:
            city = L["name"]  # שם תקני מטבלת היישובים ("קרית ביאליק" → "קריית ביאליק")
    note = (r.get("note") or "").strip()
    status = "unknown"
    # "לשעבר" בשם = שינוי שם ("פלטינום (ארמונות הגפן לשעבר)"), לא סגירה.
    if note.startswith("CLOSED") or re.search(r"נטוש|[Aa]bandoned|\([Cc]losed\)", r["name"]):
        status = "closed_reported"
    elif note.startswith("UNSURE"):
        status = "uncertain"
    flags = []
    if re.search(r"סותר|לא ודאי|לא עקבי|ייתכן|לא ידוע", note):
        flags.append("conflict_or_uncertain")
    if not city:
        flags.append("no_city")
    website = r.get("website") or None
    src = r.get("source_url") or ""
    return {
        "name": name.strip(), "aliases": aliases, "city": city,
        "address": (r.get("address") or "").strip() or None,
        "kind": r.get("kind") or None, "website": website,
        "phone": r.get("phone") or None,
        "capacity_min": r.get("capacity_min"), "capacity_max": r.get("capacity_max"),
        "lat": r.get("lat"), "lng": r.get("lng"), "osm_id": r.get("osm_id"),
        "sources": [{"url": src, "type": _source_type(src, website), "channel": r["channel"],
                     "seen": r.get("found") or BUILD_DATE}] if src else [],
        "notes": [note] if note else [], "status": status, "flags": flags, "rows": [r["_row"]],
        "nkey": name_key(name, city), "ckey": city_key(city),
    }


def _addr_key(a: str | None) -> str:
    return normalize(a).replace("רחוב ", "").replace("רח ", "")


KIND_PRIORITY = ["complex", "garden", "boutique", "hall", "restaurant", "loft", "villa", "hotel",
                 "conference", "synagogue", "community", "other"]


def merge(a: dict, b: dict) -> dict:
    """b נבלע ב-a. ערך קיים לא נדרס; סתירות נרשמות בהערות."""
    def better_name(x: dict) -> int:
        types = {s["type"] for s in x["sources"]}
        return (2 if "official" in types else 0) + (1 if any(s["channel"] == "web_search" for s in x["sources"]) else 0)

    if better_name(b) > better_name(a):
        a["aliases"].add(a["name"])
        a["name"] = b["name"]
    elif b["name"] != a["name"]:
        a["aliases"].add(b["name"])
    a["aliases"] |= b["aliases"]
    for f in ("city", "website", "phone", "lat", "lng", "osm_id"):
        if not a.get(f) and b.get(f):
            a[f] = b[f]
    # כתובת: מעדיפים כתובת עם מספר בית
    if b.get("address") and (not a.get("address") or (not re.search(r"\d", a["address"]) and re.search(r"\d", b["address"]))):
        if a.get("address"):
            a["notes"].append(f"כתובת חלופית: {a['address']}")
        a["address"] = b["address"]
    elif b.get("address") and _addr_key(b["address"]) != _addr_key(a.get("address")):
        a["notes"].append(f"כתובת חלופית: {b['address']}")
    for f in ("capacity_min", "capacity_max"):
        if a.get(f) is None and b.get(f) is not None:
            a[f] = b[f]
        elif b.get(f) is not None and a.get(f) != b.get(f):
            a["notes"].append(f"{f} סותר: {a[f]} / {b[f]}")
    if a.get("kind") != b.get("kind") and b.get("kind"):
        ka = KIND_PRIORITY.index(a["kind"]) if a.get("kind") in KIND_PRIORITY else 99
        kb = KIND_PRIORITY.index(b["kind"]) if b["kind"] in KIND_PRIORITY else 99
        if kb < ka and a.get("kind") != "hotel":
            a["kind"] = b["kind"]
    seen = {s["url"] for s in a["sources"]}
    a["sources"] += [s for s in b["sources"] if s["url"] not in seen]
    a["notes"] += [n for n in b["notes"] if n not in a["notes"]]
    a["flags"] = sorted(set(a["flags"]) | set(b["flags"]))
    if b["status"] == "closed_reported" or a["status"] == "closed_reported":
        a["status"] = "closed_reported"
    elif "uncertain" in (a["status"], b["status"]):
        a["status"] = "uncertain"
    a["rows"] += b["rows"]
    if a.get("city"):
        a["flags"] = [f for f in a["flags"] if f != "no_city"]
    a["ckey"] = city_key(a.get("city"))
    return a


def similar(a: str, b: str) -> bool:
    """חשד לאותו מקום: כל המילים המשמעותיות של אחד כלולות בשני ("דנוור" / "דנוור סטייק האוס"),
    או הבדל של שגיאת כתיב ("ווגשאל" / "וגשל"). מילים כלליות ("מלון", "אולמי") לא נספרות."""
    ta, tb = meaningful_tokens(a), meaningful_tokens(b)
    if not ta or not tb or a == b:
        return False
    if ta <= tb or tb <= ta:
        return True
    ja, jb = " ".join(sorted(ta)), " ".join(sorted(tb))
    return edit_distance(ja, jb, 2) <= (1 if min(len(ja), len(jb)) <= 6 else 2)


def _same_place(a: dict, b: dict) -> bool:
    return bool(a["ckey"]) and a["ckey"] == b["ckey"] and (a["nkey"] == b["nkey"] or similar(a["nkey"], b["nkey"]))


def build() -> None:
    by_key, _ = load_localities()
    region_for = make_region_lookup(by_key)
    manual = {}
    mp = HERE / "manual_merges.json"
    if mp.exists():
        manual = json.loads(mp.read_text(encoding="utf-8"))
    force_merge = [tuple(p) for p in manual.get("merge", [])]      # [["שם א|עיר", "שם ב|עיר"], ...]
    keep_apart = {frozenset(p) for p in manual.get("keep_apart", [])}

    raw = load_raw()
    records = [clean(r, by_key) for r in raw if (r.get("name") or "").strip()]
    report: list[dict] = []

    def label(x: dict) -> str:
        return f"{x['name']}|{x.get('city') or ''}"

    # 1) מיזוג ודאי: אותו מזהה OSM / אותו שם מנורמל באותו יישוב / אותו אתר / אותו טלפון
    merged: list[dict] = []
    idx_name: dict = {}
    idx_web: dict = {}
    idx_phone: dict = {}
    idx_osm: dict = {}
    for r in records:
        target = None
        reason = ""
        if r.get("osm_id") and r["osm_id"] in idx_osm:
            target, reason = idx_osm[r["osm_id"]], "אותו מזהה OSM"
        elif r["ckey"] and (r["nkey"], r["ckey"]) in idx_name:
            target, reason = idx_name[(r["nkey"], r["ckey"])], "שם מנורמל זהה באותו יישוב"
        # אתר/טלפון משותפים לבד לא מספיקים: רשתות (דן, ישרוטל, אצולת העמק) חולקות
        # דומיין ומוקד טלפוני בין סניפים שונים. דורשים גם אותו יישוב + שם דומה.
        elif (r.get("website") and _domain(r["website"]) in idx_web
              and _same_place(idx_web[_domain(r["website"])], r)):
            target, reason = idx_web[_domain(r["website"])], "אותו אתר רשמי + אותו יישוב ושם דומה"
        elif (_digits(r.get("phone")) and _digits(r["phone"]) in idx_phone
              and _same_place(idx_phone[_digits(r["phone"])], r)):
            target, reason = idx_phone[_digits(r["phone"])], "אותו טלפון + אותו יישוב ושם דומה"
        if target is not None and frozenset((label(target), label(r))) in keep_apart:
            target = None
        if target is not None:
            report.append({"action": "merged", "reason": reason, "kept": label(target), "merged": label(r),
                           "kept_address": target.get("address") or "", "merged_address": r.get("address") or "",
                           "rows": ";".join(r["rows"])})
            merge(target, r)
            r = target
        else:
            merged.append(r)
        if r.get("osm_id"):
            idx_osm[r["osm_id"]] = r
        if r["ckey"]:
            idx_name[(r["nkey"], r["ckey"])] = r
        if r.get("website") and _source_type(r["website"], r["website"]) == "official" and _domain(r["website"]) not in OPEN_DOMAINS:
            idx_web.setdefault(_domain(r["website"]), r)
        if _digits(r.get("phone")):
            idx_phone.setdefault(_digits(r["phone"]), r)

    # 2) רשומות בלי יישוב: אם יש בדיוק התאמת שם אחת עם יישוב → מיזוג
    by_nkey = defaultdict(list)
    for r in merged:
        by_nkey[r["nkey"]].append(r)
    final = []
    for r in merged:
        if r["ckey"] or r.get("_gone"):
            continue
        cands = [x for x in by_nkey[r["nkey"]] if x is not r and x["ckey"]]
        if len(cands) == 1:
            report.append({"action": "merged", "reason": "רשומה בלי יישוב, שם זהה יחיד", "kept": label(cands[0]),
                           "merged": label(r), "kept_address": cands[0].get("address") or "",
                           "merged_address": r.get("address") or "", "rows": ";".join(r["rows"])})
            merge(cands[0], r)
            r["_gone"] = True
    merged = [r for r in merged if not r.get("_gone")]

    # 3) מיזוגים ידניים (נבדקו ע"י אדם, מתועדים בקובץ)
    by_label = {label(r): r for r in merged}
    for la, lb in force_merge:
        a, b = by_label.get(la), by_label.get(lb)
        if a and b and a is not b:
            report.append({"action": "merged", "reason": "החלטה ידנית (manual_merges.json)", "kept": la,
                           "merged": lb, "kept_address": a.get("address") or "",
                           "merged_address": b.get("address") or "", "rows": ";".join(b["rows"])})
            merge(a, b)
            b["_gone"] = True
    final = [r for r in merged if not r.get("_gone")]

    # 4) חשדות שלא מוזגו — לדוח בלבד
    by_city = defaultdict(list)
    for r in final:
        by_city[r["ckey"]].append(r)
    for ck, rs in by_city.items():
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                if frozenset((label(a), label(b))) in keep_apart:
                    continue
                same_addr = a.get("address") and b.get("address") and _addr_key(a["address"]) == _addr_key(b["address"])
                if same_addr and a["nkey"] != b["nkey"]:
                    report.append({"action": "review", "reason": "אותה כתובת, שמות שונים (מתחם עם כמה אולמות?)",
                                   "kept": label(a), "merged": label(b), "kept_address": a["address"],
                                   "merged_address": b["address"], "rows": ""})
                elif ck and similar(a["nkey"], b["nkey"]):
                    report.append({"action": "review", "reason": "שמות דומים באותו יישוב — לא מוזג אוטומטית",
                                   "kept": label(a), "merged": label(b), "kept_address": a.get("address") or "",
                                   "merged_address": b.get("address") or "", "rows": ""})
    for nk, rs in by_nkey.items():
        cities = {r["ckey"] for r in rs if not r.get("_gone") and r["ckey"]}
        if len(cities) > 1 and len(nk) >= 4:
            live = [r for r in final if r["nkey"] == nk]
            if len(live) > 1:
                report.append({"action": "info", "reason": "אותו שם ביישובים שונים — נשמרו כמקומות נפרדים",
                               "kept": " / ".join(label(r) for r in live[:6]), "merged": "", "kept_address": "",
                               "merged_address": "", "rows": ""})

    # 5) פלט
    out = []
    for r in final:
        types = {s["type"] for s in r["sources"]}
        domains = {_domain(s["url"]) for s in r["sources"] if s["url"]}
        if "conflict_or_uncertain" in r["flags"] or "no_city" in r["flags"] or r["status"] == "uncertain":
            verification = "needs_review"
        elif "official" in types or len(domains) >= 2:
            verification = "verified_sources"
        else:
            verification = "single_source"
        key_basis = r["osm_id"] and f"osm:{r['osm_id']}" or None
        import_key = key_basis or "il:" + hashlib.sha1(f"{r['nkey']}|{r['ckey']}".encode()).hexdigest()[:14]
        aliases = sorted(a for a in r["aliases"] if a and normalize(a) != normalize(r["name"]))
        address = r.get("address")
        out.append({
            "import_key": import_key,
            "name": r["name"],
            "name_en": next((a for a in aliases if re.fullmatch(r"[A-Za-z0-9 .&'’\-]+", a)), None),
            "aliases": aliases,
            "city": r.get("city"),
            "region": region_for(r.get("city")),
            "address": address,
            "venue_kind": r.get("kind") or "other",
            "event_types": None,
            "capacity_min": r.get("capacity_min"),
            "capacity_max": r.get("capacity_max"),
            "phone": r.get("phone"),
            "website": r.get("website"),
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "osm_id": r.get("osm_id"),
            "sources": r["sources"],
            "source_types": sorted(types),
            "verification": verification,
            "operating_status": r["status"],
            "last_checked": BUILD_DATE,
            "notes": " · ".join(r["notes"]) or None,
            "flags": r["flags"],
        })
    out.sort(key=lambda x: (x["region"] or "ת", x["city"] or "", x["name"]))
    keys = Counter(x["import_key"] for x in out)
    dup_keys = [k for k, n in keys.items() if n > 1]
    for k in dup_keys:  # שני מקומות שונים שקיבלו אותו מפתח — מבדילים לפי כתובת
        for x in [x for x in out if x["import_key"] == k][1:]:
            x["import_key"] = k + "-" + hashlib.sha1((x.get("address") or x["name"]).encode()).hexdigest()[:6]

    (OUT_DIR / "venues_il.json").write_text(json.dumps(
        {"generated": BUILD_DATE, "license_note": "רשומות OSM: © OpenStreetMap contributors, ODbL 1.0",
         "count": len(out), "venues": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["import_key", "name", "name_en", "aliases", "city", "region", "address", "venue_kind",
            "capacity_min", "capacity_max", "phone", "website", "lat", "lng", "verification",
            "operating_status", "source_types", "sources", "last_checked", "notes"]
    with (OUT_DIR / "venues_il.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for x in out:
            row = dict(x)
            row["aliases"] = " | ".join(x["aliases"])
            row["source_types"] = ",".join(x["source_types"])
            row["sources"] = " ".join(s["url"] for s in x["sources"])
            w.writerow(row)
    with (OUT_DIR / "duplicates_report.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["action", "reason", "kept", "merged", "kept_address", "merged_address", "rows"])
        w.writeheader()
        w.writerows(report)

    def cnt(f):
        return dict(Counter(f(x) for x in out).most_common())

    raw_by_channel = Counter(r["channel"] for r in raw)
    raw_by_domain = Counter(_domain(r.get("source_url")) for r in raw)
    missing = {f: sum(1 for x in out if not x.get(f)) for f in
               ("address", "city", "region", "phone", "website", "capacity_max", "lat", "event_types")}
    stats = {
        "generated": BUILD_DATE,
        "raw_records": len(raw), "raw_by_channel": dict(raw_by_channel),
        "raw_by_source_domain_top": dict(raw_by_domain.most_common(40)),
        "unique_venues": len(out),
        "merged_pairs": sum(1 for r in report if r["action"] == "merged"),
        "review_pairs": sum(1 for r in report if r["action"] == "review"),
        "by_region": cnt(lambda x: x["region"] or "לא משויך"),
        "by_kind": cnt(lambda x: x["venue_kind"]),
        "by_verification": cnt(lambda x: x["verification"]),
        "by_operating_status": cnt(lambda x: x["operating_status"]),
        "missing_fields": missing,
        "by_region_and_channel": {reg: dict(Counter(
            "osm" if "osm" in x["source_types"] else "web" for x in out if (x["region"] or "לא משויך") == reg))
            for reg in cnt(lambda x: x["region"] or "לא משויך")},
    }
    (OUT_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("raw_records", "unique_venues", "merged_pairs", "review_pairs",
                                             "by_region", "by_verification", "by_operating_status", "missing_fields")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    build()
