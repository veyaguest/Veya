"""שליחת מיילים מהשרת דרך Resend — שירות אחד לכל המיילים של VEYA.

למה קובץ נפרד: כל התלות בספק המייל מרוכזת כאן, בדיוק כמו ש-``messaging.py``
מרכז את התלות ב-WhatsApp. אם נחליף ספק בעתיד, זה הקובץ היחיד שמשתנה.

מצבי עבודה (``RESEND_API_KEY``):
- אין מפתח → מצב ``mock``: המייל לא נשלח באמת, רק נרשם ללוג. כך אפשר לפתח
  ולבדוק את כל הזרימה בלי חשבון Resend ובלי עלות (אותו עיקרון כמו WhatsApp).
- יש מפתח → מצב ``live``: שליחה אמיתית דרך ה-API של Resend.

אבטחה: המפתח נקרא ממשתנה סביבה בצד השרת בלבד ולעולם לא נחשף ל-Frontend.
"""
from __future__ import annotations

import html
import os
from dataclasses import dataclass

# ── הגדרות סביבה ────────────────────────────────────────────────────────────
RESEND_API_URL = "https://api.resend.com/emails"


def api_key() -> str:
    return os.getenv("RESEND_API_KEY", "").strip()


def current_mode() -> str:
    """``live`` אם יש מפתח Resend, אחרת ``mock`` (ברירת מחדל בטוחה)."""
    return "live" if api_key() else "mock"


def from_address() -> str:
    """כתובת השולח — חייבת להיות בדומיין מאומת ב-Resend."""
    return os.getenv("RESEND_FROM", "VEYA <invite@veya.co.il>")


def public_base_url() -> str:
    """כתובת הבסיס של האפליקציה — לבניית קישורים במיילים."""
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")


@dataclass
class SendResult:
    """תוצאת שליחה — ``ok`` מציין הצלחה, ``error`` מכיל סיבה כשנכשל."""

    ok: bool
    mode: str
    provider_id: str = ""
    error: str = ""


def send_email(*, to: str, subject: str, html_body: str, text_body: str = "") -> SendResult:
    """שולח מייל בודד. לעולם לא זורק חריגה — מחזיר ``SendResult``.

    הקורא מחליט מה לעשות בכישלון. במקרה של הזמנת בן/בת זוג אנחנו לא מפילים את
    הבקשה: ההזמנה כבר נשמרה ב-DB ואפשר לשלוח אותה שוב, אז עדיף להחזיר
    "נשמר אבל המייל לא יצא" מאשר לאבד את ההזמנה.
    """
    mode = current_mode()
    if mode == "mock":
        print(f"[emailer:mock] אל: {to} | נושא: {subject}")
        return SendResult(ok=True, mode="mock", provider_id="mock")

    try:
        import httpx  # נטען רק כשצריך — לא נדרש במצב mock

        response = httpx.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_address(),
                "to": [to],
                "subject": subject,
                "html": html_body,
                **({"text": text_body} if text_body else {}),
            },
            timeout=15.0,
        )
        if response.status_code >= 400:
            return SendResult(
                ok=False, mode="live", error=f"Resend {response.status_code}: {response.text[:200]}"
            )
        provider_id = ""
        try:
            provider_id = str(response.json().get("id", ""))
        except Exception:
            pass
        return SendResult(ok=True, mode="live", provider_id=provider_id)
    except Exception as exc:  # רשת/תצורה — לא מפילים את הבקשה של המשתמש
        return SendResult(ok=False, mode="live", error=str(exc)[:200])


# ── תבנית עיצוב משותפת ──────────────────────────────────────────────────────
# עיצוב inline בלבד: לקוחות מייל (בעיקר Gmail ו-Outlook) מתעלמים מ-<style>
# חיצוני ומ-classes, ולכן כל כלל CSS חייב לשבת על האלמנט עצמו. הפריסה בנויה
# על טבלאות מאותה סיבה — זה מה שנשאר responsive בכל לקוח מייל.
_BRAND_INK = "#1c1917"
_BRAND_MUTED = "#6b6560"
_BRAND_LINE = "#e7e3de"
_BRAND_BG = "#faf8f6"


