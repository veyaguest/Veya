"""נקודת API לייצור שיבוץ הושבה (שלב 3).

קוראת את המוזמנים מה-DB, מריצה את המנוע הדטרמיניסטי (`app.seating`),
ומחזירה שיבוץ לשולחנות. אפשר גם לשמור את מספר השולחן חזרה על כל מוזמן.
"""
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import constraints as parser
from app import models, permissions, schemas, seating
from app.database import get_db
from app.deps import EventAccess

_view = EventAccess(permissions.GUESTS_VIEW)
_write = EventAccess(permissions.SEATING_WRITE)


router = APIRouter(prefix="/seating", tags=["seating"])


@router.post("/generate", response_model=schemas.SeatingResponse)
def generate(
    payload: schemas.SeatingRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    stmt = select(models.Guest).where(models.Guest.event_id == event.id)
    if payload.only_confirmed:
        stmt = stmt.where(models.Guest.rsvp_status == "confirmed")
    guests = db.scalars(stmt).all()

    if not guests:
        raise HTTPException(status_code=400, detail="אין מוזמנים לשיבוץ")

    # חבורה בודדת גדולה מקיבולת שולחן — לא ניתן לשבץ.
    # סופרים לפי הכמות שאושרה בפועל (effective_seats), לא לפי מה שהוזמן.
    too_big = [g for g in guests if g.effective_seats > payload.seats_per_table]
    if too_big:
        names = ", ".join(g.full_name for g in too_big[:3])
        raise HTTPException(
            status_code=400,
            detail=f'חבורה גדולה ממספר הכיסאות לשולחן: {names}',
        )

    guest_dicts = [
        {
            "id": g.id,
            "full_name": g.full_name,
            "side": g.side,
            "group_type": g.group_type,
            # המנוע משבץ לפי הכמות שאושרה בפועל (מי שביטל תופס 0 מקומות).
            "party_size": g.effective_seats,
        }
        for g in guests
    ]

    # אילוצים מההערות — נגזרים *טרי* בזמן השיבוץ, ולא מסתמכים על constraints_parsed
    # השמור (שעלול להיות ריק אם המשתמש רק הקליד הערה ולא הריץ ניתוח ידני). כך
    # "לא לשבת יחד" שנכתב בהערה תמיד נאכף כחוק קשיח בסידור האוטומטי.
    # התאמה *מכלילה*: שם פרטי בלבד → כל המוזמנים באותו שם (כל ה"דני" באולם);
    # "משפחת X" → כל בני המשפחה. build_pairs_from_guests מיישם זאת ישירות מתוך
    # ההערות הגולמיות, בלי resolve_name (שבוחר התאמה יחידה והופך שם עמום להבהרה).
    guest_full = [
        {"id": g.id, "full_name": g.full_name, "notes_raw": g.notes_raw}
        for g in guests
    ]
    fb, tg = parser.build_pairs_from_guests(guest_full)
    forbidden = set(fb)
    forbidden.update(tuple(p) for p in payload.forbidden_pairs)  # + מה שהמשתמש ביקש
    together = tg

    # --- הושבה מודעת-מיקום: מיקומי השולחנות + מרכזי האזורים + העדפות מההערות ---
    tables_meta = _build_tables_meta(event.table_positions or {}, payload.seats_per_table)

    # רזרבה מפוזרת: משאירים מקומות פנויים בשיבוץ האוטומטי (מפוזר אחיד). רק במצב
    # מודע-מיקום, שבו יש שולחנות אמיתיים באולם. None בבקשה => הערך השמור על האירוע.
    reserve_seats = (
        payload.reserve_seats if payload.reserve_seats is not None
        else (event.reserve_seats or 0)
    )
    if tables_meta and reserve_seats > 0:
        _apply_distributed_reserve(tables_meta, reserve_seats)
        total_needed = sum(g.effective_seats for g in guests)
        available = sum(t["capacity"] for t in tables_meta)
        if available < total_needed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"הרזרבה גדולה מדי: אחרי השארת {reserve_seats} מקומות פנויים "
                    f"נשארו {available} מקומות ל-{total_needed} אנשים. "
                    "הקטינו את הרזרבה או הוסיפו שולחנות."
                ),
            )

    zones = _build_zones(event.hall_elements or [])
    group_notes = event.group_notes or {}
    preferences = {
        g.id: parser.guest_preferences(
            g.notes_raw, g.guest_note, group_notes.get(g.group_type)
        )
        for g in guests
    }
    preferences = {gid: prefs for gid, prefs in preferences.items() if prefs}

    t0 = time.time()
    result = seating.generate_seating(
        guests=guest_dicts,
        seats_per_table=payload.seats_per_table,
        num_tables=payload.num_tables,
        forbidden_pairs=list(forbidden),
        together_pairs=together,
        tables_meta=tables_meta,
        zones=zones,
        preferences=preferences,
        event_type=event.event_type,
    )
    elapsed = time.time() - t0

    # הסברי "למה שובץ כאן" — רק למוזמנים שהיו להם העדפה מההערות, כדי שהפאנל
    # יבליט שהמערכת אכן הבינה את ההערות (ולא יציף עם כל מוזמן).
    explanations = _build_explanations(result.tables, preferences)

    persisted = False
    if payload.persist and result.hard_ok:
        table_by_guest = {
            party["id"]: table["table_number"]
            for table in result.tables
            for party in table["parties"]
        }
        for g in guests:
            g.table_number = table_by_guest.get(g.id)
        # שומרים גם את יעד הרזרבה שנבחר, כדי שהבחירה תישאר קבועה לאירוע.
        if payload.reserve_seats is not None:
            event.reserve_seats = payload.reserve_seats
        db.commit()
        persisted = True

    # אזהרה לוג צד-שרת אם חרגנו מיעד הביצועים (PRD: פחות משנייה ל-200 אורחים).
    if elapsed > 1.0:
        print(f"[seating] warning: took {elapsed:.2f}s for {len(guests)} guests")

    return schemas.SeatingResponse(
        tables=result.tables,
        total_people=result.total_people,
        num_tables=result.num_tables,
        seats_per_table=result.seats_per_table,
        score=result.score,
        hard_ok=result.hard_ok,
        unseated=result.unseated,
        persisted=persisted,
        explanations=explanations,
    )


