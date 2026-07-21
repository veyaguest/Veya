"""נקודת API לייצור שיבוץ הושבה (שלב 3).

קוראת את המוזמנים מה-DB, מריצה את המנוע הדטרמיניסטי (`app.seating`),
ומחזירה שיבוץ לשולחנות. אפשר גם לשמור את מספר השולחן חזרה על כל מוזמן.
"""
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import constraints as parser
from app import models, schemas, seating
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/seating", tags=["seating"])


@router.post("/generate", response_model=schemas.SeatingResponse)
def generate(
    payload: schemas.SeatingRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
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
    (המנוע יחזור למצב האבסטרקטי)."""
    meta: list[dict] = []
    for key, pos in (positions or {}).items():
        try:
            tnum = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
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
