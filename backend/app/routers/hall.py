"""מפת אולם — סידור השולחנות במרחב וגרירת מוזמנים (שלב 7).

המנוע האוטומטי (שלב 3) קובע שיבוץ התחלתי; כאן הבעלים יכול לכוונן ידנית —
לגרור שולחנות למיקום שמתאים לאולם האמיתי, ולהעביר מוזמן משולחן לשולחן.
המערכת מתריעה על חריגות (יותר מדי אנשים בשולחן, או זוג "לא לשבת יחד" יחד),
אבל לא חוסמת — ההחלטה הסופית של הבעלים.
"""
import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import constraints as parser
from app import media, models, schemas
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/hall", tags=["hall"])


def _guest_out(g: models.Guest) -> schemas.HallGuest:
    return schemas.HallGuest(
        id=g.id,
        full_name=g.full_name,
        party_size=g.party_size,
        seats=g.effective_seats,
        side=g.side,
        group_type=g.group_type,
        rsvp_status=g.rsvp_status,
        is_child=g.is_child,
    )


def _auto_position(index: int) -> dict:
    """פריסת רשת ברירת-מחדל לשולחן שאין לו עדיין מיקום שמור."""
    cols = 4
    row, col = divmod(index, cols)
    return {"x": 60 + col * 190.0, "y": 60 + row * 190.0}


# מיגרציה שקטה: נתונים ישנים נשמרו עם "shape": "round"|"long" בלבד.
# מ-Long (מלבני-ארוך פשוט) יש להבדיל מ"אבירים" (אותו הדבר ויזואלית כרגע —
# הבחירה בין ריבוע/מלבן/אבירים היא רק מספר המקומות וסידור הכיסאות).
_LEGACY_SHAPE_TO_TYPE = {"round": "round", "long": "knights"}


def _table_type_from_pos(pos: dict) -> str:
    if pos.get("table_type"):
        return str(pos["table_type"])
    return _LEGACY_SHAPE_TO_TYPE.get(str(pos.get("shape", "round")), "round")


def _compute_warnings(
    tables: dict[int, list[models.Guest]],
    capacities: dict[int, int],
    all_guests: list[models.Guest],
) -> list[str]:
    warnings: list[str] = []
    forbidden = set(
        parser.build_forbidden_pairs(
            [{"id": g.id, "constraints_parsed": g.constraints_parsed} for g in all_guests]
        )
    )
    name_by_id = {g.id: g.full_name for g in all_guests}
    for tnum, members in tables.items():
        used = sum(g.effective_seats for g in members)
        cap = capacities.get(tnum, 12)
        if used > cap:
            warnings.append(f"שולחן {tnum}: {used} אנשים מתוך {cap} — חריגה מהקיבולת")
        ids = [g.id for g in members]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair = (min(ids[i], ids[j]), max(ids[i], ids[j]))
                if pair in forbidden:
                    warnings.append(
                        f"שולחן {tnum}: {name_by_id[ids[i]]} ו{name_by_id[ids[j]]} "
                        f'מסומנים כ"לא לשבת יחד"'
                    )
    return warnings