# מיפוי סוג-אלמנט → אילו אזורים הוא מזין. "רעש" (loud) מוזן גם מרחבת הריקודים
# וגם מעמדת ה-DJ/רמקולים — משם רוצים להתרחק כשמבקשים "רחוק מהרעש".
def _build_zones(hall_elements: list[dict]) -> dict:
    """בונה מרכזי אזורים מהאלמנטים המיוחדים במפה: {zone: [(x,y), ...]}."""
    zones: dict[str, list[tuple[float, float]]] = {}

    def center(el: dict) -> tuple[float, float]:
        return (
            float(el.get("x", 0)) + float(el.get("width", 0)) / 2,
            float(el.get("y", 0)) + float(el.get("height", 0)) / 2,
        )

    for el in hall_elements:
        etype = el.get("type")
        c = center(el)
        if etype == "dance_floor":
            zones.setdefault("dance_floor", []).append(c)
            zones.setdefault("loud", []).append(c)
        elif etype == "bar":
            zones.setdefault("bar", []).append(c)
        elif etype == "entrance":
            zones.setdefault("entrance", []).append(c)
        elif etype == "dj":
            zones.setdefault("loud", []).append(c)
    return zones


def _build_tables_meta(positions: dict, default_seats: int) -> list[dict]:
    """הופך את מיקומי השולחנות השמורים (event.table_positions) לרשימה שהמנוע
    מבין: [{table_number, x, y, capacity}]. שולחנות ללא מיקום → רשימה ריקה
    (המנוע יחזור למצב האבסטרקטי). שולחנות רזרבה (is_reserve) מוצאים מהשיבוץ
    האוטומטי — נשמרים לשיבוץ ידני ביום האירוע בלבד."""
    meta: list[dict] = []
    for key, pos in (positions or {}).items():
        try:
            tnum = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
            continue
        if pos.get("is_reserve"):
            continue
        meta.append(
            {
                "table_number": tnum,
                "x": float(pos["x"]),
                "y": float(pos["y"]),
                "capacity": int(pos.get("capacity") or default_seats),
            }
        )
    return meta


