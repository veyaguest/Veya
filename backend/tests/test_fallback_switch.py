"""בודקת את חיבור ה-fallback ל-``default_template_for(event_type)`` (סבב 3ט, קומיט 3).

מטרות:
(הבדיקות של נוסחי ברירת המחדל לפי סוג אירוע הוסרו יחד עם ``message_library``,
5/8/2026 — היום הנוסחים חיים בהודעות המסלול, ``communication.py``.)
3. **תבניות שמורות של משתמשים לא משתנות** — fallback רק כש-NULL, אז שמור != NULL
   ממשיך לרוץ כרגיל.
4. **אין טוקנים לא-מוחלפים** — לא ``[...]`` ולא ``{...}`` נותרים בפלט.
5. **שדות ריקים לא שוברים תבניות library** — smart-line-drop בפעולה.

הבדיקות מדמות את שלוש נקודות ה-fallback (send_invitations, send_reminders,
preview) על-ידי הרצת אותה חתימה של ``render_automation_template`` שהן קוראות.

הרצה: ``python tests/test_fallback_switch.py``
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import messaging  # noqa: E402


# פרמטרים מלאים מדמים אירוע אמיתי מוגדר לגמרי
FULL_KWARGS = dict(
    guest_name="דני כהן",
    groom="יונתן",
    bride="נועה",
    venue="אולמי הגן",
    venue_address="הרצל 5, תל אביב",
    link="https://veya.co.il/confirm/abc",
    date="12.9.2026",
    time="19:30",
)


def _no_leftover_tokens(text: str) -> bool:
    return re.search(r"\{[^{}]*\}", text) is None and re.search(r"\[[^\[\]]*\]", text) is None


def _simulate_send(event_type: str, saved_template: str | None = None, **overrides) -> str:
    """מדמה את שרשרת ה-fallback ב-routers/messaging.py: send_invitations.

    ``saved_template=None`` מדמה ``event.message_template=NULL`` (fallback פועל).
    """
    kwargs = {**FULL_KWARGS, **overrides}
    template = saved_template or messaging.default_template_for(event_type)
    return messaging.render_automation_template(template, event_type=event_type, **kwargs)

def test_wedding_saved_old_syntax_template_unchanged():
    """חתונה עם תבנית שמורה בסינטקס ישן: לא משתנה — fallback לא מופעל."""
    saved = "היי {name}!\n{event_name} מזמינים ל{{celebration}}. אישור: {personal_link}"
    baseline = messaging.render_automation_template(
        saved, event_type="wedding", **FULL_KWARGS
    )
    via_fallback = _simulate_send("wedding", saved_template=saved)
    assert baseline == via_fallback
    assert _no_leftover_tokens(via_fallback)
    print(f"✓ חתונה + תבנית שמורה: לא מושפעת מהחלפת ה-fallback ({len(via_fallback)} chars)")

def test_bar_mitzvah_single_host_names_no_orphan_vav():
    """בר מצווה עם bride ריק: אין ' ו' יתום ליד שם החוגג."""
    out = _simulate_send("bar_mitzvah", bride="")
    assert "יונתן ו " not in out, f"יש ' ו ' יתום: {out!r}"
    assert "יונתן ו\n" not in out, f"' ו' לפני שורה חדשה: {out!r}"
    assert "יונתן ו." not in out, f"' ו.' יתום: {out!r}"
    assert not out.rstrip().endswith("ו"), f"מסתיים ב-'ו' יתום: {out!r}"
    # וגם שם החוגג צריך להופיע איפשהו
    assert "יונתן" in out, f"שם החוגג לא מופיע: {out!r}"
    print("✓ בר מצווה (חוגג יחיד): שם מופיע, ללא ' ו' יתום")

def test_brit_single_host_names_no_orphan_vav():
    """ברית עם bride ריק: אין ' ו' יתום."""
    out = _simulate_send("brit", bride="")
    assert "יונתן ו " not in out and "יונתן ו\n" not in out
    assert not out.rstrip().endswith("ו")
    print("✓ ברית (חוגג יחיד): ללא ' ו' יתום")

def test_wedding_two_hosts_names_joined_correctly():
    """חתונה עם שני שמות: 'יונתן ונועה' עם ו' חיבור."""
    out = _simulate_send("wedding")
    assert "יונתן ונועה" in out, f"שמות זוג לא הופיעו: {out!r}"
    print("✓ חתונה: שני השמות מחוברים כראוי ('יונתן ונועה')")

def test_henna_two_hosts_names_joined_correctly():
    """חינה: גם היא זוגית, שמות מחוברים."""
    out = _simulate_send("henna")
    assert "יונתן ונועה" in out, f"שמות זוג לא הופיעו בחינה: {out!r}"
    print("✓ חינה: שני השמות מחוברים כראוי")

def test_empty_time_smart_line_drop():
    """אירוע בלי event_time: השורה עם '[שעה]' נופלת בשקט אם היא היחידה עם טוקן.

    בפועל, בתבניות library שורת "📅 [תאריך] בשעה [שעה]" מכילה שני טוקנים.
    אם [תאריך] מלא ו-[שעה] ריק, השורה נשארת עם 'בשעה ' — לא רצוי אבל לא שובר.
    בדיקה זו מוודאת ש-רק זה עלול לקרות, ולא רגרסיה של טוקן שנשאר לא-מוחלף.
    """
    out = _simulate_send("bar_mitzvah", time="")
    assert _no_leftover_tokens(out), f"טוקן לא הוחלף אחרי time=='': {out!r}"
    # לא מבטיחים שהפלט "יפה" (זה שיפור עתידי) — רק ש-אין טוקן שבור
    print("✓ time ריק: אין טוקן לא-מוחלף (טקסט יכול להיראות פחות יפה, לא שובר)")


if __name__ == "__main__":
    test_wedding_saved_old_syntax_template_unchanged()
    test_bar_mitzvah_single_host_names_no_orphan_vav()
    test_brit_single_host_names_no_orphan_vav()
    test_wedding_two_hosts_names_joined_correctly()
    test_henna_two_hosts_names_joined_correctly()
    test_empty_time_smart_line_drop()
    print("\nכל הבדיקות עברו ✓")