def _shell(*, title: str, body_html: str) -> str:
    """מעטפת המייל: רקע בהיר, כרטיס לבן ממורכז, לוגו VEYA, כיוון RTL."""
    return f"""<!doctype html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:{_BRAND_BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{_BRAND_BG};padding:32px 12px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="max-width:520px;background:#ffffff;border:1px solid {_BRAND_LINE};
                    border-radius:18px;overflow:hidden;">
        <tr>
          <td style="padding:28px 32px 0 32px;text-align:center;">
            <span style="display:inline-block;font:700 20px/1 -apple-system,'Segoe UI',Arial,sans-serif;
                         letter-spacing:.14em;color:{_BRAND_INK};">VEYA</span>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 32px 32px;font-family:-apple-system,'Segoe UI',Arial,sans-serif;
                     color:{_BRAND_INK};text-align:right;direction:rtl;">
            {body_html}
          </td>
        </tr>
      </table>
      <div style="max-width:520px;margin:16px auto 0;font:400 12px/1.6 -apple-system,'Segoe UI',Arial,sans-serif;
                  color:{_BRAND_MUTED};text-align:center;direction:rtl;">
        נשלח מ-VEYA · הדרך הפשוטה לארגן אירוע
      </div>
    </td>
  </tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    """כפתור ראשי — <a> מעוצב (לקוחות מייל לא מריצים JS ולא תומכים ב-<button>)."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:24px auto 8px;"><tr><td align="center" '
        f'style="background:{_BRAND_INK};border-radius:999px;">'
        f'<a href="{html.escape(url, quote=True)}" '
        f'style="display:inline-block;padding:13px 34px;color:#ffffff;text-decoration:none;'
        f'font:600 15px/1 -apple-system,\'Segoe UI\',Arial,sans-serif;">'
        f"{html.escape(label)}</a></td></tr></table>"
    )


def _fallback_link(url: str) -> str:
    """הקישור המלא כטקסט — לכל מי שהכפתור לא עובד אצלו בלקוח המייל."""
    safe = html.escape(url)
    return (
        f'<p style="margin:16px 0 0;font:400 12px/1.7 -apple-system,\'Segoe UI\',Arial,sans-serif;'
        f'color:{_BRAND_MUTED};direction:ltr;text-align:left;word-break:break-all;">{safe}</p>'
    )


# ── מייל 1: הזמנת בן/בת זוג לניהול משותף ────────────────────────────────────
def send_partner_invite(
    *, to: str, inviter_name: str, event_title: str, invite_url: str
) -> SendResult:
    """מייל ההזמנה לניהול משותף של האירוע."""
    inviter = inviter_name.strip() or "בן/בת הזוג שלך"
    subject = f"{inviter} הזמין אותך לנהל יחד את האירוע שלכם ב-VEYA 💍"
    title_line = f"{html.escape(inviter)} הזמין אותך לנהל יחד את האירוע שלכם"
    event_line = (
        f'<p style="margin:0 0 20px;font:600 16px/1.5 -apple-system,\'Segoe UI\',Arial,sans-serif;'
        f'color:{_BRAND_INK};">{html.escape(event_title)}</p>'
        if event_title
        else ""
    )
    body = f"""
<h1 style="margin:0 0 10px;font:700 22px/1.4 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_INK};">
  {title_line}
</h1>
{event_line}
<p style="margin:0;font:400 15px/1.75 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_MUTED};">
  ב-VEYA תוכלו לנהל יחד את המוזמנים, אישורי ההגעה, סידור ההושבה וכל פרטי האירוע —
  שניכם רואים את אותו מידע, בזמן אמת.
</p>
{_button(invite_url, "הצטרפות לאירוע")}
{_fallback_link(invite_url)}
<p style="margin:24px 0 0;padding-top:16px;border-top:1px solid {_BRAND_LINE};
          font:400 13px/1.7 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_MUTED};">
  אם לא ציפיתם להזמנה הזו, אפשר פשוט להתעלם מהמייל.
</p>
"""
    text = (
        f"{inviter} הזמין אותך לנהל יחד את האירוע שלכם ב-VEYA.\n"
        f"{event_title}\n\nלהצטרפות: {invite_url}\n\n"
        "אם לא ציפיתם להזמנה הזו, אפשר להתעלם מהמייל."
    )
    return send_email(to=to, subject=subject, html_body=_shell(title=subject, body_html=body), text_body=text)


# ── מייל 2: אימות כתובת המייל ───────────────────────────────────────────────
def send_email_verification(*, to: str, verify_url: str) -> SendResult:
    """מייל אימות כתובת המייל אחרי הרשמה."""
    subject = "אימות כתובת המייל שלך ב-VEYA"
    body = f"""
<h1 style="margin:0 0 10px;font:700 22px/1.4 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_INK};">
  עוד צעד אחד ואתם בפנים
</h1>
<p style="margin:0;font:400 15px/1.75 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_MUTED};">
  לחצו על הכפתור כדי לאמת את כתובת המייל שלכם ולהתחיל לנהל את האירוע ב-VEYA.
  הקישור תקף ל-24 שעות.
</p>
{_button(verify_url, "אימות כתובת המייל")}
{_fallback_link(verify_url)}
<p style="margin:24px 0 0;padding-top:16px;border-top:1px solid {_BRAND_LINE};
          font:400 13px/1.7 -apple-system,'Segoe UI',Arial,sans-serif;color:{_BRAND_MUTED};">
  אם לא נרשמתם ל-VEYA, אפשר פשוט להתעלם מהמייל.
</p>
"""
    text = f"אימות כתובת המייל שלך ב-VEYA.\n\nלאימות: {verify_url}\n\nהקישור תקף ל-24 שעות."
    return send_email(to=to, subject=subject, html_body=_shell(title=subject, body_html=body), text_body=text)
