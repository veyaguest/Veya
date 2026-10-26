"""חילוץ מקומות אירועים מ-OpenStreetMap (קובצי Overpass גולמיים) → osm_candidates.jsonl.

שימוש:  python3 -I osm_extract.py <תיקיית-raw>
הקבצים הגולמיים (תשובות Overpass JSON) לא נשמרים במאגר — הם ניתנים לשחזור
מהשאילתות שב-README.md. נשמר רק הפלט המסונן + טבלת יישובים (localities.json)
שמשמשת לשיוך יישוב/אזור.

רישיון: נתוני OSM © OpenStreetMap contributors, ODbL 1.0 — חובת ייחוס בממשק.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

VENUE_AMENITIES = {"events_venue", "wedding_hall", "conference_centre"}
# שם שמעיד על מקום אירועים. "אולם" לבד לא מספיק (אולם ספורט/תצוגה/הרצאות).
EV_NAME = re.compile(
    r"אירועים|שמחות|אולמי |^אולמי|גן אירועים|גני אירועים|לאירועים|[Ee]vents?\b|[Ww]edding|[Bb]anquet"
    r"|أفراح|افراح|أعراس|اعراس|مناسبات|قاعة|قاعات"
)
NOT_VENUE = re.compile(
    r"ספורט|כדורסל|התעמלות|תצוגה|טרקלין חשמל|חשמל|רחוב|שדרות|שכונת|חניי|הספדים|הנוסעים|מקבלי הפנים"
    r"|רياض|رياضة|رياضية|شارع|[Ss]ports?|[Ss]treet|[Pp]arking|[Gg]reeters"
)
EXCLUDE_TAGS = {
    "shop", "highway", "place", "landuse", "natural", "railway", "public_transport",
}
EXCLUDE_LEISURE = {"sports_centre", "pitch", "playground", "fitness_station", "fitness_centre",
                   "sports_hall", "swimming_pool", "stadium", "park", "garden"}

SOURCE_FILES = ["osm_tags.json", "osm_he.json", "osm_ar.json", "osm_en.json", "osm_hotels.json",
                "osm_bbox_js.json"]


def _he(s: str) -> bool:
    return any("֐" <= c <= "׿" for c in s or "")


def _load(raw: Path, name: str) -> list[dict]:
    p = raw / name
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("elements", [])


def _coords(e: dict) -> tuple[float | None, float | None]:
    if "lat" in e:
        return e["lat"], e["lon"]
    c = e.get("center") or {}
    return c.get("lat"), c.get("lon")


def classify(tags: dict) -> str | None:
    """מחזיר venue_kind אם האלמנט הוא מקום אירועים/מלון, אחרת None."""
    name = tags.get("name", "")
    amenity = tags.get("amenity", "")
    if not name:
        return None
    if any(t in tags for t in EXCLUDE_TAGS) and amenity not in VENUE_AMENITIES:
        return None
    if tags.get("leisure") in EXCLUDE_LEISURE and amenity not in VENUE_AMENITIES:
        return None
    if tags.get("tourism") == "hotel":
        return "hotel"
    if tags.get("tourism") or tags.get("historic"):
        return None
    names = " ".join(v for k, v in tags.items() if k == "name" or k.startswith("name:"))
    if NOT_VENUE.search(names) and amenity not in VENUE_AMENITIES:
        return None
    is_venue = (amenity in VENUE_AMENITIES or tags.get("building") == "events_venue"
                or bool(EV_NAME.search(names)))
    if not is_venue:
        return None
    if amenity == "conference_centre":
        return "conference"
    if amenity == "restaurant":
        return "restaurant"
    if re.search(r"גן אירועים|גני אירועים|[Gg]arden|حديقة", names):
        return "garden"
    return "hall"


def localities(raw: Path) -> list[dict]:
    """יישובים (עיר/עיירה/כפר) עם שם עברי וקואורדינטות — לשיוך יישוב לנקודה."""
    il = {(e["type"], e["id"]) for e in _load(raw, "osm_places.json")}
    out, seen = [], set()
    for f in ("osm_places.json", "osm_bbox_js.json", "osm_bbox_places_all.json"):
        for e in _load(raw, f):
            t = e.get("tags", {})
            if t.get("place") not in ("city", "town", "village", "hamlet", "suburb", "neighbourhood"):
                continue
            he = t.get("name:he") or (t.get("name") if _he(t.get("name", "")) else None)
            if not he or (e["type"], e["id"]) in seen:
                continue
            # מחוץ לגבול ישראל ב-OSM: רק יישוב ששמו הראשי בעברית (יישוב ישראלי).
            if (e["type"], e["id"]) not in il and not _he(t.get("name", "")):
                continue
            seen.add((e["type"], e["id"]))
            lat, lon = _coords(e)
            try:
                pop = int(str(t.get("population", "")).replace(",", "").split(".")[0] or 0)
            except ValueError:
                pop = 0
            out.append({"name": he.replace("–", "-"), "name_en": t.get("name:en") or "",
                        "name_ar": t.get("name:ar") or "", "name_osm": t.get("name") or "",
                        "place": t["place"], "lat": lat, "lon": lon, "population": pop or None,
                        "in_il_boundary": (e["type"], e["id"]) in il})
    return out


KIND_RADIUS_KM = {"city": 8.0, "town": 3.5, "village": 1.5, "hamlet": 1.0}


def radius_km(L: dict) -> float:
    """רדיוס משוער של יישוב: לפי אוכלוסייה כשידועה, אחרת לפי סוג היישוב.
    עיר גדולה "מנצחת" כפר סמוך כשהנקודה בתוך שטחה (גבעת שאול → ירושלים, לא מוצא)."""
    if L.get("population"):
        return 1.2 + 0.35 * math.sqrt(L["population"] / 1000.0)
    return KIND_RADIUS_KM.get(L["place"], 1.0)


def nearest(locs: list[dict], lat: float, lon: float, kinds: tuple) -> tuple[dict | None, float]:
    """היישוב שהנקודה "הכי בתוכו": מינימום של מרחק/רדיוס. מחזיר (יישוב, מרחק בק"מ)."""
    best, bscore, bd = None, 1e9, 1e9
    k = math.cos(math.radians(lat))
    for L in locs:
        if L["place"] not in kinds:
            continue
        d = math.hypot((L["lat"] - lat), (L["lon"] - lon) * k) * 111.0
        score = d / radius_km(L)
        if score < bscore:
            best, bscore, bd = L, score, d
    if best is not None and bscore > 2.5:
        return None, bd
    return best, bd


def to_hebrew_city(city: str, by_alt: dict) -> str:
    """addr:city באנגלית/ערבית ("hadera", "عيلبون") → שם היישוב בעברית מטבלת היישובים."""
    c = city.strip().replace("–", "-")
    if not c:
        return ""
    if _he(c):
        return c
    return by_alt.get(c.lower(), "")


def main(raw_dir: str) -> None:
    raw = Path(raw_dir)
    locs = localities(raw)
    (HERE / "localities.json").write_text(json.dumps(locs, ensure_ascii=False, indent=0), encoding="utf-8")
    by_alt = {}
    for L in locs:
        for alt in (L["name_en"], L["name_ar"], L["name_osm"], L["name"]):
            if alt:
                by_alt.setdefault(alt.strip().lower().replace("–", "-"), L["name"])
    seen: dict = {}
    for f in SOURCE_FILES:
        for e in _load(raw, f):
            seen.setdefault((e["type"], e["id"]), e)
    out = []
    for (typ, oid), e in seen.items():
        tags = e.get("tags", {})
        kind = classify(tags)
        if not kind:
            continue
        lat, lon = _coords(e)
        if lat is None:
            continue
        name = tags.get("name:he") or tags["name"]
        town, dist = nearest(locs, lat, lon, ("city", "town", "village", "hamlet"))
        city = to_hebrew_city(tags.get("addr:city") or "", by_alt) or (town["name"] if town else "")
        # מחוץ לגבול ישראל ב-OSM וללא שם עברי → כנראה ביישוב פלסטיני; לא בתחום המאגר.
        # מחוץ לגבול ישראל ב-OSM: רק עסק ששמו הראשי בעברית (יישוב ישראלי ביו"ש);
        # עסק בשם ערבי/אנגלי שם הוא כנראה ביישוב פלסטיני — לא בתחום המאגר.
        if town and not town["in_il_boundary"] and not _he(tags.get("name", "")):
            continue
        street = " ".join(x for x in (tags.get("addr:street", ""), tags.get("addr:housenumber", "")) if x)
        aliases = sorted({v for k, v in tags.items()
                          if (k == "name" or k.startswith("name:") or k in ("alt_name", "old_name", "short_name"))
                          and v and v != name})
        out.append({
            "name": name, "city": city or None, "address": street or None, "kind": kind,
            "website": tags.get("website") or tags.get("contact:website") or None,
            "phone": tags.get("phone") or tags.get("contact:phone") or None,
            "aliases": aliases, "lat": round(lat, 6), "lng": round(lon, 6),
            "osm_id": f"{typ}/{oid}", "source_url": f"https://www.openstreetmap.org/{typ}/{oid}",
            "channel": "osm", "found": "2026-10-26", "near_town_km": round(dist, 1) if town else None,
        })
    with (HERE / "osm_candidates.jsonl").open("w", encoding="utf-8") as fh:
        for r in sorted(out, key=lambda r: (r["kind"], r["city"] or "", r["name"])):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(locs), "localities;", len(out), "osm venues", Counter(r["kind"] for r in out))


if __name__ == "__main__":
    main(sys.argv[1])
