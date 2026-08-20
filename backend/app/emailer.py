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


# הדומיין המאומת ב-Resend. **veyaguest.co.il ולא veya.co.il** — זו הייתה
# התקלה: ברירת המחדל הקודמת הצביעה על veya.co.il, שאינו מוגדר ב-Resend כלל
# (ה-SPF שלו מפנה ל-Hostinger, ואין לו רשומת resend._domainkey). Resend דחתה
# כל שליחה ב-403 עוד לפני שנוצר מייל — ולכן ה-Emails/Logs נשארו ריקים לגמרי,
# והמשתמש קיבל "משהו השתבש" (ה-502 שנגזר מכך).
# האימות בפועל של veyaguest.co.il מאומת ב-DNS: resend._domainkey (DKIM),
# send.veyaguest.co.il עם include:amazonses.com (התשתית של Resend), ורשומת
# MX ל-feedback-smtp של SES.
_VERIFIED_SENDER = "VEYA <invite@veyaguest.co.il>"


def from_address() -> str:
    """כתובת השולח — חייבת להיות בדומיין מאומת ב-Resend (ראו ההערה למעלה)."""
    return os.getenv("RESEND_FROM", _VERIFIED_SENDER)


# הכתובת הידועה של ה-Frontend בייצור — משמשת רק כברירת מחדל כש-PUBLIC_BASE_URL
# לא הוגדר בסביבת הריצה. זו הייתה בדיוק התקלה: PUBLIC_BASE_URL הוא משתנה
# sync:false ב-render.yaml (ממולא ידנית ב-Render Dashboard) שמעולם לא הוגדר
# בפועל, ולכן כל קישור שנבנה — מייל אימות, הזמנת שותף, קישור RSVP — נפל
# חזרה ל-http://localhost:5173 גם בייצור החי.
_PRODUCTION_FRONTEND_URL = "https://veyaguest.co.il"


