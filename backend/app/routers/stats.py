"""נקודת API לדשבורד — תמונת מצב מהירה של האירוע (שלב 6).

מרכז את כל המספרים החשובים במקום אחד: כמה מוזמנים, כמה אישרו, פילוח לפי צד/קבוצה,
כמה שולחנות שובצו, וכמה הבהרות ממתינות. הכל בקריאה אחת, כדי שהמסך ייטען מהר.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=schemas.DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()

    total_guests = len(guests)
    total_people = sum(g.party_size for g in guests)
    confirmed = sum(1 for g in guests if g.rsvp_status == "confirmed")
    declined = sum(1 for g in guests if g.rsvp_status == "declined")
    maybe = sum(1 for g in guests if g.rsvp_status == "maybe")
    pending = sum(1 for g in guests if g.rsvp_status == "pending")
    # כמות האורחים שאישרו בפועל: לפי הכמות שהמוזמן הזין (confirmed_count),
    # ולא לפי כמה שהוזמנו (party_size). אם משום מה אין ערך — נופלים ל-party_size.
    confirmed_people = sum(
        (g.confirmed_count if g.confirmed_count is not None else g.party_size)
        for g in guests
        if g.rsvp_status == "confirmed"
    )
    responded = confirmed + declined
    response_rate = round(responded / total_guests * 100) if total_guests else 0

    by_side: dict = {"groom": 0, "bride": 0, "shared": 0}
    by_group: dict = {
        "close_family": 0, "extended_family": 0, "friends": 0, "work": 0,
        "army": 0, "studies": 0, "childhood": 0, "neighbors": 0, "other": 0,
    }
    for g in guests:
        by_side[g.side] = by_side.get(g.side, 0) + 1
        by_group[g.group_type] = by_group.get(g.group_type, 0) + 1

    seated = [g for g in guests if g.table_number is not None]
    tables_assigned = len({g.table_number for g in seated})

    # אותות ל"העדפות ישיבה" במדד המוכנות: מוזמנים עם הערה חופשית + קבוצות
    # שהוגדרה להן העדפה (סבב B). שניהם רכים — לא חוסמים.
    guests_with_notes = sum(1 for g in guests if (g.notes_raw or "").strip())
    group_notes_count = len(event.group_notes or {})

    invitations_sent = db.scalar(
        select(func.count()).select_from(models.Message)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status == "sent")
    ) or 0

    pending_clar = db.scalar(
        select(func.count()).select_from(models.Clarification)
        .where(models.Clarification.event_id == event.id)
        .where(models.Clarification.status == "pending")
    ) or 0

    return schemas.DashboardStats(
        total_guests=total_guests,
        total_people=total_people,
        confirmed_people=confirmed_people,
        confirmed=confirmed,
        declined=declined,
        maybe=maybe,
        pending=pending,
        response_rate=response_rate,
        invitations_sent=invitations_sent,
        by_side=by_side,
        by_group=by_group,
        tables_assigned=tables_assigned,
        seated_guests=len(seated),
        pending_clarifications=pending_clar,
        guests_with_notes=guests_with_notes,
        group_notes_count=group_notes_count,
        groom_name=event.groom_name,
        bride_name=event.bride_name,
        venue_name=event.venue_name,
    )
