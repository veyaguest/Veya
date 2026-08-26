"""כניסה לסביבת פיתוח בלבד — יוצר/מרענן משתמש בדיקה מאומת ומדפיס טוקן.

⚠️ הסקריפט הזה **אינו** חלק מהאפליקציה: הוא לא רשום כ-router, אין לו endpoint,
ואי אפשר להגיע אליו מהרשת. הוא רץ ידנית מהטרמינל של מכונת הפיתוח בלבד.
לכן הוא אינו "backdoor" — הוא לא מוסיף שום מסלול כניסה למערכת הפרוסה.

שלוש שכבות הגנה, כולן חייבות להתקיים:
  1. ``VEYA_ENV`` אינו ``production``.
  2. ``VEYA_DEV_LOGIN=1`` מוגדר במפורש בסביבת ההרצה.
  3. ``DATABASE_URL`` מצביע על SQLite מקומי או על localhost — לא על DB מרוחק.

מה הוא עושה:
  * יוצר (או מוצא) משתמש ``VEYA_DEV_LOGIN_EMAIL`` (ברירת מחדל dev@veya.local),
    מסומן כמאומת, עם סיסמה אקראית שנוצרת בזמן ריצה — אין שום credential
    קשיח בקוד.
  * מזרים לו אירוע חתונה לדוגמה עם רשימת מוזמנים מגוונת, כדי שאפשר יהיה
    לבדוק ויזואלית מסכים עם נתונים אמיתיים (טבלאות, גרפים, הושבה).
  * מדפיס טוקן JWT + פקודת localStorage להדבקה ב-DevTools.

הרצה:
    VEYA_DEV_LOGIN=1 python scripts/dev_login.py
"""
from __future__ import annotations

import os
import random
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# ── שכבות ההגנה ────────────────────────────────────────────────────────────
def _refuse(reason: str) -> None:
    print(f"\n✋ dev_login נעצר: {reason}\n", file=sys.stderr)
    raise SystemExit(2)


if os.getenv("VEYA_ENV", "").strip().lower() == "production":
    _refuse("VEYA_ENV=production — הסקריפט הזה אסור בייצור.")

if os.getenv("VEYA_DEV_LOGIN", "").strip() != "1":
    _refuse(
        "חסר VEYA_DEV_LOGIN=1. זו הפעלה מכוונת בלבד:\n"
        "    VEYA_DEV_LOGIN=1 python scripts/dev_login.py"
    )

_db_url = (os.getenv("DATABASE_URL", "") or "").strip()
_is_local = (
    _db_url == ""
    or _db_url.startswith("sqlite")
    or "localhost" in _db_url
    or "127.0.0.1" in _db_url
)
if not _is_local:
    _refuse(
        "DATABASE_URL מצביע על מסד נתונים מרוחק. הסקריפט רץ רק מול DB מקומי "
        "(sqlite/localhost) כדי שלא ייגע בנתוני אמת."
    )

from app import auth, legal, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

DEV_EMAIL = (os.getenv("VEYA_DEV_LOGIN_EMAIL", "dev@veya.local") or "").strip().lower()

# ── נתוני הדגמה ────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "נועה", "איתי", "שירה", "יונתן", "תמר", "עומר", "מאיה", "אורי", "יעל", "דניאל",
    "אביגיל", "רועי", "הילה", "אלון", "טליה", "גיא", "ליאור", "עדי", "רון", "מיכל",
    "אסף", "נטע", "יובל", "שקד", "אמיר", "רותם", "בר", "אלה", "עידו", "כרמל",
]
SURNAMES = [
    "לוי", "כהן", "מזרחי", "פרץ", "ביטון", "אברהם", "פרידמן", "שפירא", "גולן",
    "אזולאי", "בן־דוד", "רוזן", "הראל", "ברקוביץ",
]
GROUPS = ["family", "friends", "work", "army", "other"]
SIDES = ["groom", "bride", "shared"]
GIFT_NAMES = [
    "משפחת כהן", "נועה ואיתי", "דוד ורחל לוי", "צוות המשרד", "שירה מזרחי",
    "משפחת פרץ", "יונתן וטליה", "סבתא אסתר", "חברים מהצבא", "רון ואלה",
]
GIFT_BLESSINGS = [
    "מזל טוב! שיהיה בשעה טובה ומוצלחת",
    "אוהבים אתכם, מחכים לחגוג",
    "כל הכבוד, מאחלים לכם המון אושר",
    "",
    "בהצלחה בדרך החדשה שלכם",
    "",
]