def public_base_url() -> str:
    """כתובת הבסיס של האפליקציה — לבניית קישורים במיילים ובהודעות WhatsApp.

    מקור אמת יחיד (גם messaging.py מייבא מכאן, לא משכפל). סדר עדיפויות:
    1. ``PUBLIC_BASE_URL`` — אם הוגדר במפורש, הוא תמיד מנצח (מאפשר גם
       staging/preview environments בעתיד בלי לגעת בקוד).
    2. ``VEYA_ENV=production`` בלי ``PUBLIC_BASE_URL`` מוגדר — נופלים בעדינות
       לכתובת הייצור הידועה, כדי שלא ניפול ל-localhost בייצור החי כמו שקרה.
    3. אחרת (פיתוח מקומי) — שרת הפיתוח הרגיל של Vite.
    """
    explicit = os.getenv("PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if os.getenv("VEYA_ENV", "").strip().lower() == "production":
        return _PRODUCTION_FRONTEND_URL
    return "http://localhost:5173"


# ── DEBUG זמני (tracing ייצור) ──────────────────────────────────────────────
# נוסף כדי לאתר למה לא יוצאות בקשות ל-Resend. לא מדפיס אף פעם מפתח API,
# טוקן, או כתובת מייל מלאה. להסרה אחרי שהתקלה תאותר.
def _mask_email(addr: str) -> str:
    """מסתיר את רוב הכתובת ומשאיר רק מספיק כדי לזהות התאמה בין שורות לוג."""
    addr = (addr or "").strip()
    if "@" not in addr:
        return "***"
    local, _, domain = addr.partition("@")
    keep = local[:2] if len(local) > 2 else local[:1]
    return f"{keep}***@{domain}"


def debug_log(message: str) -> None:
    """שורת trace אחת. flush מפורש — אחרת Render עלול לא להציג אותה בזמן אמת."""
    print(f"[veya:email-trace] {message}", flush=True)


def config_summary() -> str:
    """תצורת המייל — **קיום** בלבד, אף פעם לא ערך המפתח."""
    return (
        f"RESEND_API_KEY present={bool(api_key())} "
        f"(len={len(api_key())}) | "
        f"RESEND_FROM env_set={'RESEND_FROM' in os.environ} "
        f"effective_from={from_address()!r} | "
        f"PUBLIC_BASE_URL={public_base_url()!r} | "
        f"mode={current_mode()}"
    )


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
    debug_log(f"emailer called | to={_mask_email(to)} | mode={mode}")
    if mode == "mock":
        # ⚠️ נקודת כשל אפשרית #1: אין RESEND_API_KEY ב-runtime של Render.
        # במצב הזה **לא נשלחת שום בקשת HTTP** ל-Resend — ולכן ה-Logs של
        # Resend יישארו ריקים לגמרי, בדיוק כמו שדווח.
        debug_log(
            "resend SKIPPED — mock mode. RESEND_API_KEY חסר/ריק בסביבת הריצה. "
            "לא נשלחה בקשת HTTP כלשהי."
        )
        print(f"[emailer:mock] אל: {to} | נושא: {subject}")
        return SendResult(ok=True, mode="mock", provider_id="mock")

    debug_log(f"resend live mode | from={from_address()!r} | POST {RESEND_API_URL}")
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
        debug_log(f"resend response status={response.status_code}")
        if response.status_code >= 400:
            # ⚠️ נקודת כשל אפשרית #2: Resend דחתה את הבקשה (מפתח לא תקין,
            # דומיין לא מאומת, from לא מורשה). זה כן יופיע ב-Resend Logs.
            debug_log(f"resend REJECTED | body={response.text[:200]}")
            return SendResult(
                ok=False, mode="live", error=f"Resend {response.status_code}: {response.text[:200]}"
            )
        provider_id = ""
        try:
            provider_id = str(response.json().get("id", ""))
        except Exception:
            pass
        debug_log(f"resend message id={provider_id or '(none)'}")
        return SendResult(ok=True, mode="live", provider_id=provider_id)
    except Exception as exc:  # רשת/תצורה — לא מפילים את הבקשה של המשתמש
        # ⚠️ נקודת כשל אפשרית #3: הבקשה מעולם לא הגיעה ל-Resend (DNS/רשת/
        # timeout). גם כאן ה-Logs של Resend יישארו ריקים — והשגיאה נבלעה עד
        # עכשיו בשקט מוחלט, כי הקוראים לא בדקו את ערך ההחזרה.
        debug_log(
            f"resend REQUEST FAILED — no HTTP response reached Resend | "
            f"{type(exc).__name__}: {str(exc)[:200]}"
        )
        return SendResult(ok=False, mode="live", error=str(exc)[:200])


# ── מערכת העיצוב של מיילי VEYA ──────────────────────────────────────────────
# העיקרון: המייל הוא ההמשך הישיר של מסך ההתחברות ומסך אימות המייל, ולכן הוא
# יושב על **אותו משטח כהה** ומשתמש באותם טוקנים בדיוק. משתמש שפותח את המייל
# ואז לוחץ ונוחת במסך האימות אמור להרגיש שהוא לא עזב את המוצר.
#
# מקורות האמת:
#   רקע/טקסט/מסגרות → הבלוק ".auth-marketing, .auth-panel, .verify-page" ב-App.css
#   הכפתור          → .auth-submit (כפתור ההתחברות)
#   שדה הקוד        → .verify-code-box / .auth-field input
#   הלוגו           → frontend/public/logo.png (קובץ המותג, לא שחזור)
#
# הצבעים שטוחים ל-HEX כי rgba(), gradient ו-CSS variables לא נתמכים ב-Outlook.
# אין כאן אף צבע שהומצא למייל.
_INK = "#f5efe2"        # --charcoal בהקשר כהה · כותרות וטקסט ראשי
_BODY = "#cfc8b8"       # --body     בהקשר כהה · טקסט גוף
_MUTED = "#8b8578"      # --muted    בהקשר כהה · טקסט משני
_SURFACE = "#14120e"    # --cream    בהקשר כהה · רקע המייל (= רקע מסך האימות)
_INSET = "#0b0a0c"      # --black             · משטח שדות הקוד במסך האימות
_LINE = "#2a2620"       # --line     בהקשר כהה · קווי הפרדה
_LINE_2 = "#3a3426"     # --line-2   בהקשר כהה · מסגרת שדה קלט
_GOLD = "#c9a227"       # --gold
_GOLD_LIGHT = "#e4c96b" # --gold-light · גם --gold-deep בהקשר כהה (זהב קריא על כהה)
_ON_GOLD = "#14120e"    # צבע הטקסט של .auth-submit — --cream בהקשר כהה

# הגופנים של VEYA, בדיוק כפי שהם מוגדרים ב-frontend/app.html ו-App.css:
#   לוגו     → Cormorant Garamond (רק ב-wordmark; במייל זו תמונה, לא טקסט)
#   כותרות   → Frank Ruhl Libre  (.auth-panel-title, .verify-title)
#   גוף/כפתור → Assistant         (index.css, .auth-submit, .auth-field input)
# לקוחות מייל: Apple Mail/iOS ו-Gmail באנדרואיד יטענו אותם דרך ה-<link>;
# Outlook ו-Gmail בדפדפן יתעלמו. לכן לכל אחד יש שרשרת web-safe שתומכת
# בעברית — Tahoma היא ברירת המחדל העברית בווינדוס, Arial במק,
# ו-Times New Roman/Georgia נותנים את תחושת הסריף של הכותרות.
_FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700"
    "&family=Frank+Ruhl+Libre:wght@500;700&display=swap"
)
_FONT_SANS = "'Assistant','Segoe UI',Tahoma,Arial,sans-serif"
_FONT_SERIF = "'Frank Ruhl Libre','Times New Roman',Georgia,serif"

