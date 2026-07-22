"""נקודות API לפרסור הערות ולניהול תור ההבהרות (שלב 4).

- POST /constraints/analyze — מפרסר מחדש את ההערות של כל המוזמנים, שומר את
  האילוצים, ומעדכן את תור ההבהרות הממתינות (עמימויות).
- GET  /constraints/clarifications — תור ההבהרות הממתינות (עם שמות המועמדים).
- POST /constraints/clarifications/{id}/resolve — פותר הבהרה לפי בחירת המשתמש.

בחירות שהמשתמש כבר הכריע בהן נשמרות, כך שניתוח חוזר לא "שוכח" אותן.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import constraints as parser
from app import models, permissions, schemas
from app.database import get_db
from app.deps import EventAccess

_access = EventAccess(permissions.CLARIFICATIONS)


router = APIRouter(prefix="/constraints", tags=["constraints"])


def _guest_dicts(guests: list[models.Guest]) -> list[dict]:
    return [
        {"id": g.id, "full_name": g.full_name, "notes_raw": g.notes_raw}
        for g in guests
    ]


@router.post("/analyze", response_model=schemas.AnalyzeResult)
def analyze(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    guest_dicts = _guest_dicts(guests)

    # החלטות עבר של המשתמש (resolved/dismissed) — כדי לא לשכוח בחירות.
    existing = db.scalars(
        select(models.Clarification).where(
            models.Clarification.event_id == event.id
        )
    ).all()
    decided = {
        (c.source_guest_id, c.relation_type, c.target_text): c
        for c in existing
        if c.status in ("resolved", "dismissed")
    }

    counts = {"relations": 0, "resolved": 0, "ambiguous": 0, "unresolved": 0}
    needed: dict[tuple, list[int]] = {}  # עמימויות שעדיין דורשות הבהרה

    for g in guests:
        parsed = parser.analyze_guest(
            {"id": g.id, "full_name": g.full_name, "notes_raw": g.notes_raw},
            guest_dicts,
        )
        for rel in parsed["relations"]:
            counts["relations"] += 1
            if rel["status"] == "ambiguous":
                key = (g.id, rel["type"], rel["target_text"])
                prior = decided.get(key)
                if prior and prior.status == "resolved" and prior.chosen_guest_id:
                    rel["status"] = "resolved"
                    rel["target_guest_id"] = prior.chosen_guest_id
                    rel["candidates"] = [prior.chosen_guest_id]
                elif prior and prior.status == "dismissed":
                    rel["status"] = "dismissed"
                else:
                    needed[key] = rel["candidates"]
            counts[rel["status"]] = counts.get(rel["status"], 0) + 1
        g.constraints_parsed = parsed  # reassignment => SQLAlchemy מזהה שינוי

    # סנכרון תור ההבהרות הממתינות עם מה שבאמת עמום כרגע.
    pending = {
        (c.source_guest_id, c.relation_type, c.target_text): c
        for c in existing
        if c.status == "pending"
    }
    for key in list(pending):
        if key not in needed:  # ההערה נערכה/נפתרה — ההבהרה כבר לא רלוונטית
            db.delete(pending[key])
    for key, candidates in needed.items():
        if key not in pending:
            src_id, rel_type, target_text = key
            db.add(
                models.Clarification(
                    event_id=event.id,
                    source_guest_id=src_id,
                    relation_type=rel_type,
                    target_text=target_text,
                    candidate_ids=candidates,
                    status="pending",
                )
            )

    db.commit()

    pending_total = len(
        db.scalars(
            select(models.Clarification)
            .where(models.Clarification.event_id == event.id)
            .where(models.Clarification.status == "pending")
        ).all()
    )

    return schemas.AnalyzeResult(
        guests_analyzed=len(guests),
        relations_found=counts["relations"],
        resolved=counts.get("resolved", 0),
        ambiguous=counts.get("ambiguous", 0),
        unresolved=counts.get("unresolved", 0),
        pending_clarifications=pending_total,
    )


@router.get("/clarifications", response_model=list[schemas.ClarificationRead])
def list_clarifications(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    clars = db.scalars(
        select(models.Clarification)
        .where(models.Clarification.event_id == event.id)
        .where(models.Clarification.status == "pending")
        .order_by(models.Clarification.created_at)
    ).all()

    # מיפוי מזהה->שם לכל המוזמנים שנדרשים.
    guest_ids = {c.source_guest_id for c in clars}
    for c in clars:
        guest_ids.update(c.candidate_ids or [])
    names = {
        g.id: g.full_name
        for g in db.scalars(
            select(models.Guest).where(models.Guest.id.in_(guest_ids))
        ).all()
    }

    out = []
    for c in clars:
        out.append(
            schemas.ClarificationRead(
                id=c.id,
                source_guest_id=c.source_guest_id,
                source_guest_name=names.get(c.source_guest_id, "?"),
                relation_type=c.relation_type,
                target_text=c.target_text,
                candidates=[
                    schemas.ClarificationCandidate(
                        id=cid, full_name=names.get(cid, "?")
                    )
                    for cid in (c.candidate_ids or [])
                ],
            )
        )
    return out


@router.post("/clarifications/{clar_id}/resolve", response_model=schemas.AnalyzeResult)
def resolve_clarification(
    clar_id: int,
    payload: schemas.ResolveClarification,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    clar = db.get(models.Clarification, clar_id)
    if clar is None or clar.event_id != event.id:
        raise HTTPException(status_code=404, detail="הבהרה לא נמצאה")

    chosen = payload.chosen_guest_id
    if chosen is not None and chosen not in (clar.candidate_ids or []):
        raise HTTPException(status_code=400, detail="הבחירה אינה מבין המועמדים")

    clar.status = "resolved" if chosen is not None else "dismissed"
    clar.chosen_guest_id = chosen

    # מעדכן את היחס אצל המוזמן המקורי כדי שהשיבוץ ייקח אותו בחשבון.
    src = db.get(models.Guest, clar.source_guest_id)
    if src and src.constraints_parsed:
        parsed = dict(src.constraints_parsed)
        for rel in parsed.get("relations", []):
            if (
                rel.get("type") == clar.relation_type
                and rel.get("target_text") == clar.target_text
            ):
                if chosen is not None:
                    rel["status"] = "resolved"
                    rel["target_guest_id"] = chosen
                    rel["candidates"] = [chosen]
                else:
                    rel["status"] = "dismissed"
        src.constraints_parsed = parsed

    db.commit()

    pending_total = len(
        db.scalars(
            select(models.Clarification)
            .where(models.Clarification.event_id == event.id)
            .where(models.Clarification.status == "pending")
        ).all()
    )
    return schemas.AnalyzeResult(
        guests_analyzed=0,
        relations_found=0,
        resolved=1 if chosen is not None else 0,
        ambiguous=0,
        unresolved=0,
        pending_clarifications=pending_total,
    )