def _apply_distributed_reserve(meta: list[dict], reserve: int) -> int:
    """מוריד קיבולת זמינה מהשולחנות הפעילים כדי להשאיר סה"כ ``reserve`` מקומות
    פנויים, מפוזרים אחיד (base לכל שולחן + שארית לשולחנות הראשונים לפי מספר).
    משנה את ``meta`` in-place ומחזיר כמה מקומות הופחתו בפועל. לא מוריד שולחן
    מתחת למקום אחד זמין, כדי לא לנטרל אותו לגמרי (עודף לא-נספג פשוט לא ננעל)."""
    if reserve <= 0 or not meta:
        return 0
    n = len(meta)
    base, extra = divmod(reserve, n)
    order = sorted(range(n), key=lambda i: meta[i]["table_number"])
    applied = 0
    for rank, i in enumerate(order):
        want = base + (1 if rank < extra else 0)
        cap = meta[i]["capacity"]
        reduce = min(want, max(0, cap - 1))
        meta[i]["capacity"] = cap - reduce
        applied += reduce
    return applied


def _occupancy_tables(event: models.Event, guests: list[models.Guest]) -> list[dict]:
    """מצב השולחנות הנוכחי להמלצת שיבוץ/סיכום רזרבה: לכל שולחן מהמפה — קיבולת,
    דגל רזרבה, מיקום, והחברים היושבים בו כרגע (לפי הכמות שתופסים בפועל)."""
    positions = event.table_positions or {}
    default_seats = event.seats_per_table or 12
    members_by_table: dict[int, list[dict]] = {}
    for g in guests:
        if g.table_number is not None:
            members_by_table.setdefault(g.table_number, []).append(
                {"id": g.id, "side": g.side, "group_type": g.group_type,
                 "size": g.effective_seats}
            )
    tables: list[dict] = []
    for key, pos in positions.items():
        try:
            tnum = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(pos, dict):
            continue
        tables.append(
            {
                "table_number": tnum,
                "name": str(pos.get("name", "")),
                "capacity": int(pos.get("capacity") or default_seats),
                "is_reserve": bool(pos.get("is_reserve", False)),
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "members": members_by_table.get(tnum, []),
            }
        )
    return tables


