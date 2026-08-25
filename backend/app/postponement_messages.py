"""נוסחי הודעת "אירוע נדחה" — הטקסטים שהבעלים כתב, מילה במילה.

**מקור אמת יחיד לתוכן הזה.** הטקסטים כאן הועתקו בדיוק כפי שנשלחו: אותן
מילים, אותו סדר שורות, אותם אמוג'י. לא נוסחו מחדש, לא קוצרו ולא "שופרו".
כל שינוי בהם הוא החלטה של הבעלים בלבד.

## למה זריעה בקוד ולא הזנה ידנית במסך האדמין

``seed_message_default_options`` (main.py) רץ **רק כשהטבלה ריקה**, ולכן
בייצור — שבו כבר יש 72 נוסחי חתונה — הוא לא יוסיף כאן דבר. בלי הזריעה
הזו, הדרך היחידה להכניס את הנוסחים לייצור היא הקלדה ידנית במסך האדמין,
אחד-אחד. זה בדיוק הפער שתועד ב-``decisions.md`` (2026-08-10): תוכן שהוזן
רק בסביבה המקומית ומעולם לא הגיע לייצור.

## שני כללי בטיחות

1. **לעולם לא דורס.** שורה שכבר קיימת לאותו ``event_type`` × ``message_type``
   × ``option_number`` נשארת כפי שהיא — כולל אם הבעלים ערך אותה במסך
   האדמין. הזריעה משלימה חסר, לא מיישרת בכוח.
2. **לא מוחקת דבר.** אין כאן ``DELETE``.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import communication, models

#: המשתנים שהנוסחים כאן משתמשים בהם בפועל. תת-קבוצה של
#: ``DEFAULT_VARIABLES_SUPPORTED[POSTPONEMENT]`` — ראו שם למה אין
#: ``event_date`` ואין ``rsvp_link`` בהודעת דחייה.
VARIABLES = ["guest_name", "event_type", "host_names"]

#: לאילו סוגי אירוע נזרעים הנוסחים.
#:
#: **כל הסוגים, ולא חתונה בלבד** — בשונה מזריעת ההזמנות ההיסטורית. הנוסחים
#: האלה נכתבו מלכתחילה בלי מילה אחת שקשורה לחתונה: הם מדברים על
#: ``{{event_type}}`` ועל ``{{host_names}}``, ומנוע המונחים ממלא את השאר.
#: אירוע שנדחה הוא אירוע שנדחה, בכל סוג.
EVENT_TYPES = [
    "wedding", "bar_mitzvah", "bat_mitzvah", "henna",
    "brit", "brita", "family", "business", "other",
]

#: חמשת הנוסחים, בסדר שבו נשלחו.
#:
#: ``title`` ו-``tone`` הם **תוויות בחירה**, לא תוכן — הם עוזרים לזוג לזהות
#: מהר איזה נוסח מתאים לו בלי לקרוא את חמשתם במלואם. הם נגזרו מהנוסחים
#: עצמם ואינם חלק מהטקסט שנשלח לאורחים.
OPTIONS: list[dict] = [
    {
        "option_number": 1,
        "title": "אישי — עם התנצלות",
        "tone": "חם ואישי",
        "content": (
            "שלום {{guest_name}} ❤️\n"
            "\n"
            "עדכון חשוב — {{event_type}} שלנו נדחה.\n"
            "אנחנו מצטערים מאוד על השינוי ועל אי-הנוחות שנגרמה, ומודים לך מכל הלב על ההבנה, האהבה והתמיכה.\n"
            "אנחנו עובדים על מועד חדש ונעדכן אותך ברגע שיהיה תאריך סופי.\n"
            "אוהבים ומקווים לחגוג איתך בקרוב ❤️\n"
            "{{host_names}}\n"
            "נתראה בשמחות."
        ),
    },
    {
        "option_number": 2,
        "title": "קצר",
        "tone": "תמציתי וחם",
        "content": (
            "שלום {{guest_name}} ❤️\n"
            "\n"
            "רצינו לעדכן אותך ש{{event_type}} שלנו נדחה.\n"
            "אנחנו עדיין עובדים על מועד חדש, וכמובן שנעדכן אותך ברגע שיהיה תאריך סופי.\n"
            "תודה לך על ההבנה, האהבה והתמיכה בתקופה הזו ❤️\n"
            "אוהבים,\n"
            "{{host_names}}\n"
            "נתראה בשמחות."
        ),
    },
    {
        "option_number": 3,
        "title": "אישי — מורחב",
        "tone": "אישי ומפורט",
        "content": (
            "שלום {{guest_name}} ❤️\n"
            "\n"
            "לצערנו, {{event_type}} שלנו נדחה.\n"
            "זה לא היה שינוי שרצינו בו, ואנחנו מצטערים מאוד על אי-הנוחות שנגרמה לך.\n"
            "כרגע אנחנו עדיין עובדים על מועד חדש, וברגע שיהיה לנו תאריך סופי — נעדכן אותך.\n"
            "תודה על ההבנה, הסבלנות, האהבה והתמיכה ❤️\n"
            "מחכים כבר לרגע שנוכל לחגוג איתך כמו שחלמנו.\n"
            "{{host_names}}\n"
            "נתראה בשמחות."
        ),
    },
    {
        "option_number": 4,
        "title": "עדיין אין תאריך חדש",
        "tone": "פתוח וכן",
        "content": (
            "שלום {{guest_name}} ❤️\n"
            "\n"
            "רצינו לעדכן אותך ש{{event_type}} שלנו נדחה.\n"
            "אנחנו עדיין לא יודעים מה יהיה התאריך החדש, אבל עובדים על זה ונעדכן אותך ברגע שנדע.\n"
            "מצטערים על השינוי ומודים לך מאוד על ההבנה והאהבה ❤️\n"
            "אוהבים,\n"
            "{{host_names}}\n"
            "נתראה בשמחות!"
        ),
    },
    {
        "option_number": 5,
        "title": "רשמי",
        "tone": "מכובד ומאופק",
        "content": (
            "שלום {{guest_name}},\n"
            "\n"
            "רצינו לעדכן אותך כי {{event_type}} שלנו נדחה.\n"
            "אנו מצטערים על השינוי ועל אי-הנוחות שעלולה להיגרם לך בעקבותיו.\n"
            "אנו פועלים לקביעת מועד חדש ונעדכן אותך ברגע שהתאריך יהיה סופי.\n"
            "תודה רבה על ההבנה, הסבלנות והתמיכה ❤️\n"
            "{{host_names}}\n"
            "נתראה בשמחות."
        ),
    },
]


def seed_postponement_options(db: Session) -> int:
    """משלים את נוסחי הדחייה החסרים. מחזיר כמה שורות נוצרו.

    idempotent ולא-דורס: מריצים בכל עלייה, וברגע שהשורות קיימות זה no-op.
    """
    existing = {
        (event_type, number)
        for event_type, number in db.execute(
            select(
                models.MessageDefaultOption.event_type,
                models.MessageDefaultOption.option_number,
            ).where(
                models.MessageDefaultOption.message_type == communication.POSTPONEMENT
            )
        ).all()
    }

    created = 0
    for event_type in EVENT_TYPES:
        for option in OPTIONS:
            if (event_type, option["option_number"]) in existing:
                continue
            db.add(models.MessageDefaultOption(
                event_type=event_type,
                message_type=communication.POSTPONEMENT,
                option_number=option["option_number"],
                tone=option["tone"],
                title=option["title"],
                content=option["content"],
                variables_supported=list(VARIABLES),
                is_active=True,
            ))
            created += 1
    if created:
        db.flush()
    return created
