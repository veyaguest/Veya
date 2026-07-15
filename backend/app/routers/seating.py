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

    # אילוצים שנגזרו מההערות (שלב 4) — זוגות אסורים (קשיח) + "לשבת יחד" (רך).
    constraint_dicts = [
        {"id": g.id, "constraints_parsed": g.constraints_parsed} for g in guests
    ]
    forbidden = set(parser.build_forbidden_pairs(constraint_dicts))
    forbidden.update(tuple(p) for p in payload.forbidden_pairs)  # + מה שהמשתמש ביקש
    together = parser.build_together_pairs(constraint_dicts)

    t0 = time.time()
    result = seating.generate_seating(
        guests=guest_dicts,
        seats_per_table=payload.seats_per_table,
        num_tables=payload.num_tables,
        forbidden_pairs=list(forbidden),
        together_pairs=together,
    )
    elapsed = time.time() - t0

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
    )