@router.post("/recommend-seat", response_model=schemas.RecommendSeatResponse)
def recommend_seat(
    payload: schemas.RecommendSeatRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """ממליץ על השולחן המתאים ביותר לשבץ בו מוזמן (מצב יום האירוע). דטרמיניסטי —
    אותם משקלים כמו המנוע (צד/קבוצה/'לשבת עם' + העדפות). לא משבץ, רק ממליץ."""
    guest = db.get(models.Guest, payload.guest_id)
    if not guest or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")

    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()

    guest_full = [
        {"id": g.id, "full_name": g.full_name, "notes_raw": g.notes_raw}
        for g in guests
    ]
    fb, tg = parser.build_pairs_from_guests(guest_full)

    tables = _occupancy_tables(event, guests)
    # מסירים את המוזמן עצמו מהשולחן הנוכחי שלו (אם משבצים מחדש) — שלא ייחשב.
    for t in tables:
        t["members"] = [m for m in t["members"] if m["id"] != guest.id]

    zones = _build_zones(event.hall_elements or [])
    group_notes = event.group_notes or {}
    prefs = parser.guest_preferences(
        guest.notes_raw, guest.guest_note, group_notes.get(guest.group_type)
    )
    needed = max(1, guest.effective_seats)
    recs = seating.recommend_seats(
        guest={
            "id": guest.id, "side": guest.side,
            "group_type": guest.group_type, "party_size": needed,
        },
        tables=tables,
        forbidden_pairs=list(fb),
        together_pairs=tg,
        zones=zones,
        guest_prefs=prefs,
        include_reserve=payload.include_reserve,
        event_type=event.event_type,
    )
    return schemas.RecommendSeatResponse(
        guest_id=guest.id,
        guest_name=guest.full_name,
        seats_needed=needed,
        recommendations=[schemas.SeatRecommendation(**r) for r in recs],
    )


@router.post("/assign", response_model=schemas.AssignSeatResult)
def assign_seat(
    payload: schemas.AssignSeatRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    """שיבוץ מהיר בקליק אחד (מצב יום האירוע). מחזיר אזהרות רכות (קיבולת / זוג
    'לא לשבת יחד') אך אינו חוסם — ההחלטה הסופית של המשתמש."""
    guest = db.get(models.Guest, payload.guest_id)
    if not guest or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")

    warnings: list[str] = []
    if payload.table_number is not None:
        guests = db.scalars(
            select(models.Guest).where(models.Guest.event_id == event.id)
        ).all()
        positions = event.table_positions or {}
        pos = positions.get(str(payload.table_number)) or {}
        cap = int(pos.get("capacity") or event.seats_per_table or 12)
        others = [
            g for g in guests
            if g.table_number == payload.table_number and g.id != guest.id
        ]
        used = sum(g.effective_seats for g in others) + max(1, guest.effective_seats)
        if used > cap:
            warnings.append(
                f"שולחן {payload.table_number}: {used} אנשים מתוך {cap} — חריגה מהקיבולת"
            )
        guest_full = [
            {"id": g.id, "full_name": g.full_name, "notes_raw": g.notes_raw}
            for g in guests
        ]
        fb, _ = parser.build_pairs_from_guests(guest_full)
        forbidden = {(min(a, b), max(a, b)) for a, b in fb}
        for o in others:
            if (min(o.id, guest.id), max(o.id, guest.id)) in forbidden:
                warnings.append(
                    f'{guest.full_name} ו{o.full_name} מסומנים כ"לא לשבת יחד"'
                )

    guest.table_number = payload.table_number
    db.commit()
    return schemas.AssignSeatResult(
        guest_id=guest.id, table_number=guest.table_number, warnings=warnings
    )


@router.get("/reserve", response_model=schemas.ReserveSummary)
def reserve_summary(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """סיכום הרזרבה — לכרטיס הדשבורד ולפאנל 'מצב יום האירוע'."""
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    positions = event.table_positions or {}
    default_seats = event.seats_per_table or 12

    used_by_table: dict[int, int] = {}
    for g in guests:
        if g.table_number is not None:
            used_by_table[g.table_number] = (
                used_by_table.get(g.table_number, 0) + g.effective_seats
            )

    reserve_tables = 0
    reserve_cap = 0
    free_active = 0
    for key, pos in positions.items():
        try:
            tnum = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(pos, dict):
            continue
        cap = int(pos.get("capacity") or default_seats)
        used = used_by_table.get(tnum, 0)
        if pos.get("is_reserve"):
            reserve_tables += 1
            reserve_cap += cap
        else:
            free_active += max(0, cap - used)

    seated_people = sum(g.effective_seats for g in guests if g.table_number is not None)
    unseated = sum(
        1 for g in guests if g.table_number is None and g.effective_seats > 0
    )
    return schemas.ReserveSummary(
        reserve_seats=event.reserve_seats or 0,
        reserve_tables=reserve_tables,
        reserve_tables_capacity=reserve_cap,
        free_seats_active=free_active,
        seated_people=seated_people,
        unseated_guests=unseated,
    )


def _build_explanations(
    tables: list[dict], preferences: dict
) -> list[schemas.SeatingExplanation]:
    """אוסף הסברי שיבוץ רק למוזמנים שהיו להם העדפה מההערות."""
    out: list[schemas.SeatingExplanation] = []
    for table in tables:
        for party in table.get("parties", []):
            gid = party.get("id")
            reasons = party.get("reasons") or []
            if gid in preferences and reasons:
                out.append(
                    schemas.SeatingExplanation(
                        guest_id=gid,
                        full_name=party.get("full_name", ""),
                        table_number=table.get("table_number"),
                        reasons=reasons,
                    )
                )
    return out