NOTE_POOL = [
    "לשבת ליד משפחת כהן",
    "עדיף לא ליד השולחן של הרמקולים",
    "מגיעים עם תינוק — צריך מקום לעגלה",
    "צמחונית",
    "לשבת עם החברים מהצבא",
    "",
    "",
    "",
]


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == DEV_EMAIL).one_or_none()
        created = False
        if user is None:
            # סיסמה אקראית שנוצרת עכשיו — לא שמורה בקוד ולא ניתנת לניחוש.
            password = secrets.token_urlsafe(18)
            user = models.User(
                email=DEV_EMAIL,
                password_hash=auth.hash_password(password),
                display_name="משתמש פיתוח",
                phone="0500000000",
                # לא אדמין: המטרה היא לראות את המערכת בדיוק כמו זוג אמיתי.
                # למי שצריך את פאנל האדמין — VEYA_DEV_LOGIN_ADMIN=1.
                is_admin=os.getenv("VEYA_DEV_LOGIN_ADMIN", "").strip() == "1",
                account_type="couple",
                email_verified_at=datetime.utcnow(),
                token_version=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            created = True
            print(f"\n🔑 נוצרה סיסמה אקראית למשתמש הפיתוח (שמור אם תרצה): {password}")
        elif user.email_verified_at is None:
            user.email_verified_at = datetime.utcnow()
            db.commit()

        # רישום הסכמות למסמכים המשפטיים בגרסה הנוכחית — כדי שמסך הפיתוח לא
        # ייחסם ע"י מודל ה-Reconsent. אותה פונקציה שמשמשת בהרשמה רגילה.
        for consent_type in legal.REQUIRED_CONSENT_TYPES:
            legal.record_consent(
                db, user_id=user.id, consent_type=consent_type, source="dev_login"
            )
        db.commit()

        event = (
            db.query(models.Event)
            .filter(models.Event.owner_id == user.id)
            .order_by(models.Event.id.desc())
            .first()
        )
        if event is None:
            event = models.Event(
                owner_id=user.id,
                event_type="wedding",
                groom_name="דניאל",
                bride_name="שירה",
                groom_parents_line="משפחת לוי",
                bride_parents_line="משפחת כהן",
                venue_name="אחוזת הדקלים",
                venue_address="דרך השדות 12, כפר סבא",
                event_date=(date.today() + timedelta(days=84)).isoformat(),
                event_time="19:30",
                seats_per_table=12,
                reserve_seats=6,
                rsvp_send_time="16:00",
                thank_you_send_time="11:00",
                rsvp_track_active=True,
                rsvp_track_started_at=datetime.utcnow() - timedelta(days=9),
            )
            db.add(event)
            db.commit()
            db.refresh(event)

        existing = db.query(models.Guest).filter(models.Guest.event_id == event.id).count()
        if existing < 40:
            rng = random.Random(20261119)  # זרע קבוע → אותה רשימה בכל הרצה
            statuses = (
                ["confirmed"] * 74 + ["pending"] * 38 + ["declined"] * 14 + ["maybe"] * 9
            )
            rng.shuffle(statuses)
            used_phones: set[str] = set()
            for i, st in enumerate(statuses):
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
                while True:
                    phone = "05" + str(rng.randint(10_000_000, 89_999_999))
                    if phone not in used_phones:
                        used_phones.add(phone)
                        break
                party = rng.choice([1, 1, 2, 2, 2, 3, 4])
                note = rng.choice(NOTE_POOL)
                db.add(
                    models.Guest(
                        event_id=event.id,
                        full_name=name,
                        phone=phone,
                        side=rng.choice(SIDES),
                        group_type=rng.choice(GROUPS),
                        party_size=party,
                        rsvp_status=st,
                        confirmed_count=party if st == "confirmed" else None,
                        seating_notes=note or None,
                        is_child=rng.random() < 0.08,
                        guest_token=secrets.token_urlsafe(16),
                        table_number=(i % 11) + 1 if st == "confirmed" else None,
                    )
                )
            db.commit()

        # ---- חשבון קבלת מתנות מאומת ----
        # השרת מסתיר סכומי מתנות כל עוד החשבון לא עבר את שתי הבדיקות
        # (ראו decisions.md 2026-08-25), ולכן בלי זה אי אפשר לראות בכלל
        # את מצב "הסכומים גלויים" של המסך. VEYA_DEV_PAYOUT_VERIFIED=1
        # מדלג על תהליך האישור **במסד המקומי בלבד** — לא בקוד ולא בייצור.
        if os.getenv("VEYA_DEV_PAYOUT_VERIFIED", "").strip() == "1":
            pa = (
                db.query(models.PayoutAccount)
                .filter(models.PayoutAccount.event_id == event.id)
                .one_or_none()
            )
            if pa is None:
                pa = models.PayoutAccount(
                    event_id=event.id,
                    bank_code=12,
                    branch_number="661",
                    account_number="4041288",
                )
                db.add(pa)
            pa.status = "verified"
            pa.provider_status = "approved"
            pa.submitted_at = datetime.utcnow() - timedelta(days=6)
            pa.status_changed_at = datetime.utcnow() - timedelta(days=4)
            db.commit()

        # ---- מתנות באשראי ----
        # נזרעות רק כשהמתג המתועד VEYA_GIFT_ENABLED דלוק, כלומר רק כשמישהו
        # באמת עובד על המסך הזה. אלה נתוני פיתוח מקומיים בלבד.
        if os.getenv("VEYA_GIFT_ENABLED", "").strip() == "1":
            have = db.query(models.Gift).filter(models.Gift.event_id == event.id).count()
            if have == 0:
                grng = random.Random(770425)
                guest_ids = [
                    g.id
                    for g in db.query(models.Guest)
                    .filter(models.Guest.event_id == event.id)
                    .limit(40)
                    .all()
                ]
                statuses = ["paid"] * 9 + ["pending"] * 2 + ["failed"] + ["refunded"]
                for i, st in enumerate(statuses):
                    amount = grng.choice([20000, 30000, 40000, 50000, 75000, 100000])
                    fee = round(amount * 0.019) + 150
                    db.add(
                        models.Gift(
                            event_id=event.id,
                            guest_id=guest_ids[i % len(guest_ids)] if guest_ids else None,
                            gift_amount_agorot=amount,
                            fee_agorot=fee,
                            total_agorot=amount + fee,
                            currency="ILS",
                            status=st,
                            provider="mock",
                            provider_transaction_id=f"dev_{i:03d}",
                            idempotency_key=secrets.token_urlsafe(12),
                            sender_name=GIFT_NAMES[i % len(GIFT_NAMES)],
                            message=grng.choice(GIFT_BLESSINGS) or None,
                            created_at=datetime.utcnow() - timedelta(days=grng.randint(0, 14)),
                        )
                    )
                db.commit()

        token = auth.create_access_token(user)
        guests = db.query(models.Guest).filter(models.Guest.event_id == event.id).count()
        gifts = db.query(models.Gift).filter(models.Gift.event_id == event.id).count()

        print("\n" + "=" * 68)
        print("  VEYA — כניסת פיתוח (development only)")
        print("=" * 68)
        print(f"  משתמש : {user.email} (id={user.id}, {'חדש' if created else 'קיים'})")
        print(f"  אירוע : {event.groom_name} ו{event.bride_name} (id={event.id})")
        print(f"  מוזמנים: {guests}")
        if gifts:
            print(f"  מתנות : {gifts}")
        print("-" * 68)
        print("  הדבק ב-DevTools Console של האפליקציה, ואז רענן:\n")
        print(
            f"localStorage.setItem('veya_token','{token}');"
            f"localStorage.setItem('veya_event_id','{event.id}');"
            f"localStorage.setItem('veya_event_type','{event.event_type}');"
            "location.reload()"
        )
        print("=" * 68 + "\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