@router.get("", response_model=schemas.HallState)
def get_hall(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    positions = event.table_positions or {}
    seats = event.seats_per_table or 12

    tables: dict[int, list[models.Guest]] = {}
    unassigned: list[models.Guest] = []
    for g in guests:
        if g.table_number is None:
            unassigned.append(g)
        else:
            tables.setdefault(g.table_number, []).append(g)

    # שולחן יכול להישאר בלי אף מוזמן (כל האורחים הועברו הלאה) ועדיין להיות
    # קיים במפה — יש לכלול גם אותו, לא רק שולחנות שיש בהם כרגע מישהו,
    # אחרת הוא "נעלם" מהמפה אחרי שמירה (למרות שהמיקום שלו נשמר ב-DB).
    all_table_numbers = set(tables.keys()) | {int(k) for k in positions.keys()}

    capacities = {
        tnum: int((positions.get(str(tnum)) or {}).get("capacity") or seats)
        for tnum in all_table_numbers
    }
    warnings = _compute_warnings(tables, capacities, guests)

    out_tables: list[schemas.HallTable] = []
    for idx, tnum in enumerate(sorted(all_table_numbers)):
        members = tables.get(tnum, [])
        pos = positions.get(str(tnum)) or _auto_position(idx)
        out_tables.append(
            schemas.HallTable(
                table_number=tnum,
                x=float(pos["x"]),
                y=float(pos["y"]),
                seats_used=sum(g.effective_seats for g in members),
                guests=[_guest_out(g) for g in members],
                table_type=_table_type_from_pos(pos),
                capacity=capacities[tnum],
                rotation=float(pos.get("rotation", 0)),
                name=str(pos.get("name", "")),
                color=str(pos.get("color", "")),
                notes=str(pos.get("notes", "")),
                locked=bool(pos.get("locked", False)),
            )
        )

    elements = [
        schemas.HallElement(**el) for el in (event.hall_elements or [])
    ]

    # זוגות אילוצים שכבר מחושבים היום מהערות חופשיות — נחשפים כאן כדי
    # שעוזר ההושבה החכם בצד הלקוח יוכל לבדוק אותם מיידית (כולל בזמן גרירה)
    # בלי קריאת רשת נוספת. אותו דפוס בדיוק כמו ב-routers/seating.py.
    constraint_dicts = [
        {"id": g.id, "constraints_parsed": g.constraints_parsed} for g in guests
    ]
    forbidden_pairs = parser.build_forbidden_pairs(constraint_dicts)
    together_pairs = parser.build_together_pairs(constraint_dicts)

    return schemas.HallState(
        seats_per_table=seats,
        tables=out_tables,
        unassigned=[_guest_out(g) for g in unassigned],
        elements=elements,
        warnings=warnings,
        sketch=media.to_url(event.hall_sketch),
        forbidden_pairs=forbidden_pairs,
        together_pairs=together_pairs,
    )


@router.put("", response_model=schemas.HallState)
def save_hall(
    payload: schemas.SaveHallRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    by_id = {g.id: g for g in guests}

    # אימות: כל מוזמן מופיע לכל היותר פעם אחת בשולחן אחד.
    seen: set[int] = set()
    positions: dict[str, dict] = {}
    assigned: dict[int, int] = {}  # guest_id -> table_number
    for t in payload.tables:
        positions[str(t.table_number)] = {
            "x": t.x,
            "y": t.y,
            "table_type": t.table_type,
            "capacity": t.capacity,
            "rotation": t.rotation,
            "name": t.name,
            "color": t.color,
            "notes": t.notes,
            "locked": t.locked,
        }
        for gid in t.guest_ids:
            if gid in seen:
                raise HTTPException(status_code=400, detail=f"מוזמן {gid} משובץ פעמיים")
            seen.add(gid)
            if gid in by_id:
                assigned[gid] = t.table_number

    # החלת השיבוץ: מי שברשימה מקבל שולחן, כל השאר חוזר ל"ללא שולחן".
    for g in guests:
        g.table_number = assigned.get(g.id)

    event.table_positions = positions
    if payload.elements is not None:
        event.hall_elements = [el.model_dump() for el in payload.elements]
    if payload.seats_per_table:
        event.seats_per_table = payload.seats_per_table
    # סקיצת האולם: None => לא נגענו; "" => מחיקה; data URL => קובץ חדש;
    # URL קיים => ללא שינוי. הטיפול מרוכז ב-media.resolve_incoming.
    if payload.sketch is not None:
        event.hall_sketch = media.resolve_incoming(
            payload.sketch, event.hall_sketch, prefix=f"sketch-{event.id}"
        )
    db.commit()

    return get_hall(db=db, event=event)