# קובץ הלוגו הרשמי — אותו קובץ שמסך אימות המייל מציג ושדף הנחיתה משתמש בו
# ב-hero. לקוחות מייל לא מרנדרים SVG, ולכן PNG (ו-logo.svg ממילא מרנדר את
# מילת המותג כ-<text> בגופן חיצוני, שלא נטען בתוך <img>).
_LOGO_WIDTH = 152   # == width במסך האימות (VerifyEmailPage.tsx)
_LOGO_HEIGHT = 133  # == height במסך האימות — אותו קובץ, אותו גודל בדיוק


def logo_url() -> str:
    """כתובת מלאה ללוגו — במייל חייבת להיות אבסולוטית."""
    return f"{public_base_url()}/logo.png"


def _shell(*, title: str, preheader: str, body_html: str) -> str:
    """מעטפת אחת לכל מיילי VEYA.

    בלי כרטיס, בלי מסגרות ובלי פסי קישוט: טור אחד ממורכז ברוחב 600px על
    המשטח הכהה של המותג, עם הרבה אוויר. ``preheader`` הוא שורת התצוגה
    המקדימה בתיבת הדואר (מוסתרת בגוף המייל).
    """
    return f"""<!doctype html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- המייל כהה מלכתחילה. ההצהרה הזו מונעת מלקוחות שתומכים בה להפוך אותו
     שוב במצב כהה (inversion), מה שהיה הורס את הניגודיות. -->
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{_FONTS_HREF}">
<style>
  :root {{ color-scheme: dark; }}
  /* מובייל — לקוחות בלי תמיכה ב-@media נשארים עם ערכי ה-inline. */
  @media only screen and (max-width:480px) {{
    .veya-pad {{ padding-left:26px !important; padding-right:26px !important; }}
    .veya-code {{ font-size:32px !important; letter-spacing:8px !important;
                  padding-left:8px !important; }}
    .veya-h1 {{ font-size:24px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{_SURFACE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;
            font-size:1px;line-height:1px;color:{_SURFACE};">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       bgcolor="{_SURFACE}" style="background:{_SURFACE};">
  <tr>
    <td align="center" style="padding:48px 16px 40px;">
      <!--[if mso]>
      <table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0"
             border="0"><tr><td>
      <![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;">
        <!-- Header: הלוגו בלבד. ה-alt מעוצב כך שגם כשלקוח המייל חוסם
             תמונות נשארת מילת המותג בשנהב ולא ריבוע שבור. -->
        <tr>
          <td align="center" class="veya-pad" style="padding:0 44px 30px;text-align:center;">
            <img src="{logo_url()}" alt="VEYA"
                 width="{_LOGO_WIDTH}" height="{_LOGO_HEIGHT}"
                 style="display:block;margin:0 auto;border:0;outline:none;
                        width:{_LOGO_WIDTH}px;height:{_LOGO_HEIGHT}px;
                        color:{_INK};font:500 24px/{_LOGO_HEIGHT}px {_FONT_SERIF};
                        letter-spacing:7px;text-align:center;">
          </td>
        </tr>
        <tr>
          <td class="veya-pad" style="padding:0 44px;font-family:{_FONT_SANS};
                     direction:rtl;text-align:center;">
            {body_html}
          </td>
        </tr>
        <!-- Footer: קו שיער ושורה אחת. -->
        <tr>
          <td class="veya-pad" style="padding:38px 44px 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td height="1" bgcolor="{_LINE}"
                      style="height:1px;line-height:1px;font-size:0;
                             background:{_LINE};">&nbsp;</td></tr>
            </table>
            <p style="margin:18px 0 0;font:400 11.5px/1.8 {_FONT_SANS};color:{_MUTED};
                      text-align:center;direction:rtl;">
              VEYA · מערכת חכמה לניהול אירועים<br>veyaguest.co.il
            </p>
          </td>
        </tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td>
  </tr>
</table>
</body>
</html>"""


