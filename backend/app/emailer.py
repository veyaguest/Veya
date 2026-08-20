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


# ── תבנית עיצוב משותפת ──────────────────────────────────────────────────────
# עיצוב inline בלבד: לקוחות מייל (בעיקר Gmail ו-Outlook) מתעלמים מ-<style>
# חיצוני ומ-classes, ולכן כל כלל CSS חייב לשבת על האלמנט עצמו. הפריסה בנויה
# על טבלאות מאותה סיבה — זה מה שנשאר responsive בכל לקוח מייל.
#
# הצבעים הם **בדיוק** טוקני המותג מ-frontend/src/App.css (:root), שטוחים
# ל-HEX כי rgba() ו-gradient לא נתמכים ב-Outlook. אין כאן שום צבע שהומצא
# למייל — כל ערך מופיע אחד-לאחד ב-design system של האפליקציה.
_BRAND_INK = "#2b2620"        # --charcoal  · כותרות וטקסט ראשי
_BRAND_BODY = "#4a4438"       # --body      · טקסט גוף
_BRAND_MUTED = "#8c8375"      # --muted     · טקסט משני/פוטר
_BRAND_LINE = "#e5dec9"       # --line      · מסגרות ומפרידים
_BRAND_BG = "#fbf6ee"         # --ivory     · רקע העמוד + משטח מקונן
_BRAND_CARD = "#ffffff"       # --cream     · משטח הכרטיס
_BRAND_GOLD = "#c9a227"       # --gold      · הדגשה ראשית ו-CTA
_BRAND_GOLD_DEEP = "#9a7b2e"  # --gold-deep · טקסט זהב קריא על רקע בהיר
_BRAND_ON_GOLD = "#201a06"    # צבע הטקסט של .btn-primary על רקע זהב
_BRAND_ON_DARK = "#f5efe2"    # הטקסט הבהיר על המשטח הכהה (fallback ללוגו)

# הגופנים של VEYA — אותם שמות שנטענים ב-frontend/app.html: Assistant לגוף
# ו-Frank Ruhl Libre לכותרות. ב-HTML של מייל אי אפשר לסמוך עליהם: חלק
# מהלקוחות (Apple Mail, iOS, Gmail באנדרואיד) יטענו אותם דרך ה-<link>
# שב-<head>, ואחרים (בעיקר Outlook ו-Gmail בדפדפן) יתעלמו לגמרי. לכן אחרי
# כל שם מותג באה שרשרת web-safe אמיתית שתומכת בעברית: Tahoma הוא ברירת
# המחדל העברית הבטוחה בווינדוס, Arial במק, ו-Times New Roman לסריף.
_FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700"
    "&family=Frank+Ruhl+Libre:wght@500;700&display=swap"
)
_FONT_SANS = "'Assistant','Segoe UI',Tahoma,Arial,sans-serif"
_FONT_SERIF = "'Frank Ruhl Libre','Times New Roman',Georgia,serif"

# לוגו המותג הרשמי — אותו קובץ שהאפליקציה ודף הנחיתה מציגים
# (frontend/public/logo.png). לקוחות מייל לא תומכים ב-SVG, ולכן PNG.
# הכתובת נבנית מ-public_base_url() הקיים — בלי שום הגדרה חדשה.
_LOGO_WIDTH = 140
_LOGO_HEIGHT = 122  # יחס הקובץ המקורי: 1224x1067


def logo_url() -> str:
    """כתובת מלאה ללוגו — במייל חייבת להיות אבסולוטית."""
    return f"{public_base_url()}/logo.png"


