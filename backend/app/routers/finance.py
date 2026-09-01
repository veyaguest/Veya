"""כספי האירוע — עלות האירוע, ספירת המתנות והסיכום שאחרי.

## מודל ההרשאות: ``owner_only`` בכל נתיב, בלי יוצא מן הכלל

זה המסך היחיד במערכת — יחד עם פרטי קבלת המתנות — שבו **אף חבר-אירוע לא
נכנס**. לא מפיק, לא אולם, בשום הרשאה. הסיבה מוצרית: ``event_expenses``
מכיל את מה שהזוג משלם לכל ספק אחר, ולעיתים הספק שיושב מול המסך הוא אחד
מהם; ו-``gift_envelopes`` הוא ספירת הכסף הפיזי של משק בית.

אותו כלל נאכף פעמיים ובאופן עצמאי — כאן (``EventAccess(owner_only=True)``)
וב-Postgres (``rls/16_finance_rls.sql``), בדיוק כמו בשאר המערכת.

## החישוב קורה בשרת. תמיד.

אף נתיב כאן לא מקבל סכום מחושב מהלקוח. ה-Frontend שולח מה שהזוג הקליד
(מחיר, כמות, התחייבות) ומקבל בחזרה מספרים מוכנים להצגה. זה אותו כלל
שכבר נאכף במתנות (``app/gift.py``), ומאותה סיבה: שני מקורות חישוב לאותו
מספר הם ההגדרה של באג שמתגלה מול חשבונית.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    audit,
    event_terms,
    finance,
    finance_categories,
    finance_service,
    guest_journey,
    models,
    schemas,
)
from app.auth import get_current_user
from app.database import get_db
from app.deps import EventAccess

# ראו הסבר בראש הקובץ: אין כאן וריאנט "צפייה בלבד" לחבר-אירוע, כי אין
# הרשאה שפותחת את המסך הזה. שער אחד, לכל הנתיבים.
_access = EventAccess(owner_only=True)

router = APIRouter(prefix="/finance", tags=["finance"])


# ════════════════════════════════════════════════════════════════════════
#  עזרים משותפים
# ════════════════════════════════════════════════════════════════════════

def _guests(db: Session, event_id: int) -> list[models.Guest]:
    return list(
        db.scalars(select(models.Guest).where(models.Guest.event_id == event_id)).all()
    )


def _expense_read(
    expense: models.EventExpense, line: finance.LineResult, event_type: str = "wedding"
) -> schemas.ExpenseRead:
    return schemas.ExpenseRead(
        id=expense.id,
        category=expense.category,
        # התווית בניסוח של סוג האירוע — "התינוק" בברית, "התינוקת" בבריתה.
        category_label=finance_categories.category_label(expense.category, event_type),
        item_key=expense.item_key,
        label=expense.label,
        calc_method=expense.calc_method,
        amount_agorot=expense.amount_agorot,
        quantity=expense.quantity,
        committed_quantity=expense.committed_quantity,
        min_total_agorot=expense.min_total_agorot,
        note=expense.note,
        vendor=expense.vendor or "",
        is_estimated=bool(expense.is_estimated),
        is_paid=bool(expense.is_paid),
        sort_order=expense.sort_order,
        total_agorot=line.total_agorot,
        total_display=finance.format_shekels(line.total_agorot),
        billed_quantity=line.billed_quantity,
        unused_quantity=line.unused_quantity,
        over_commitment=line.over_commitment,
        min_total_applied=line.min_total_applied,
    )


def _cost_summary(
    expenses: list[models.EventExpense], attendees: int, invited: int
) -> schemas.CostSummaryRead:
    """בונה את כל צד ההוצאות — כולל התרחישים וההתחייבויות.

    **כל מספר כאן נגזר מ-``finance.total_for``**, גם הסיכום וגם התרחישים
    וגם "כמה עולה אורח נוסף". לכן אין מצב שבו הלוח מראה מספר שלא מסתדר
    עם הסיכום שמעליו: הם לא שני חישובים, הם אותה פונקציה בשתי נקודות.
    """
    breakdown = finance.cost_breakdown(expenses, attendees, invited)

    steps = []
    for size in finance.STEP_SIZES:
        added = finance.total_for(expenses, attendees + size, invited) - breakdown.total_agorot
        steps.append(
            schemas.StepCostRead(
                guests=size,
                added_agorot=added,
                added_display=finance.format_shekels(added),
            )
        )

    commitment_points = {
        e.committed_quantity
        for e in expenses
        if e.calc_method == finance_categories.PER_ATTENDEE and e.committed_quantity
    }
    scenarios = []
    for point in finance.scenario_points(attendees, expenses):
        total = finance.total_for(expenses, point, invited)
        scenarios.append(
            schemas.ScenarioRead(
                attendees=point,
                total_agorot=total,
                total_display=finance.format_shekels(total),
                delta_agorot=total - breakdown.total_agorot,
                is_current=point == attendees,
                is_commitment=point in commitment_points,
            )
        )

    commitments = []
    for expense in expenses:
        if expense.calc_method != finance_categories.PER_ATTENDEE:
            continue
        if not expense.committed_quantity:
            continue
        line = breakdown.lines[expense.id]
        commitments.append(
            schemas.CommitmentRead(
                expense_id=expense.id,
                label=expense.label,
                committed_quantity=expense.committed_quantity,
                attendees=attendees,
                unused_quantity=line.unused_quantity,
                over_commitment=line.over_commitment,
                billed_quantity=line.billed_quantity or 0,
                unit_price_agorot=expense.amount_agorot,
                total_agorot=line.total_agorot,
                total_display=finance.format_shekels(line.total_agorot),
                min_total_agorot=expense.min_total_agorot,
                min_total_applied=line.min_total_applied,
            )
        )

    paid = sum(breakdown.lines[e.id].total_agorot for e in expenses if e.is_paid)
    estimated = sum(
        breakdown.lines[e.id].total_agorot for e in expenses if e.is_estimated
    )

    return schemas.CostSummaryRead(
        paid_agorot=paid,
        paid_display=finance.format_shekels(paid),
        unpaid_agorot=breakdown.total_agorot - paid,
        unpaid_display=finance.format_shekels(breakdown.total_agorot - paid),
        estimated_agorot=estimated,
        estimated_display=finance.format_shekels(estimated),
        total_agorot=breakdown.total_agorot,
        total_display=finance.format_shekels(breakdown.total_agorot),
        fixed_agorot=breakdown.fixed_agorot,
        fixed_display=finance.format_shekels(breakdown.fixed_agorot),
        variable_agorot=breakdown.variable_agorot,
        variable_display=finance.format_shekels(breakdown.variable_agorot),
        attendees=attendees,
        invited=invited,
        cost_per_attendee_agorot=breakdown.cost_per_attendee_agorot,
        cost_per_attendee_display=finance.format_shekels(
            breakdown.cost_per_attendee_agorot
        ),
        next_attendee_agorot=breakdown.next_attendee_agorot,
        next_attendee_display=finance.format_shekels(breakdown.next_attendee_agorot),
        steps=steps,
        scenarios=scenarios,
        commitments=commitments,
    )


def _income_read(income: finance_service.GiftIncome) -> schemas.GiftIncomeRead:
    return schemas.GiftIncomeRead(
        envelopes_agorot=income.envelopes_agorot,
        envelopes_display=finance.format_shekels(income.envelopes_agorot),
        envelopes_count=income.envelopes_count,
        credit_agorot=income.credit_agorot,
        credit_display=finance.format_shekels(income.credit_agorot),
        credit_count=income.credit_count,
        total_agorot=income.total_agorot,
        total_display=finance.format_shekels(income.total_agorot),
        unidentified_count=income.unidentified_count,
        unidentified_agorot=income.unidentified_agorot,
        unidentified_display=finance.format_shekels(income.unidentified_agorot),
    )


def _entry_read(entry: finance_service.GiftEntry) -> schemas.GiftEntryRead:
    return schemas.GiftEntryRead(
        source=entry.source,
        id=entry.id,
        amount_agorot=entry.amount_agorot,
        amount_display=finance.format_shekels(entry.amount_agorot),
        guest_id=entry.guest_id,
        guest_name=entry.guest_name,
        envelope_number=entry.envelope_number,
        note=entry.note,
        created_at=entry.created_at,
        shared_names=entry.shared_names,
        status=entry.status,
    )


def _breakdown_read(b: finance_service.GiftBreakdown) -> schemas.GiftBreakdownRead:
    return schemas.GiftBreakdownRead(
        from_attendees_agorot=b.from_attendees_agorot,
        from_attendees_display=finance.format_shekels(b.from_attendees_agorot),
        from_non_attendees_agorot=b.from_non_attendees_agorot,
        from_non_attendees_display=finance.format_shekels(b.from_non_attendees_agorot),
        unattributed_agorot=b.unattributed_agorot,
        unattributed_display=finance.format_shekels(b.unattributed_agorot),
        guests_counted=b.guests_counted,
        guests_not_counted=b.guests_not_counted,
    )


def _guest_row_read(row: finance_service.GuestGiftRow) -> schemas.GuestGiftRowRead:
    return schemas.GuestGiftRowRead(
        guest_id=row.guest_id,
        full_name=row.full_name,
        phone=row.phone,
        rsvp_status=row.rsvp_status,
        party_size=row.party_size,
        attended_count=row.attended_count,
        status=row.status,
        total_agorot=row.total_agorot,
        total_display=finance.format_shekels(row.total_agorot),
        envelope_agorot=row.envelope_agorot,
        # מעטפה שלא נספרה מציגה מחרוזת ריקה ולא "0 ₪": אפס הוא טענה
        # ("נספרה מעטפה ריקה") שאין לה כיסוי כשלא נספר כלום.
        envelope_display=finance.format_shekels(row.envelope_agorot) if row.envelope_count else "",
        credit_agorot=row.credit_agorot,
        credit_display=finance.format_shekels(row.credit_agorot) if row.credit_count else "",
        envelope_count=row.envelope_count,
        credit_count=row.credit_count,
        gift_count=row.gift_count,
        envelope_numbers=row.envelope_numbers,
        note=row.note,
    )


def _single_expense_read(
    db: Session, event: models.Event, expense: models.EventExpense
) -> schemas.ExpenseRead:
    """שורה אחת, **מחושבת בהקשר של כל שורות האירוע.**

    לא ניתן לחשב שורה כספית בבידוד: שורת ``percent`` נגזרת מסך שאר
    השורות, ו-``cost_breakdown([expense])`` היה נותן לה בסיס ריק — כלומר
    0 ₪ בתשובת ה-POST/PUT, בזמן שהסיכום מציג את הערך הנכון. שני מספרים
    שונים לאותה שורה, משני נתיבים באותו API.

    לכן החישוב כאן עובר תמיד דרך כל ההוצאות, כמו בכל שאר הנתיבים.
    """
    guests = _guests(db, event.id)
    rows = finance_service.expenses_for(db, event.id)
    breakdown = finance.cost_breakdown(
        rows, finance.attendee_count(guests), finance.invited_count(guests)
    )
    return _expense_read(expense, breakdown.lines[expense.id], event.event_type)


def _rsvp_snapshot(guests: list[models.Guest]) -> schemas.RsvpSnapshotRead:
    """אותה ספירה בדיוק כמו ב-``routers/stats.py`` — ובכוונה.

    לא נספר כאן "מחדש בדרך שלנו": מסך כספי שמראה 421 מגיעים בזמן שתמונת
    המצב מראה 419 שובר את האמון בשני המסכים גם יחד.
    """
    return schemas.RsvpSnapshotRead(
        total_guests=len(guests),
        invited_people=finance.invited_count(guests),
        confirmed_guests=sum(1 for g in guests if g.rsvp_status == "confirmed"),
        confirmed_people=finance.attendee_count(guests),
        declined_guests=sum(1 for g in guests if g.rsvp_status == "declined"),
        pending_guests=sum(1 for g in guests if g.rsvp_status == "pending"),
        maybe_guests=sum(1 for g in guests if g.rsvp_status == "maybe"),
    )


# ════════════════════════════════════════════════════════════════════════
#  קטלוג
# ════════════════════════════════════════════════════════════════════════

@router.get("/categories", response_model=list[schemas.ExpenseCategoryRead])
def categories(event: models.Event = Depends(_access)):
    """קטלוג ההוצאות המותאם לסוג האירוע.

    מוגש מהשרת ולא משוכפל ל-TypeScript: מקור אחד לשני צרכנים (המסך
    והחישוב), ואין דרך שהם יסטו זה מזה.
    """
    return [
        schemas.ExpenseCategoryRead(
            key=c.key,
            label=c.label,
            items=[
                schemas.ExpenseItemRead(
                    key=i.key,
                    label=i.label,
                    calc_method=i.calc_method,
                    supports_commitment=i.supports_commitment,
                    default_quantity=i.default_quantity,
                    is_default=i.is_default,
                    sort_order=i.sort_order,
                )
                for i in c.items
            ],
        )
        for c in finance_categories.catalog_for(event.event_type)
    ]


# ════════════════════════════════════════════════════════════════════════
#  סיכום מלא — הקריאה שמזינה את כל המסך
# ════════════════════════════════════════════════════════════════════════

@router.get("", response_model=schemas.FinanceSummaryRead)
def summary(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """כל המסך בקריאה אחת — בדיוק כמו ``/stats`` לתמונת המצב.

    שלוש קריאות נפרדות היו מציגות שלושה חלקים שנטענים בזמנים שונים,
    ובמסך כספי זה נראה כמו מספרים שקופצים.
    """
    guests = _guests(db, event.id)
    expenses = finance_service.expenses_for(db, event.id)
    attendees = finance.attendee_count(guests)
    invited = finance.invited_count(guests)

    breakdown = finance.cost_breakdown(expenses, attendees, invited)
    credit_visible = finance_service.credit_amounts_visible(db, event)
    income = finance_service.gift_income(db, event, credit_visible=credit_visible)
    bottom = finance_service.bottom_line(breakdown, income)

    return schemas.FinanceSummaryRead(
        rsvp=_rsvp_snapshot(guests),
        cost=_cost_summary(expenses, attendees, invited),
        income=_income_read(income),
        breakdown=_breakdown_read(
            finance_service.gift_breakdown(db, event, credit_visible=credit_visible)
        ),
        counting_open=finance_service.counting_open(event),
        bottom_line_agorot=bottom,
        bottom_line_display=finance.format_shekels(bottom),
        expenses=[_expense_read(e, breakdown.lines[e.id], event.event_type) for e in expenses],
    )


@router.get("/report", response_model=schemas.FinanceReportRead)
def report(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """הדוח הסופי — **תמונה אחת מלאה של האירוע.**

    ## למה זה נתיב נפרד מ-``GET /finance``

    הסיכום השוטף נטען בכל כניסה למסך ומכיל עשרות שורות. הדוח מכיל **שורה
    לכל מוזמן** — מאות שורות באירוע טיפוסי — והוא נדרש פעם אחת, בסוף.
    לגרור אותו בכל טעינת מסך היה מאט את המסך בשביל נתון שאיש לא מסתכל
    עליו רוב הזמן.

    ## מה הדוח מבטיח

    1. **כל מוזמן מופיע**, כולל מי שלא הגיע וכולל מי שעדיין לא נספרה לו
       מתנה. הזוג לא צריך לחבר מידע משלושה מסכים.
    2. **הגעה ומתנה הם שתי עמודות נפרדות** שלא נגזרות זו מזו. מוזמן
       שביטל הגעה ונתן ₪1,000 מופיע בדיוק כך.
    3. **מעטפות שלא שויכו אינן נעלמות** — הן חוזרות ב-``unidentified``
       כדי שהסכום הכולל בדוח יסתדר עם הסכום שבמסך.
    4. **ייצוג אחד, שלושה פלטים.** אותו מבנה מזין את המסך, את הייצוא
       ל-Excel ואת גרסת ההדפסה/PDF — ולכן אין דרך שהם יסטו זה מזה.
    """
    from datetime import datetime

    guests = _guests(db, event.id)
    expenses = finance_service.expenses_for(db, event.id)
    attendees = finance.attendee_count(guests)
    invited = finance.invited_count(guests)

    cost = finance.cost_breakdown(expenses, attendees, invited)
    credit_visible = finance_service.credit_amounts_visible(db, event)
    income = finance_service.gift_income(db, event, credit_visible=credit_visible)
    rows = finance_service.guest_gift_rows(db, event, credit_visible=credit_visible)
    entries = finance_service.gift_entries(db, event, credit_visible=credit_visible)

    # דרך הלקסיקון: "החתונה של אביב ודנה" / "הברית של יונתן" — לא צירוף
    # שמות גולמי שהיה מייצר כותרת חתונתית לכל סוג אירוע.
    title = event_terms.event_display_title(
        event.event_type, event.groom_name, event.bride_name
    )

    return schemas.FinanceReportRead(
        event_title=title,
        event_date=event.event_date or "",
        venue_name=event.venue_name or "",
        generated_at=datetime.utcnow(),
        rsvp=_rsvp_snapshot(guests),
        cost=_cost_summary(expenses, attendees, invited),
        income=_income_read(income),
        breakdown=_breakdown_read(
            finance_service.gift_breakdown(db, event, credit_visible=credit_visible)
        ),
        bottom_line_agorot=finance_service.bottom_line(cost, income),
        bottom_line_display=finance.format_shekels(
            finance_service.bottom_line(cost, income)
        ),
        expenses=[_expense_read(e, cost.lines[e.id], event.event_type) for e in expenses],
        guests=[_guest_row_read(r) for r in rows],
        # רק מעטפות: עסקת אשראי תמיד משויכת למוזמן דרך הטוקן שלו, ולכן
        # לא קיימת "מתנה באשראי בלי שם".
        unidentified=[
            _entry_read(e) for e in entries if e.source == "envelope" and not e.guest_id
        ],
    )


# ════════════════════════════════════════════════════════════════════════
#  הוצאות
# ════════════════════════════════════════════════════════════════════════

def _apply_expense(payload: schemas.ExpenseWrite, expense: models.EventExpense) -> None:
    """כותב את הקלט לשורה, אחרי ניקוי שדות שאינם שייכים לשיטת החישוב.

    **ניקוי ולא התעלמות:** זוג ששינה שורה מ"לפי אורח" ל"סכום קבוע" חייב
    שכמות ההתחייבות תיעלם, ולא תישאר רדומה בשורה ותחזור לחיים בעריכה
    הבאה. שדה שאינו שייך לשיטה נמחק, נקודה.
    """
    expense.category = payload.category or "other"
    expense.item_key = payload.item_key
    expense.label = payload.label
    expense.calc_method = payload.calc_method
    expense.amount_agorot = payload.amount_agorot
    expense.note = (payload.note or "").strip() or None
    expense.vendor = (payload.vendor or "").strip()
    expense.is_estimated = payload.is_estimated
    expense.is_paid = payload.is_paid

    # ``quantity`` משרת שתי שיטות: יחידות ב-``per_unit``, ואחוזים
    # שלמים ב-``percent``. בכל שאר השיטות הוא נמחק.
    if payload.calc_method in (finance_categories.PER_UNIT, finance_categories.PERCENT):
        expense.quantity = payload.quantity
    else:
        expense.quantity = None
    if payload.calc_method == finance_categories.PER_ATTENDEE:
        expense.committed_quantity = payload.committed_quantity or None
    else:
        expense.committed_quantity = None
    # המינימום הכספי חל על כל שיטה — חוזה יכול לנקוב במינימום גם על
    # שורה קבועה או שורה לפי יחידה.
    expense.min_total_agorot = payload.min_total_agorot or None


@router.post("/expenses", response_model=schemas.ExpenseRead, status_code=201)
def create_expense(
    payload: schemas.ExpenseWrite,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    expense = models.EventExpense(
        event_id=event.id, sort_order=finance_service.next_sort_order(db, event.id)
    )
    _apply_expense(payload, expense)
    db.add(expense)
    db.flush()

    audit.record(
        db, "finance_expense_add",
        event_id=event.id, user_id=user.id,
        detail=f"נוספה הוצאה — {expense.label} ({finance.format_shekels(expense.amount_agorot)})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(expense)
    return _single_expense_read(db, event, expense)


@router.post("/template/apply", response_model=schemas.TemplateApplyResult)
def apply_template(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    """יוצר את שורות התבנית של סוג האירוע — **תקציב פתיחה, לא כלוב.**

    מסך ריק שמבקש מזוג להמציא את רשימת ההוצאות של אירוע הוא מסך שנשאר
    ריק. במקום זה, לחיצה אחת יוצרת את השורות שרוב האירועים מהסוג הזה
    כוללים, בסכום 0 ומסומנות כהערכה — מוכנות למילוי.

    **רק ``is_default``.** התבנית המלאה עשירה בהרבה (עשרות פריטים), אבל
    תקציב שנפתח עם 60 שורות הוא תקציב שסוגרים. השאר נשארים תחת "הוספת
    הוצאה".

    **לא דורס.** אירוע שכבר יש בו שורה אחת מקבל ``applied=False`` ולא
    משתנה כלל: התבנית היא נקודת פתיחה, ואין שום מצב שבו לחיצה כאן
    מוחקת עבודה קיימת.
    """
    existing = finance_service.expenses_for(db, event.id)
    if existing:
        guests = _guests(db, event.id)
        cost = finance.cost_breakdown(
            existing, finance.attendee_count(guests), finance.invited_count(guests)
        )
        return schemas.TemplateApplyResult(
            created=0,
            applied=False,
            expenses=[_expense_read(e, cost.lines[e.id], event.event_type) for e in existing],
        )

    created: list[models.EventExpense] = []
    for category_key, item in finance_categories.default_items_for(event.event_type):
        expense = models.EventExpense(
            event_id=event.id,
            category=category_key,
            item_key=item.key,
            label=item.label,
            calc_method=item.calc_method,
            # סכום 0: התבנית יודעת **מה** משלמים, לא **כמה**. מחיר משוער
            # שהמערכת תמציא הוא בדיוק המספר שזוג ייקח ברצינות בטעות.
            amount_agorot=0,
            quantity=item.default_quantity,
            is_estimated=True,
            is_paid=False,
            sort_order=item.sort_order,
        )
        db.add(expense)
        created.append(expense)
    db.flush()

    audit.record(
        db, "finance_template_apply",
        event_id=event.id, user_id=user.id,
        detail=f"נוצר תקציב פתיחה — {len(created)} שורות",
        ip=request.client.host if request.client else None,
    )
    db.commit()

    guests = _guests(db, event.id)
    rows = finance_service.expenses_for(db, event.id)
    cost = finance.cost_breakdown(
        rows, finance.attendee_count(guests), finance.invited_count(guests)
    )
    return schemas.TemplateApplyResult(
        created=len(created),
        applied=True,
        expenses=[_expense_read(e, cost.lines[e.id], event.event_type) for e in rows],
    )


def _owned_expense(db: Session, event: models.Event, expense_id: int) -> models.EventExpense:
    """שורה של **האירוע הזה** בלבד.

    בדיקת ה-``event_id`` כאן אינה כפילות של ה-RLS אלא השכבה השנייה שלו:
    בפיתוח מול SQLite אין RLS בכלל, ובלעדיה ``db.get`` לבדו היה מחזיר
    שורה של אירוע אחר למי שינחש מזהה.
    """
    expense = db.get(models.EventExpense, expense_id)
    if expense is None or expense.event_id != event.id:
        raise HTTPException(status_code=404, detail="ההוצאה לא נמצאה")
    return expense


@router.put("/expenses/{expense_id}", response_model=schemas.ExpenseRead)
def update_expense(
    expense_id: int,
    payload: schemas.ExpenseWrite,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    expense = _owned_expense(db, event, expense_id)
    _apply_expense(payload, expense)
    db.flush()

    audit.record(
        db, "finance_expense_update",
        event_id=event.id, user_id=user.id,
        detail=f"עודכנה הוצאה — {expense.label} ({finance.format_shekels(expense.amount_agorot)})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(expense)
    return _single_expense_read(db, event, expense)


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    expense = _owned_expense(db, event, expense_id)
    label = expense.label
    db.delete(expense)
    audit.record(
        db, "finance_expense_delete",
        event_id=event.id, user_id=user.id,
        detail=f"נמחקה הוצאה — {label}",
        ip=request.client.host if request.client else None,
    )
    db.commit()


# ════════════════════════════════════════════════════════════════════════
#  ספירת מתנות
# ════════════════════════════════════════════════════════════════════════

@router.get("/gifts", response_model=schemas.GiftCountingRead)
def gift_counting(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """מסך ספירת המתנות — מעטפות ואשראי יחד.

    **המסך מוחזר גם כשהספירה עדיין נעולה** (``counting_open=False``), עם
    ``days_until_open``. אין כאן שום מידע רגיש שנחשף מוקדם — רק מסך שאין
    בו טעם לפני האירוע — ו-404 היה מונע מהמסך להסביר לזוג *למה* הוא נעול
    ומתי ייפתח.
    """
    credit_visible = finance_service.credit_amounts_visible(db, event)
    days = guest_journey.days_until_event(event)

    return schemas.GiftCountingRead(
        counting_open=finance_service.counting_open(event),
        days_until_open=days if days is not None and days > 0 else None,
        credit_service_active=credit_visible,
        credit_amounts_visible=credit_visible,
        next_envelope_number=finance_service.next_envelope_number(db, event.id),
        income=_income_read(
            finance_service.gift_income(db, event, credit_visible=credit_visible)
        ),
        entries=[
            _entry_read(e)
            for e in finance_service.gift_entries(db, event, credit_visible=credit_visible)
        ],
    )


@router.get("/gifts/by-guest", response_model=list[schemas.GuestGiftRowRead])
def gifts_by_guest(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """מצב המתנה לכל מוזמן — **כולל מי שעדיין לא נספר**.

    מוזמן בלי מתנה מופיע כאן עם ``not_counted``, ולא נעדר מהרשימה. זו כל
    הנקודה של המסך: לראות מה נשאר לספור, ולא לנחש מי חסר. "עדיין לא
    נספרה" אינו "לא נתן", והמערכת לא תציג את השני במקום הראשון.
    """
    credit_visible = finance_service.credit_amounts_visible(db, event)
    return [
        _guest_row_read(row)
        for row in finance_service.guest_gift_rows(db, event, credit_visible=credit_visible)
    ]


def _validate_guest_links(
    db: Session, event: models.Event, payload: schemas.EnvelopeWrite
) -> list[int]:
    """מוודא ששיוכי המוזמנים שייכים לאירוע הזה, ומחזיר את הרשימה המנוקה.

    ``guest_id`` עצמו מסונן החוצה מ-``shared_guest_ids`` כדי שמוזמן לא
    ייספר פעמיים באותה מעטפה.
    """
    if payload.guest_id is not None:
        guest = db.get(models.Guest, payload.guest_id)
        if guest is None or guest.event_id != event.id:
            raise HTTPException(status_code=404, detail="המוזמן לא נמצא")

    shared: list[int] = []
    for gid in payload.shared_guest_ids:
        if gid == payload.guest_id or gid in shared:
            continue
        guest = db.get(models.Guest, gid)
        if guest is None or guest.event_id != event.id:
            raise HTTPException(status_code=404, detail="המוזמן לא נמצא")
        shared.append(gid)
    return shared


def _envelope_entry(
    db: Session, event_id: int, envelope: models.GiftEnvelope
) -> schemas.GiftEntryRead:
    names = {
        row[0]: row[1]
        for row in db.execute(
            select(models.Guest.id, models.Guest.full_name).where(
                models.Guest.event_id == event_id
            )
        ).all()
    }
    return _entry_read(
        finance_service.GiftEntry(
            source="envelope",
            id=envelope.id,
            amount_agorot=envelope.amount_agorot,
            guest_id=envelope.guest_id,
            guest_name=names.get(envelope.guest_id or -1, ""),
            envelope_number=envelope.envelope_number,
            note=envelope.note,
            created_at=envelope.created_at,
            shared_names=[
                names[g] for g in (envelope.shared_guest_ids or []) if g in names
            ],
        )
    )


@router.post("/envelopes", response_model=schemas.EnvelopeCreated, status_code=201)
def create_envelope(
    payload: schemas.EnvelopeWrite,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    """שמירת מעטפה, ומיד המספר של הבאה אחריה.

    **המספר הבא חוזר מהשרת** ולא נספר בדפדפן: זו הדרך היחידה ששני מכשירים
    שסופרים את אותה ערימה במקביל לא יקבלו את אותו מספר. אילוץ הייחודיות
    ב-DB (``uq_envelope_number``) הוא הרשת מתחת לזה.
    """
    shared = _validate_guest_links(db, event, payload)

    envelope = models.GiftEnvelope(
        event_id=event.id,
        envelope_number=finance_service.next_envelope_number(db, event.id),
        amount_agorot=payload.amount_agorot,
        guest_id=payload.guest_id,
        shared_guest_ids=shared or None,
        note=(payload.note or "").strip() or None,
        recorded_by_user_id=user.id,
    )
    db.add(envelope)
    db.flush()

    audit.record(
        db, "finance_envelope_add",
        event_id=event.id, user_id=user.id,
        detail=(
            f"נספרה מעטפה #{envelope.envelope_number} — "
            f"{finance.format_shekels(envelope.amount_agorot)}"
        ),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(envelope)

    return schemas.EnvelopeCreated(
        envelope=_envelope_entry(db, event.id, envelope),
        next_envelope_number=finance_service.next_envelope_number(db, event.id),
    )


def _owned_envelope(db: Session, event: models.Event, envelope_id: int) -> models.GiftEnvelope:
    envelope = db.get(models.GiftEnvelope, envelope_id)
    if envelope is None or envelope.event_id != event.id:
        raise HTTPException(status_code=404, detail="המעטפה לא נמצאה")
    return envelope


@router.put("/envelopes/{envelope_id}", response_model=schemas.GiftEntryRead)
def update_envelope(
    envelope_id: int,
    payload: schemas.EnvelopeWrite,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    """עריכת מעטפה — כולל שיוך מאוחר של מעטפה שלא זוהתה.

    ``envelope_number`` **אינו** משתנה כאן. המספר הוא העוגן שבו הזוג
    מזהה את המעטפה הפיזית בערימה; שינוי שלו בעריכה היה מנתק בין מה
    שכתוב על המעטפה למה שרשום במערכת.
    """
    envelope = _owned_envelope(db, event, envelope_id)
    shared = _validate_guest_links(db, event, payload)

    envelope.amount_agorot = payload.amount_agorot
    envelope.guest_id = payload.guest_id
    envelope.shared_guest_ids = shared or None
    envelope.note = (payload.note or "").strip() or None
    db.flush()

    audit.record(
        db, "finance_envelope_update",
        event_id=event.id, user_id=user.id,
        detail=(
            f"עודכנה מעטפה #{envelope.envelope_number} — "
            f"{finance.format_shekels(envelope.amount_agorot)}"
        ),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(envelope)
    return _envelope_entry(db, event.id, envelope)


@router.delete("/envelopes/{envelope_id}", status_code=204)
def delete_envelope(
    envelope_id: int,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_user),
):
    envelope = _owned_envelope(db, event, envelope_id)
    number = envelope.envelope_number
    amount = envelope.amount_agorot
    db.delete(envelope)
    audit.record(
        db, "finance_envelope_delete",
        event_id=event.id, user_id=user.id,
        detail=f"נמחקה מעטפה #{number} — {finance.format_shekels(amount)}",
        ip=request.client.host if request.client else None,
    )
    db.commit()