# ── אבני הבניין של גוף המייל ────────────────────────────────────────────────
# היררכיה קבועה בשני המיילים, זהה לזו של מסך אימות המייל:
# כותרת סריפית → משפט אחד רגוע → התוכן הראשי → CTA אחד → הערה שקטה.


def _title(text_html: str) -> str:
    """כותרת — Frank Ruhl Libre, בדיוק כמו .verify-title ו-.auth-panel-title."""
    return (
        f'<h1 class="veya-h1" style="margin:0;font:600 26px/1.35 {_FONT_SERIF};'
        f'letter-spacing:-0.01em;color:{_INK};">{text_html}</h1>'
    )


def _lead(text_html: str) -> str:
    """המשפט שמתחת לכותרת — זהה ל-.verify-sub (14.5px, --muted)."""
    return (
        f'<p style="margin:12px 0 0;font:400 14.5px/1.6 {_FONT_SANS};'
        f'color:{_MUTED};">{text_html}</p>'
    )


def _secondary(text_html: str) -> str:
    """טקסט משני אחרי ה-CTA — אותו גודל של ``_lead`` עם מרווח עליון גדול יותר."""
    return (
        f'<p style="margin:28px 0 0;font:400 14.5px/1.7 {_FONT_SANS};'
        f'color:{_MUTED};">{text_html}</p>'
    )


def _accent_line(text_html: str) -> str:
    """שורת מידע מודגשת (למשל שם האירוע) — טקסט ראשי, בלי כרטיס ובלי מסגרת."""
    return (
        f'<p style="margin:14px 0 0;font:600 16px/1.5 {_FONT_SANS};'
        f'color:{_INK};">{text_html}</p>'
    )


def _button(url: str, label: str) -> str:
    """ה-CTA היחיד — ``.auth-submit`` מתורגם למייל.

    ``bgcolor`` + ``background`` מוצקים בזהב המותג הם מה ש-Outlook יראה;
    לקוחות שתומכים ב-background-image יקבלו את אותו gradient בדיוק של
    כפתור ההתחברות באפליקציה. הטקסט הכהה על הזהב הוא --cream בהקשר הכהה,
    בדיוק כמו במסך.
    """
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'align="center" style="margin:32px auto 0;"><tr>'
        f'<td align="center" bgcolor="{_GOLD}" style="background:{_GOLD};'
        f'background-image:linear-gradient(150deg,{_GOLD_LIGHT},#b08d2a);'
        f'border-radius:8px;">'
        f'<a href="{html.escape(url, quote=True)}" '
        f'style="display:inline-block;padding:16px 44px;color:{_ON_GOLD};'
        f'text-decoration:none;border-radius:8px;font:700 16px/1 {_FONT_SANS};">'
        f"{html.escape(label)}</a></td></tr></table>"
    )


def _fallback_link(url: str) -> str:
    """הקישור המלא כטקסט — למי שהכפתור לא עובד אצלו בלקוח המייל."""
    return (
        f'<p style="margin:16px 0 0;font:400 11px/1.7 {_FONT_SANS};color:{_MUTED};'
        f'direction:ltr;text-align:center;word-break:break-all;">{html.escape(url)}</p>'
    )


def _fine_print(text: str) -> str:
    """הערת הסיום — שורה שקטה, בלי מסגרת ובלי רקע."""
    return (
        f'<p style="margin:30px 0 0;font:400 12.5px/1.75 {_FONT_SANS};'
        f'color:{_MUTED};">{html.escape(text)}</p>'
    )