def _shell(*, title: str, preheader: str, body_html: str) -> str:
    """מעטפת המייל — זהה לכל מיילי VEYA (אימות, הזמנת שותף וכל מה שיבוא).

    המבנה מחקה את פריסת האפליקציה עצמה: **משטח כהה עם הלוגו למעלה, ותוכן
    בהיר ואוורירי מתחתיו** — בדיוק כמו סרגל הצד הכהה מול אזור התוכן השנהבי.
    בכוונה בלי מסגרות, בלי פס זהב ובלי כרטיסים מקוננים: לפי `brand.md`
    "הפחתה תמיד עדיפה על הוספה", והזהב הוא accent (הלוגו, תווית הקוד,
    הכפתור) ולא צבע ששוטף את המייל.

    ``preheader`` הוא שורת התצוגה המקדימה בתיבת הדואר — מוסתרת בגוף המייל.
    """
    return f"""<!doctype html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{_FONTS_HREF}">
<style>
  /* מובייל: מקטינים ריווח פנימי כדי שהתוכן ינשום גם ב-360px.
     לקוחות שלא תומכים ב-@media פשוט נשארים עם ערכי ה-inline. */
  @media only screen and (max-width:480px) {{
    .veya-pad {{ padding-left:24px !important; padding-right:24px !important; }}
    .veya-code {{ font-size:34px !important; letter-spacing:8px !important; }}
    .veya-h1 {{ font-size:23px !important; }}
  }}
  /* מצב כהה — נתמך ב-Apple Mail/iOS ובחלק מהלקוחות. ‎!important‎ הכרחי
     כדי לגבור על ה-inline styles. הערכים הם טוקני המצב הכהה של App.css. */
  @media (prefers-color-scheme: dark) {{
    .veya-bg {{ background:#14120e !important; }}
    .veya-card {{ background:#1c1a14 !important; }}
    .veya-soft {{ background:#14120e !important; }}
    .veya-ink {{ color:#f5efe2 !important; }}
    .veya-body {{ color:#cfc8b8 !important; }}
    .veya-muted {{ color:#8b8578 !important; }}
    /* --gold-deep הופך לזהב בהיר על רקע כהה, בדיוק כמו בהקשר הכהה ב-App.css */
    .veya-gold {{ color:#e4c96b !important; }}
    .veya-rule {{ background:#2a2620 !important; }}
  }}
</style>
</head>
<body class="veya-bg" style="margin:0;padding:0;background:{_BRAND_BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;
            mso-hide:all;font-size:1px;line-height:1px;color:{_BRAND_BG};">
  {html.escape(preheader)}
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       class="veya-bg" style="background:{_BRAND_BG};padding:40px 16px;">
  <tr>
    <td align="center">
      <!--[if mso]>
      <table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0"
             border="0"><tr><td>
      <![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;border-radius:16px;overflow:hidden;">
        <!-- משטח כהה עם הלוגו הרשמי. הלוגו של VEYA בנוי למשטח כהה (מילת
             המותג בשנהב), ולכן זה גם הרקע הנכון עבורו וגם ההד של סרגל הצד
             באפליקציה. ה-alt מעוצב כדי שגם כשלקוח המייל חוסם תמונות תישאר
             מילת המותג בשנהב על הרקע הכהה — ולא ריבוע שבור. -->
        <tr>
          <td bgcolor="{_BRAND_INK}" align="center"
              style="background:{_BRAND_INK};padding:26px 24px 24px;text-align:center;">
            <img src="{logo_url()}" alt="VEYA"
                 width="{_LOGO_WIDTH}" height="{_LOGO_HEIGHT}"
                 style="display:block;margin:0 auto;border:0;outline:none;
                        width:{_LOGO_WIDTH}px;height:{_LOGO_HEIGHT}px;
                        color:{_BRAND_ON_DARK};font:500 24px/{_LOGO_HEIGHT}px {_FONT_SERIF};
                        letter-spacing:7px;text-align:center;">
          </td>
        </tr>
        <tr>
          <td class="veya-card veya-pad" bgcolor="{_BRAND_CARD}"
              style="background:{_BRAND_CARD};padding:44px 44px 40px;
                     font-family:{_FONT_SANS};text-align:right;direction:rtl;">
            {body_html}
          </td>
        </tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
      <div class="veya-muted" style="max-width:600px;margin:22px auto 0;
                  font:400 12px/1.8 {_FONT_SANS};color:{_BRAND_MUTED};
                  text-align:center;direction:rtl;">
        VEYA · מערכת חכמה לניהול אירועים<br>veyaguest.co.il
      </div>
    </td>
  </tr>
</table>
</body>
</html>"""


# ── אבני הבניין של גוף המייל ────────────────────────────────────────────────
# היררכיה קבועה בשני המיילים: eyebrow קטן → כותרת סריפית → גוף רגוע →
# תוכן ראשי (קוד/אירוע) → CTA אחד → הערת סיום שקטה.


