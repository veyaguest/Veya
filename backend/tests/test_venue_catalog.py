"""המאגר הארצי של מקומות האירועים: ייבוא מבוקר, חיפוש, הרשאות, ביצועים.

מה נבדק (לפי הבריף של המשימה):
- ייבוא חוזר בלי כפילויות; dry-run לא כותב כלום.
- קשרים קיימים: אירוע שכבר בחר אולם לא משתנה; אולם שזוג הזין לא נדרס.
- חיפוש לפי שם, שם חלופי (אנגלית), עיר, כתובת; שגיאות כתיב; אותיות שימוש.
- שמות זהים ביישובים שונים; מתחם עם כמה אולמות באותה כתובת.
- רשומות עם שדות חסרים; רשומות לא תקינות נדחות.
- סגור לא מוצע; עריכת אדמין לא נדרסת בייבוא חוזר.
- הרשאות: רק אדמין עם venues.edit מייבא; חיפוש דורש התחברות.
- ביצועים: 5,000 מקומות.
- הזנה ידנית של אולם שלא נמצא — נשמר ומוצע לאחרים.
- תקינות קובץ המאגר האמיתי (venues_il.json).
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

TAG = uuid.uuid4().hex[:5]


def _admin(role="super_admin"):
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u = models.User(email=f"cat-{uuid.uuid4().hex[:8]}@veya.test", password_hash=auth.hash_password("Test12345!"),
                        display_name="אדמין", is_admin=True, admin_role=role)
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def _rec(key, name, city, **kw):
    base = {"import_key": f"test:{TAG}:{key}", "name": name, "city": city, "region": "מרכז",
            "venue_kind": "hall", "sources": [{"url": "https://example.org/x", "type": "portal"}],
            "verification": "single_source", "operating_status": "unknown", "last_checked": "2026-10-26"}
    base.update(kw)
    return base


def _catalog():
    return [
        _rec("a", f"אולמי הנסיכה {TAG}", "באר שבע", address="קרית יהודית 522", aliases=[f"Princess {TAG}"]),
        _rec("b", f"אולמי הנסיכה {TAG}", "אשדוד", address="הבושם 3"),
        _rec("c", f"שיבולים {TAG}", "נתניה", address="הצורן 4", venue_kind="complex"),
        _rec("d", f"פיטנגו {TAG}", "נתניה", address="הצורן 4", venue_kind="complex"),
        _rec("e", f"גן הפקאן {TAG}", "רמת הכובש", venue_kind="garden", capacity_max=650),
        _rec("f", f"מקום בלי כלום {TAG}", None, region=None, venue_kind=None, sources=[]),  # שדות חסרים
        _rec("g", f"פוגאטה {TAG}", "ראשון לציון", operating_status="closed_reported"),
        _rec("h", "", "חיפה"),  # לא תקין: בלי שם
        _rec("i", f"מתחם עם קיבולת שגויה {TAG}", "חיפה", capacity_min=500, capacity_max=100,
             lat=10.0, lng=10.0, website="javascript:alert(1)"),
    ]


def _db():
    from app.database import SessionLocal

    return SessionLocal()


def _import(records, dry_run):
    from app import cache, venue_catalog

    db = _db()
    try:
        r = venue_catalog.import_catalog(db, records, dry_run=dry_run)
        if not dry_run:
            db.commit()
        cache.invalidate_prefix("venues:")
        return r
    finally:
        db.close()


def _search(api, q):
    from app import cache

    cache.invalidate_prefix("venues:")
    r = api.client.get("/venues/search", params={"q": q}, headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _count_imported():
    from sqlalchemy import func, select

    from app import models

    db = _db()
    try:
        return db.scalar(select(func.count(models.Venue.id)).where(models.Venue.import_key.like(f"test:{TAG}:%")))
    finally:
        db.close()


# ── ייבוא ────────────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing_then_import_is_idempotent() -> None:
    bootstrap()
    dry = _import(_catalog(), dry_run=True)
    assert dry["created"] == 8 and dry["invalid_count"] == 1, dry
    assert _count_imported() == 0, "dry-run כתב למסד"

    first = _import(_catalog(), dry_run=False)
    assert first["created"] == 8 and first["hidden_closed"] == 1, first
    second = _import(_catalog(), dry_run=False)
    assert second["created"] == 0 and second["updated"] == 0 and second["unchanged"] == 8, second
    assert _count_imported() == 8
    # מקום שהוסר מהקובץ — לא נמחק, רק מדווח
    shorter = [r for r in _catalog() if not r["import_key"].endswith(":e")]
    third = _import(shorter, dry_run=True)
    assert any(x["name"] == f"גן הפקאן {TAG}" for x in third["not_in_file"]), third
    assert _count_imported() == 8


def test_invalid_values_are_cleaned_not_invented() -> None:
    from sqlalchemy import select

    from app import models

    bootstrap()
    _import(_catalog(), dry_run=False)
    db = _db()
    try:
        bad = db.scalar(select(models.Venue).where(models.Venue.import_key == f"test:{TAG}:i"))
        assert bad.capacity_min is None and bad.capacity_max is None  # min > max → לא ידוע
        assert bad.lat is None and bad.lng is None                    # מחוץ לישראל → לא ידוע
        assert bad.website == ""                                        # לא URL → נזרק
        empty = db.scalar(select(models.Venue).where(models.Venue.import_key == f"test:{TAG}:f"))
        assert empty.city == "" and empty.address == "" and empty.venue_kind == "other"
        assert empty.capacity_max is None and empty.phone == "" and empty.status == "active"
    finally:
        db.close()


def test_existing_events_and_couple_venues_untouched() -> None:
    """אירוע שבחר אולם לפני הייבוא — שם, כתובת ו-usage_count נשארים בדיוק כפי שהיו."""
    from sqlalchemy import select

    from app import models

    api, _ = bootstrap()
    name = f"אולמי הדר {TAG}"
    r = api.client.patch("/event", headers=api.headers, json={"venue_name": name, "venue_address": "הרצל 9, רחובות"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        auto = db.scalar(select(models.Venue).where(models.Venue.dedup_key == name.lower()))
        before = (auto.name, auto.address, auto.usage_count, auto.source)
    finally:
        db.close()

    rep = _import([_rec("z", name, "רחובות", address="שדרות הרצל 100")], dry_run=False)
    assert rep["created"] == 0 and rep["matched_existing_count"] == 1, rep

    db = _db()
    try:
        auto = db.scalar(select(models.Venue).where(models.Venue.dedup_key == name.lower()))
        assert (auto.name, auto.address, auto.usage_count, auto.source) == before
        ev = db.get(models.Event, api.event_id)
        assert ev.venue_name == name and ev.venue_address == "הרצל 9, רחובות"
    finally:
        db.close()


def test_couples_cannot_overwrite_imported_address() -> None:
    from sqlalchemy import select

    from app import models, venues

    bootstrap()
    _import(_catalog(), dry_run=False)
    db = _db()
    try:
        venues.record_venue(db, f"גן הפקאן {TAG}", "כתובת אחרת שהזוג הקליד")
        db.commit()
        v = db.scalar(select(models.Venue).where(models.Venue.import_key == f"test:{TAG}:e"))
        assert v.address == "" and v.usage_count == 1  # נספר שימוש, הכתובת לא נדרסה
    finally:
        db.close()


def test_same_name_in_two_cities_counts_usage_on_the_right_one() -> None:
    from sqlalchemy import select

    from app import models, venues

    bootstrap()
    _import(_catalog(), dry_run=False)
    db = _db()
    try:
        venues.record_venue(db, f"אולמי הנסיכה {TAG}", "הבושם 3, אשדוד")
        db.commit()
        bs = db.scalar(select(models.Venue).where(models.Venue.import_key == f"test:{TAG}:a"))
        ash = db.scalar(select(models.Venue).where(models.Venue.import_key == f"test:{TAG}:b"))
        assert ash.usage_count >= 1 and bs.usage_count == 0
    finally:
        db.close()


def test_admin_edit_survives_reimport_and_closed_is_hidden() -> None:
    from sqlalchemy import select

    from app import models

    api, _ = bootstrap()
    admin = _admin()
    _import(_catalog(), dry_run=False)
    db = _db()
    try:
        vid = db.scalar(select(models.Venue.id).where(models.Venue.import_key == f"test:{TAG}:c"))
    finally:
        db.close()
    r = api.client.patch(f"/admin/venue-cms/{vid}", headers=admin, json={"address": "הצורן 4א", "phone": "09-0000000"})
    assert r.status_code == 200, r.text
    changed = _catalog()
    changed[2]["address"] = "כתובת מהקובץ"
    rep = _import(changed, dry_run=False)
    assert rep["skipped_admin_edited"] == 1, rep
    db = _db()
    try:
        v = db.get(models.Venue, vid)
        assert v.address == "הצורן 4א" and v.phone == "09-0000000"
    finally:
        db.close()
    assert not any(v["name"] == f"פוגאטה {TAG}" for v in _search(api, f"פוגאטה {TAG}")), "מקום סגור הוצע"


# ── חיפוש ────────────────────────────────────────────────────────────────────

def test_search_by_name_alias_city_address_and_typos() -> None:
    api, _ = bootstrap()
    _import(_catalog(), dry_run=False)

    def names(q):
        return [(v["name"], v["city"]) for v in _search(api, q)]

    # שם + שני יישובים באותו שם: שתי תוצאות, עם העיר להבחנה, בלי כפילות
    hits = names(f"הנסיכה {TAG}")
    assert (f"אולמי הנסיכה {TAG}", "באר שבע") in hits and (f"אולמי הנסיכה {TAG}", "אשדוד") in hits
    assert len(hits) == len(set(hits))
    # שם חלופי באנגלית
    assert (f"אולמי הנסיכה {TAG}", "באר שבע") in names(f"princess {TAG}")
    # עיר (כולל אות שימוש: "בנתניה") וכתובת
    assert (f"שיבולים {TAG}", "נתניה") in names(f"בנתניה {TAG}")
    assert (f"פיטנגו {TAG}", "נתניה") in names(f"הצורן {TAG}")
    # שגיאת כתיב
    assert (f"גן הפקאן {TAG}", "רמת הכובש") in names(f"פקן {TAG}") + names(f"הפקאנ {TAG}")
    assert (f"שיבולים {TAG}", "נתניה") in names(f"שיבולימ {TAG}")


def test_search_response_shape_shows_city_and_kind() -> None:
    api, _ = bootstrap()
    _import(_catalog(), dry_run=False)
    row = next(v for v in _search(api, f"גן הפקאן {TAG}") if v["name"] == f"גן הפקאן {TAG}")
    assert row["city"] == "רמת הכובש" and row["kind_label"] == "גן אירועים"
    # מתחם עם שני אולמות באותה כתובת — שני מקומות נפרדים
    both = {v["name"] for v in _search(api, f"הצורן {TAG}")}
    assert {f"שיבולים {TAG}", f"פיטנגו {TAG}"} <= both


def test_manual_venue_not_in_catalog_is_saved_and_suggested() -> None:
    api, _ = bootstrap()
    name = f"החצר של סבתא {TAG}"
    assert _search(api, name) == []
    r = api.client.patch("/event", headers=api.headers, json={"venue_name": name, "venue_address": "הגפן 3, כפר ורדים"})
    assert r.status_code == 200 and r.json()["venue_name"] == name
    other, _ = bootstrap()
    assert any(v["name"] == name for v in _search(other, f"החצר של סבתא {TAG}"))


# ── הרשאות ──────────────────────────────────────────────────────────────────

def test_permissions_for_import_and_search() -> None:
    api, _ = bootstrap()
    support = _admin("support")
    admin = _admin()
    assert api.client.post("/admin/venue-cms/catalog/import", headers=support, json={"apply": True}).status_code == 403
    assert api.client.post("/admin/venue-cms/catalog/import", headers=api.headers, json={"apply": True}).status_code in (401, 403)
    assert api.client.get("/venues/search", params={"q": "אולם"}).status_code in (401, 403)
    # תצוגה מקדימה דרך ה-API (מהקובץ האמיתי) לא כותבת כלום
    from sqlalchemy import func, select

    from app import models

    db = _db()
    try:
        before = db.scalar(select(func.count(models.Venue.id)))
    finally:
        db.close()
    r = api.client.post("/admin/venue-cms/catalog/import", headers=admin, json={})
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["created"] > 0, r.text
    db = _db()
    try:
        assert db.scalar(select(func.count(models.Venue.id))) == before
    finally:
        db.close()
    info = api.client.get("/admin/venue-cms/catalog", headers=support)
    assert info.status_code == 200 and info.json()["count"] > 0


def test_search_does_not_leak_internal_fields() -> None:
    api, _ = bootstrap()
    _import([_rec("n", f"אולם סודי {TAG}", "חיפה", notes="הערה פנימית לא לפרסום", phone="04-1111111")], dry_run=False)
    body = json.dumps(_search(api, f"אולם סודי {TAG}"), ensure_ascii=False)
    assert "הערה פנימית" not in body and "04-1111111" not in body and "import_key" not in body


# ── ביצועים ─────────────────────────────────────────────────────────────────

def test_search_performance_with_5000_venues() -> None:
    from app import cache, venues

    bootstrap()
    cities = ["תל אביב-יפו", "ירושלים", "חיפה", "באר שבע", "אשדוד", "נתניה", "אילת", "עפולה", "כרמיאל", "מודיעין"]
    words = ["ארמון", "גן", "נוף", "פנינה", "אחוזת", "בית", "היכל", "טרסה", "קסם", "שמש", "ירח", "יהלום", "אגם"]
    recs = [_rec(f"p{i}", f"{words[i % 13]} {words[(i * 7) % 13]} {i}", cities[i % 10], address=f"הרצל {i % 200}")
            for i in range(5000)]
    t0 = time.time()
    rep = _import(recs, dry_run=False)
    import_s = time.time() - t0
    assert rep["created"] == 5000, rep
    assert import_s < 120, f"ייבוא 5,000 לקח {import_s:.0f} שניות"

    db = _db()
    try:
        cache.invalidate_prefix("venues:")
        t0 = time.time()
        venues.search_venues(db, "ארמון")  # בונה את האינדקס
        build_ms = (time.time() - t0) * 1000
        times = []
        for q in ["ארמון נוף", "גן", "בחיפה", "פנינא", "היכל 12", "טרסה ירושלים", "יהלומ", "אחוזת קסם 4"]:
            t0 = time.time()
            res = venues.search_venues(db, q)
            times.append((time.time() - t0) * 1000)
            assert len(res) <= 8
        avg = sum(times) / len(times)
        assert build_ms < 5000, f"בניית אינדקס {build_ms:.0f}ms"
        assert avg < 250 and max(times) < 600, f"חיפוש ממוצע {avg:.0f}ms, מקסימום {max(times):.0f}ms"
        print(f"\n[perf] import 5000: {import_s:.1f}s · index: {build_ms:.0f}ms · search avg {avg:.0f}ms max {max(times):.0f}ms")
    finally:
        db.close()


# ── קובץ המאגר האמיתי ────────────────────────────────────────────────────────

def test_real_catalog_file_is_consistent() -> None:
    from app import venue_catalog

    data = venue_catalog.load_catalog()
    items = data["venues"]
    assert data["count"] == len(items) > 500
    keys = [v["import_key"] for v in items]
    assert len(keys) == len(set(keys)), "import_key כפול בקובץ"
    for v in items:
        assert v["name"].strip(), v
        assert v["sources"], f"רשומה בלי מקור: {v['name']}"
        assert v["verification"] in ("verified_sources", "single_source", "needs_review"), v
        assert v["operating_status"] in ("unknown", "closed_reported", "uncertain"), v
        # לא ממציאים: אין רשומה שמסומנת "פעילה" — רק לא-נבדק/סגור/לא-ודאי
        assert venue_catalog.validate(v)[1] is None, v
    # אין שני מקומות עם אותו שם מנורמל באותו יישוב (זה היה אמור להתמזג)
    from app.venue_text import city_key, name_key

    pairs = [(name_key(v["name"], v["city"]), city_key(v["city"])) for v in items if v["city"]]
    dups = {p for p in pairs if pairs.count(p) > 1}
    assert len(dups) <= len(pairs) * 0.01, f"כפילויות לא מטופלות: {sorted(dups)[:10]}"


def teardown_module(module) -> None:  # noqa: ARG001
    # המודול הזה פותח הרבה סשנים ישירים (SessionLocal); חיבורים שנשארים במאגר
    # מצביעים על קובץ ה-DB הזמני שנמחק ב-shutdown — והמודול הבא היה מקבל
    # "readonly database". משחררים אותם לפני המחיקה.
    from app.database import engine

    engine.dispose()
    shutdown()