def _code_block(code: str) -> str:
    """הקוד — ה-centerpiece, ובמכוון נראה כמו שדות הקוד במסך האימות:
    אותו משטח כמעט-שחור (--black) ואותה מסגרת (--line-2 בהקשר כהה).

    פרטים שחשובים דווקא בלקוחות מייל:
    - ``dir="ltr"`` על הספרות, אחרת הן מתהפכות בתוך מייל RTL.
    - ``letter-spacing`` מוסיף רווח גם **אחרי** הספרה האחרונה ומזיז את הבלוק
      שמאלה; ``padding-left`` בגודל זהה מחזיר אותו למרכז אופטי.
    - בלי flex/grid — רק טבלה ו-``text-align``, שנתמכים בכל לקוח.
    """
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin:30px 0 0;">
  <tr>
    <td align="center" bgcolor="{_INSET}"
        style="background:{_INSET};border:1px solid {_LINE_2};border-radius:12px;
               padding:24px 16px;text-align:center;">
      <div class="veya-code" dir="ltr"
           style="font:600 40px/1.1 {_FONT_SANS};letter-spacing:12px;
                  padding-left:12px;color:{_INK};">{html.escape(code)}</div>
    </td>
  </tr>
</table>
<p style="margin:14px 0 0;font:400 12.5px/1.7 {_FONT_SANS};color:{_MUTED};">
  הקוד תקף ל־10 דקות
</p>
"""


# ── מייל 1: הזמנת בן/בת זוג לניהול משותף ────────────────────────────────────
def send_partner_invite(
    *, to: str, inviter_name: str, event_title: str, invite_url: str
) -> SendResult:
    """מייל ההזמנה לניהול משותף של האירוע."""
    inviter = inviter_name.strip() or "בן/בת הזוג שלך"
    subject = f"{inviter} הזמין אותך לנהל את האירוע ב-VEYA"
    event_line = _accent_line(html.escape(event_title)) if event_title else ""
    body = f"""
{_title("הוזמנת לנהל את האירוע ב־VEYA")}
{_lead(f"{html.escape(inviter)} הזמין אותך להצטרף לניהול האירוע ב־VEYA.")}
{event_line}
{_button(invite_url, "הצטרפות לאירוע")}
{_fallback_link(invite_url)}
{_secondary("נהלו יחד את המוזמנים, אישורי ההגעה, סידור ההושבה ועוד.")}
{_fine_print("אם לא ציפיתם להזמנה הזו, אפשר להתעלם מהמייל הזה.")}
"""
    text = (
        "הוזמנת לנהל את האירוע ב-VEYA\n\n"
        f"{inviter} הזמין אותך להצטרף לניהול האירוע ב-VEYA.\n"
        f"{event_title}\n\n"
        f"להצטרפות: {invite_url}\n\n"
        "נהלו יחד את המוזמנים, אישורי ההגעה, סידור ההושבה ועוד.\n"
        "אם לא ציפיתם להזמנה הזו, אפשר להתעלם מהמייל הזה."
    )
    return send_email(
        to=to,
        subject=subject,
        html_body=_shell(
            title=subject,
            preheader=f"{inviter} הזמין אותך להצטרף לניהול האירוע ב-VEYA.",
            body_html=body,
        ),
        text_body=text,
    )


# ── מייל 2: אימות כתובת המייל ───────────────────────────────────────────────
def send_email_verification(*, to: str, verify_url: str, code: str) -> SendResult:
    """מייל אימות כתובת המייל אחרי הרשמה — קוד 6 ספרות (ערוץ עיקרי, תקף
    10 דקות) + קישור כ-fallback (תקף 24 שעות) שממשיך לעבוד במקביל."""
    subject = "קוד האימות שלך ל-VEYA"
    body = f"""
{_title("אימות כתובת המייל")}
{_lead("שלחנו לך קוד אימות כדי להשלים את ההרשמה ל־VEYA.")}
{_code_block(code)}
{_button(verify_url, "אימות המייל שלי")}
{_fallback_link(verify_url)}
{_fine_print("אם לא ביקשת להירשם ל־VEYA, אפשר להתעלם מהמייל הזה.")}
"""
    text = (
        "אימות כתובת המייל\n\n"
        "שלחנו לך קוד אימות כדי להשלים את ההרשמה ל-VEYA.\n\n"
        f"קוד האימות: {code}\n"
        "הקוד תקף ל-10 דקות.\n\n"
        f"אפשר גם לאמת בלחיצה אחת: {verify_url}\n\n"
        "אם לא ביקשת להירשם ל-VEYA, אפשר להתעלם מהמייל הזה."
    )
    return send_email(
        to=to,
        subject=subject,
        html_body=_shell(
            title=subject, preheader="הקוד תקף ל־10 דקות", body_html=body
        ),
        text_body=text,
    )