def _eyebrow(text: str) -> str:
    """תווית זעירה מעל הכותרת — הנגיעה היחידה של זהב בראש התוכן."""
    return (
        f'<p class="veya-gold" style="margin:0 0 12px;font:600 11px/1.5 {_FONT_SANS};'
        f'letter-spacing:2px;color:{_BRAND_GOLD_DEEP};">{html.escape(text)}</p>'
    )


def _title(text_html: str) -> str:
    """כותרת המייל — סריף, כמו כותרות המסכים באפליקציה (Frank Ruhl Libre)."""
    return (
        f'<h1 class="veya-ink veya-h1" style="margin:0 0 14px;font:500 26px/1.35 {_FONT_SERIF};'
        f'color:{_BRAND_INK};">{text_html}</h1>'
    )


def _paragraph(text_html: str, *, size: int = 15, top: int = 0) -> str:
    """פסקת גוף רגילה — תמיד מיושרת לימין, שורות נושמות."""
    return (
        f'<p class="veya-body" style="margin:{top}px 0 0;font:400 {size}px/1.8 {_FONT_SANS};'
        f'color:{_BRAND_BODY};">{text_html}</p>'
    )


def _button(url: str, label: str) -> str:
    """ה-CTA היחיד — הגרסה השטוחה של ``.btn-primary``: זהב מלא, טקסט כהה,
    פינות 12px. <a> ולא <button>, כי לקוחות מייל לא מריצים JS.
    ``bgcolor`` על ה-<td> נשאר בשביל Outlook, שמתעלם מ-background ב-CSS."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:30px 0 0;"><tr><td align="center" bgcolor="{_BRAND_GOLD}" '
        f'style="background:{_BRAND_GOLD};border-radius:12px;">'
        f'<a href="{html.escape(url, quote=True)}" '
        f'style="display:inline-block;padding:15px 40px;color:{_BRAND_ON_GOLD};'
        f'text-decoration:none;border-radius:12px;font:700 15px/1 {_FONT_SANS};">'
        f"{html.escape(label)}</a></td></tr></table>"
    )


def _fallback_link(url: str) -> str:
    """הקישור המלא כטקסט — למי שהכפתור לא עובד אצלו בלקוח המייל."""
    safe = html.escape(url)
    return (
        f'<p class="veya-muted" style="margin:14px 0 0;font:400 11px/1.7 {_FONT_SANS};'
        f'color:{_BRAND_MUTED};direction:ltr;text-align:right;word-break:break-all;">{safe}</p>'
    )


def _fine_print(text: str) -> str:
    """הערת הסיום — מופרדת בקו שיער דק, לא במסגרת."""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:34px 0 0;"><tr><td class="veya-rule" height="1" bgcolor="{_BRAND_LINE}" '
        f'style="height:1px;line-height:1px;font-size:0;background:{_BRAND_LINE};">&nbsp;</td>'
        f'</tr></table>'
        f'<p class="veya-muted" style="margin:18px 0 0;font:400 12.5px/1.75 {_FONT_SANS};'
        f'color:{_BRAND_MUTED};">{html.escape(text)}</p>'
    )


# ── מייל 1: הזמנת בן/בת זוג לניהול משותף ────────────────────────────────────
def send_partner_invite(
    *, to: str, inviter_name: str, event_title: str, invite_url: str
) -> SendResult:
    """מייל ההזמנה לניהול משותף של האירוע."""
    inviter = inviter_name.strip() or "בן/בת הזוג שלך"
    subject = f"{inviter} הזמין אותך לנהל את האירוע ב-VEYA"
    # שם האירוע — שורה שקטה מתחת לכותרת, בלי כרטיס ובלי מסגרת: זה מידע
    # מזהה, לא אלמנט שמתחרה על תשומת הלב עם ה-CTA.
    event_line = (
        f'<p class="veya-ink" style="margin:14px 0 0;font:600 16px/1.5 {_FONT_SANS};'
        f'color:{_BRAND_INK};">{html.escape(event_title)}</p>'
        if event_title
        else ""
    )
    body = f"""
{_eyebrow("הזמנה לניהול משותף")}
{_title("הוזמנת לנהל את האירוע ב־VEYA")}
{_paragraph(f"{html.escape(inviter)} הזמין אותך להצטרף לניהול האירוע ב־VEYA.")}
{event_line}
{_button(invite_url, "הצטרפות לאירוע")}
{_fallback_link(invite_url)}
{_paragraph("נהלו יחד את המוזמנים, אישורי ההגעה, סידור ההושבה ועוד.", size=14, top=26)}
{_fine_print("אם לא ציפיתם להזמנה הזו, אפשר פשוט להתעלם מהמייל הזה.")}
"""
    text = (
        f"הוזמנת לנהל את האירוע ב-VEYA\n\n"
        f"{inviter} הזמין אותך להצטרף לניהול האירוע ב-VEYA.\n"
        f"{event_title}\n\n"
        f"להצטרפות: {invite_url}\n\n"
        "נהלו יחד את המוזמנים, אישורי ההגעה, סידור ההושבה ועוד.\n\n"
        "אם לא ציפיתם להזמנה הזו, אפשר להתעלם מהמייל הזה."
    )
    preheader = f"{inviter} הזמין אותך להצטרף לניהול האירוע ב-VEYA."
    return send_email(
        to=to,
        subject=subject,
        html_body=_shell(title=subject, preheader=preheader, body_html=body),
        text_body=text,
    )


def _code_block(code: str) -> str:
    """קוד האימות — ה-centerpiece של המייל.

    בכוונה **בלי** שש תיבות ובלי מסגרת זהב: משטח שנהב שקט אחד, תווית זעירה,
    והספרות עצמן גדולות ומרוּוחות. זה קריא יותר, קל יותר להעתקה, ונאמן
    לעיקרון "הפחתה תמיד עדיפה על הוספה" מ-brand.md.

    פרטים שחשובים דווקא בלקוחות מייל:
    - ``dir="ltr"`` על הספרות — אחרת הן מתהפכות בתוך מייל RTL.
    - ``letter-spacing`` מוסיף רווח גם **אחרי** הספרה האחרונה, מה שמזיז את
      הבלוק שמאלה; ``padding-left`` בגודל זהה מחזיר אותו למרכז אופטי.
    - בלי flex/grid — רק טבלה ו-``text-align``, שנתמכים בכל לקוח.
    """
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin:28px 0 0;">
  <tr>
    <td class="veya-soft" bgcolor="{_BRAND_BG}" align="center"
        style="background:{_BRAND_BG};border-radius:14px;padding:26px 16px 24px;
               text-align:center;">
      <div class="veya-gold" style="font:600 11px/1.5 {_FONT_SANS};letter-spacing:2px;
                  color:{_BRAND_GOLD_DEEP};">קוד האימות</div>
      <div class="veya-ink veya-code" dir="ltr"
           style="margin:14px 0 0;font:600 40px/1.1 {_FONT_SANS};letter-spacing:10px;
                  padding-left:10px;color:{_BRAND_INK};">{html.escape(code)}</div>
    </td>
  </tr>
</table>
<p class="veya-muted" style="margin:14px 0 0;font:400 12.5px/1.7 {_FONT_SANS};
          color:{_BRAND_MUTED};text-align:center;">הקוד תקף ל־10 דקות</p>
"""


# ── מייל 2: אימות כתובת המייל ───────────────────────────────────────────────
def send_email_verification(*, to: str, verify_url: str, code: str) -> SendResult:
    """מייל אימות כתובת המייל אחרי הרשמה — קוד 6 ספרות (ערוץ עיקרי, תקף
    10 דקות) + קישור כ-fallback (תקף 24 שעות) שממשיך לעבוד במקביל."""
    subject = "קוד האימות שלך ל-VEYA"
    body = f"""
{_eyebrow("אימות חשבון")}
{_title("אימות כתובת המייל")}
{_paragraph("שלחנו לך קוד אימות כדי להשלים את ההרשמה ל־VEYA.")}
{_code_block(code)}
{_button(verify_url, "אימות המייל שלי")}
{_fallback_link(verify_url)}
{_fine_print("אם לא ביקשת להירשם ל־VEYA, אפשר להתעלם מהמייל הזה.")}
"""
    text = (
        f"אימות כתובת המייל\n\n"
        f"שלחנו לך קוד אימות כדי להשלים את ההרשמה ל-VEYA.\n\n"
        f"קוד האימות: {code}\n"
        f"הקוד תקף ל-10 דקות.\n\n"
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
