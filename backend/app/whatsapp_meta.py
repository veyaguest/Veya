"""לקוח WhatsApp Cloud API של Meta — השכבה היחידה שמדברת עם graph.facebook.com.

מי קורא לכאן: ``messaging.MetaProvider`` (שליחת Template למוזמן) וכלי הבדיקה
הידני ``send_hello_world``. שום מקום אחר במערכת לא בונה בקשה ל-Meta.

## הגדרות (משתני סביבה בלבד — ראו ``load_config``)
``WHATSAPP_ACCESS_TOKEN`` (או הישן ``WHATSAPP_TOKEN``), ``WHATSAPP_PHONE_NUMBER_ID``
(או ``WHATSAPP_PHONE_ID``), ``WHATSAPP_BUSINESS_ACCOUNT_ID``, ``WHATSAPP_GRAPH_API_VERSION``
(ברירת מחדל ``v26.0``; ``v20.0`` שהיה כתוב בקוד פג ב-24.9.2026).

## תוצאה של שליחה — שלושה מצבים, לא שניים
- **נשלחה** (``sent``): Meta החזירה מזהה הודעה (``messages[0].id``) — היא קיבלה אותה.
- **נכשלה** (``failed``): Meta החזירה שגיאה — היא *לא* קיבלה. נשמרים קוד ותיאור.
- **לא ידוע** (``pending``): הבקשה יצאה, ולא ברור אם Meta קיבלה (timeout בקריאת
  התשובה, ניתוק באמצע, תשובה בלי מזהה). **לא מנסים שוב** — Meta לא מציעה
  מפתח שמונע כפילות, ושליחה חוזרת עלולה לתת לאורח הודעה כפולה. השורה נשארת
  ``pending``, ו-webhook עם ``biz_opaque_callback_data`` משלים אותה
  (``message_status.reconcile_pending``).

## ניסיון חוזר — רק כשבטוח ש-Meta לא קיבלה
כשל התחברות לפני שהבקשה יצאה, או קוד שגיאה ש-Meta עצמה מגדירה "נסו שוב"
(``RETRYABLE_CODES``, לפי developers.facebook.com/documentation/business-messaging/
whatsapp/support/error-codes, נבדק 2026-10-12). עד ``MAX_ATTEMPTS`` ניסיונות.

## מה לעולם לא יוצא מכאן
הטוקן לא נכתב ללוג ולא לסיבת הכשל (``_scrub``), וגם לא גוף התשובה הגולמי —
רק קוד, תיאור קצר מ-Meta ומזהה ה-trace שלה.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_GRAPH_VERSION = "v26.0"
_VERSION_RE = re.compile(r"^v\d{1,3}\.\d{1,2}$")

# קודים ש-Meta מגדירה כזמניים ("נסו שוב"): מגבלת קצב של האפליקציה/החשבון/
# המספר, שגיאה פנימית, שירות לא זמין, חשבון בתחזוקה. 131049/131056 אינם כאן —
# Meta מבקשת לחכות שעות, לא שניות; ניסיון חוזר מיידי רק יחמיר.
RETRYABLE_CODES = frozenset({4, 80007, 130429, 131000, 131016, 2494100})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)
TIMEOUT = 15.0
CONNECT_TIMEOUT = 5.0

# ערך ה-``provider_status`` כשהתוצאה לא ידועה — כדי שאפשר יהיה לזהות בדיוק
# אילו שורות ``pending`` הן "נשלחו ואין תשובה" (ולא "השרת נפל לפני השליחה").
OUTCOME_UNKNOWN = "send_outcome_unknown"
UNKNOWN_DETAIL = "לא ידוע אם Meta קיבלה את ההודעה — ממתינים לעדכון ממנה. לא נשלח שוב."

# נקודת החלפה לבדיקות (``httpx.MockTransport``) ולהמתנה בין ניסיונות.
_transport = None
_sleep = time.sleep


@dataclass(frozen=True)
class MetaConfig:
    access_token: str
    phone_number_id: str
    business_account_id: str
    graph_version: str

    def missing(self) -> list[str]:
        """שמות המשתנים החסרים לשליחה (בלי ערכים)."""
        out = []
        if not self.access_token:
            out.append("WHATSAPP_ACCESS_TOKEN")
        if not self.phone_number_id:
            out.append("WHATSAPP_PHONE_NUMBER_ID")
        return out


def _env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def load_config() -> MetaConfig:
    """ההגדרות ממשתני הסביבה. שמות חדשים קודמים; הישנים ממשיכים לעבוד."""
    version = _env("WHATSAPP_GRAPH_API_VERSION") or DEFAULT_GRAPH_VERSION
    if not _VERSION_RE.match(version):
        print("[veya:whatsapp] WHATSAPP_GRAPH_API_VERSION לא תקין — משתמשים בברירת המחדל",
              flush=True)
        version = DEFAULT_GRAPH_VERSION
    return MetaConfig(
        access_token=_env("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_TOKEN"),
        phone_number_id=_env("WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_PHONE_ID"),
        business_account_id=_env("WHATSAPP_BUSINESS_ACCOUNT_ID"),
        graph_version=version,
    )


def config_report() -> dict[str, str]:
    """מצב כל משתנה — "מוגדר"/"חסר" בלבד, לעולם לא הערך. לכלי הבדיקה."""
    names = {
        "WHATSAPP_MODE": ("WHATSAPP_MODE",),
        "WHATSAPP_ACCESS_TOKEN": ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": ("WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_PHONE_ID"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": ("WHATSAPP_BUSINESS_ACCOUNT_ID",),
        "WHATSAPP_VERIFY_TOKEN": ("WHATSAPP_VERIFY_TOKEN",),
        "WHATSAPP_APP_SECRET": ("WHATSAPP_APP_SECRET",),
        "WHATSAPP_GRAPH_API_VERSION": ("WHATSAPP_GRAPH_API_VERSION",),
        "WHATSAPP_TEST_RECIPIENTS": ("WHATSAPP_TEST_RECIPIENTS",),
    }
    return {k: ("מוגדר" if _env(*v) else "חסר") for k, v in names.items()}


def to_wa_number(phone: str) -> Optional[str]:
    """טלפון ישראלי בפורמט ש-Meta מצפה לו (``9725XXXXXXXX``), או ``None``."""
    from app.validators import normalize_israeli_phone

    try:
        local = normalize_israeli_phone(phone or "")
    except ValueError:
        return None
    return "972" + local[1:]


def _scrub(text: str, config: MetaConfig) -> str:
    """מבטיח שהטוקן לא ייכנס לשום טקסט שנשמר או מודפס."""
    text = text or ""
    if config.access_token and config.access_token in text:
        text = text.replace(config.access_token, "[redacted]")
    return text


def _client():
    import httpx

    return httpx.Client(
        timeout=httpx.Timeout(TIMEOUT, connect=CONNECT_TIMEOUT),
        transport=_transport,
    )


def _result(ok, status, detail="", provider_message_id="", error_code=None, provider_status=None):
    from app.messaging import SendResult

    return SendResult(
        ok=ok, provider="meta", status=status, detail=detail,
        provider_message_id=provider_message_id, error_code=error_code,
        provider_status=provider_status,
    )


def _post_message(config: MetaConfig, payload: dict, *, log_ref: str = ""):
    """שולח בקשה אחת ל-``/{phone-number-id}/messages`` עם ניסיונות חוזרים בטוחים.

    מחזיר ``SendResult`` עם ``status`` אחד מ-sent / failed / pending (לא ידוע).
    """
    import httpx

    missing = config.missing()
    if missing:
        return _result(False, "failed", detail="חסרות הגדרות WhatsApp: " + ", ".join(missing))

    url = f"https://graph.facebook.com/{config.graph_version}/{config.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {config.access_token}"}
    last: Optional[object] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _client() as client:
                resp = client.post(url, json=payload, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # הבקשה לא יצאה — בטוח לנסות שוב.
            last = _result(False, "failed", detail="לא ניתן להתחבר ל-Meta")
            _log("connect_error", log_ref, attempt=attempt, error=type(exc).__name__)
            if attempt < MAX_ATTEMPTS:
                _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                continue
            return last
        except httpx.HTTPError as exc:
            # הבקשה (אולי) יצאה ואין תשובה — לא ידוע. לא מנסים שוב.
            _log("outcome_unknown", log_ref, attempt=attempt, error=type(exc).__name__)
            return _result(False, "pending", detail=UNKNOWN_DETAIL, provider_status=OUTCOME_UNKNOWN)

        body = _json(resp)
        if 200 <= resp.status_code < 300:
            messages = body.get("messages") if isinstance(body, dict) else None
            first = messages[0] if isinstance(messages, list) and messages and isinstance(messages[0], dict) else {}
            wamid = first.get("id") if isinstance(first.get("id"), str) else ""
            if not wamid:
                # 2xx בלי מזהה — אי אפשר לדעת מה קרה, ואי אפשר לעקוב. לא ידוע.
                _log("outcome_unknown", log_ref, attempt=attempt, http=resp.status_code)
                return _result(False, "pending", detail=UNKNOWN_DETAIL, provider_status=OUTCOME_UNKNOWN)
            raw = first.get("message_status")
            _log("accepted", log_ref, attempt=attempt)
            return _result(True, "sent", provider_message_id=wamid,
                           provider_status=raw if isinstance(raw, str) else None)

        error = body.get("error") if isinstance(body, dict) else None
        error = error if isinstance(error, dict) else {}
        code = error.get("code")
        code = int(code) if isinstance(code, (int, str)) and str(code).lstrip("-").isdigit() else None
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        _log("error", log_ref, attempt=attempt, http=resp.status_code, code=code,
             trace=error.get("fbtrace_id") if isinstance(error.get("fbtrace_id"), str) else None)

        if code is None and resp.status_code >= 500:
            # שגיאת שרת בלי גוף של Meta (gateway וכו') — לא ברור אם התקבלה.
            return _result(False, "pending", detail=UNKNOWN_DETAIL, provider_status=OUTCOME_UNKNOWN)
        retryable = code in RETRYABLE_CODES or (code is None and resp.status_code == 429)
        detail = _scrub(f"Meta {code if code is not None else resp.status_code}: {message}"[:300], config)
        last = _result(False, "failed", detail=detail, error_code=code)
        if retryable and attempt < MAX_ATTEMPTS:
            _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
            continue
        return last
    return last  # pragma: no cover — הלולאה תמיד מחזירה


def _json(resp) -> object:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 — גוף לא-JSON מטופל כ"אין פרטים"
        return {}


def _log(outcome: str, ref: str, **fields) -> None:
    """שורת לוג בלי מידע אישי — בלי טלפון, בלי תוכן, בלי טוקן."""
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    print(f"[veya:whatsapp] meta {outcome} ref={ref or '-'} {parts}".rstrip(), flush=True)


# ---- בקשות ----

def template_payload(
    *, to: str, name: str, language: str, body_params: list[str],
    url_suffix: Optional[str] = None, callback_data: Optional[str] = None,
    header_image_id: Optional[str] = None,
    url_suffixes: Optional[list[tuple[int, str]]] = None,
) -> dict:
    """גוף בקשה לשליחת Template (Cloud API ``type: template``).

    ``body_params`` — ערכי ``{{1}}``, ``{{2}}``… בגוף התבנית, לפי הסדר.
    ``url_suffix`` — הסיומת הדינמית של כפתור הקישור (כפתור ראשון, index 0).
    ``url_suffixes`` — כמה כפתורי קישור דינמיים: ``[(index, סיומת), ...]`` (קישור
    אישי + ניווט). גובר על ``url_suffix``.
    ``callback_data`` — ``biz_opaque_callback_data``: Meta מחזירה אותו כמו שהוא
    בעדכוני הסטטוס של ההודעה (עד 512 תווים).
    ``header_image_id`` — מזהה מדיה (``upload_media``) לתבנית עם Header מסוג תמונה.
    """
    components: list[dict] = []
    if header_image_id:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": header_image_id}}],
        })
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in body_params],
        })
    if url_suffixes is None and url_suffix:
        url_suffixes = [(0, url_suffix)]
    for index, suffix in url_suffixes or []:
        components.append({
            "type": "button", "sub_type": "url", "index": str(index),
            "parameters": [{"type": "text", "text": suffix}],
        })
    template: dict = {"name": name, "language": {"code": language}}
    if components:
        template["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }
    if callback_data:
        payload["biz_opaque_callback_data"] = callback_data[:512]
    return payload


def send_template(
    *, phone: str, name: str, language: str, body_params: list[str],
    url_suffix: Optional[str] = None, callback_data: Optional[str] = None,
    header_image_id: Optional[str] = None, config: Optional[MetaConfig] = None,
    url_suffixes: Optional[list[tuple[int, str]]] = None,
):
    """שולח Template לטלפון ישראלי. מחזיר ``SendResult``."""
    config = config or load_config()
    to = to_wa_number(phone)
    if to is None:
        return _result(False, "failed", detail="מספר הטלפון אינו מספר ישראלי תקין")
    return _post_message(config, template_payload(
        to=to, name=name, language=language, body_params=body_params,
        url_suffix=url_suffix, callback_data=callback_data, header_image_id=header_image_id,
        url_suffixes=url_suffixes,
    ), log_ref=callback_data or "")


# ---- העלאת תמונה ל-Meta (Header של תבנית) ----
#
# Meta מקבלת תמונה רק כ-JPEG/PNG עד 5MB. מעלים את הבייטים בעצמנו (ולא שולחים
# קישור): תמונות ההזמנה נשמרות אצלנו כ-WebP, והשרת ב-Render "נרדם" — Meta לא
# הייתה מצליחה למשוך אותן. המזהה שחוזר תקף 30 יום לפי Meta, אבל **לא נשמר**:
# מעלים מחדש בכל מנת שליחה (``messaging.MetaProvider``), כך שמזהה ישן לא נשלח.

# שגיאות מדיה של Meta בשליחת הודעה (131052 הורדת מדיה, 131053 העלאת מדיה) —
# למשל מזהה שפג. אחרי אחת מהן מעלים מחדש לפני ההודעה הבאה (``messaging.MetaProvider``).
MEDIA_ERROR_CODES = frozenset({131052, 131053})


def upload_media(data: bytes, mime_type: str, *, config: Optional[MetaConfig] = None):
    """``POST /{phone-number-id}/media``. מחזיר ``(media_id, "")`` או ``(None, סיבה)``.

    בלי "לא ידוע": העלאה כפולה לא מזיקה (מזהה נוסף שלא בשימוש), ולכן כל
    כשל — כולל timeout — הוא פשוט "לא הועלתה", והשליחה לא מתבצעת.
    """
    import httpx

    config = config or load_config()
    missing = config.missing()
    if missing:
        return None, "חסרות הגדרות WhatsApp: " + ", ".join(missing)
    url = f"https://graph.facebook.com/{config.graph_version}/{config.phone_number_id}/media"
    headers = {"Authorization": f"Bearer {config.access_token}"}
    detail = "העלאת התמונה ל-Meta נכשלה"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _client() as client:
                resp = client.post(
                    url, headers=headers,
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files={"file": ("invitation.jpg", data, mime_type)},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            _log("media_connect_error", "", attempt=attempt, error=type(exc).__name__)
            if attempt < MAX_ATTEMPTS:
                _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                continue
            return None, "לא ניתן להתחבר ל-Meta"
        except httpx.HTTPError as exc:
            _log("media_error", "", attempt=attempt, error=type(exc).__name__)
            return None, detail
        body = _json(resp)
        media_id = body.get("id") if isinstance(body, dict) else None
        if 200 <= resp.status_code < 300 and isinstance(media_id, str) and media_id:
            _log("media_uploaded", "", attempt=attempt)
            return media_id, ""
        error = body.get("error") if isinstance(body, dict) else None
        error = error if isinstance(error, dict) else {}
        code = error.get("code")
        code = int(code) if isinstance(code, (int, str)) and str(code).lstrip("-").isdigit() else None
        _log("media_error", "", attempt=attempt, http=resp.status_code, code=code)
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        detail = _scrub(f"Meta {code if code is not None else resp.status_code}: {message}"[:300], config)
        if code in RETRYABLE_CODES and attempt < MAX_ATTEMPTS:
            _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
            continue
        return None, detail
    return None, detail


def send_text(*, phone: str, body: str, callback_data: Optional[str] = None,
              config: Optional[MetaConfig] = None):
    """הודעת טקסט חופשי — **רק** בתוך 24 השעות שאחרי הודעה מהאורח (אחרת Meta
    מחזירה 131047). לא מחובר היום לשום מסלול; קיים לשלב שבו נענה לאורחים."""
    config = config or load_config()
    to = to_wa_number(phone)
    if to is None:
        return _result(False, "failed", detail="מספר הטלפון אינו מספר ישראלי תקין")
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "text", "text": {"body": body[:4096]},
    }
    if callback_data:
        payload["biz_opaque_callback_data"] = callback_data[:512]
    return _post_message(config, payload, log_ref=callback_data or "")


# ---- כלי בדיקה ידני: hello_world ----

HELLO_WORLD = ("hello_world", "en_US")


@dataclass
class HelloWorldCheck:
    ok: bool
    reasons: list[str]


def hello_world_preflight(phone: str) -> HelloWorldCheck:
    """כל תנאי הבטיחות לכלי הבדיקה. **כולם** חייבים להתקיים:

    1. ``WHATSAPP_MODE=meta_test`` — לא mock ולא meta.
    2. ``VEYA_ENV`` אינו ``production`` — הכלי מקומי בלבד.
    3. עצירת החירום לא פעילה.
    4. הנמען ברשימה המורשית (``WHATSAPP_TEST_RECIPIENTS``), והרשימה לא ריקה.
    5. טוקן ומזהה מספר מוגדרים.
    """
    from app import messaging
    from app.validators import normalize_israeli_phone

    reasons: list[str] = []
    if messaging.whatsapp_mode() != messaging.MODE_META_TEST:
        reasons.append("WHATSAPP_MODE חייב להיות meta_test")
    if (os.getenv("VEYA_ENV") or "").strip().lower() == "production":
        reasons.append("הכלי לא רץ בסביבת production")
    if messaging.emergency_stop_active():
        reasons.append("עצירת החירום פעילה")
    allowed = messaging.test_recipients()
    try:
        local = normalize_israeli_phone(phone or "")
    except ValueError:
        local = None
    if not allowed:
        reasons.append("WHATSAPP_TEST_RECIPIENTS ריק")
    elif local is None or local not in allowed:
        reasons.append("הנמען אינו ברשימת הנמענים המורשים")
    missing = load_config().missing()
    if missing:
        reasons.append("חסרות הגדרות: " + ", ".join(missing))
    return HelloWorldCheck(ok=not reasons, reasons=reasons)


def send_hello_world(phone: str):
    """שולח את תבנית ``hello_world`` של Meta (קיימת בכל חשבון בדיקה) — רק אם
    ``hello_world_preflight`` עבר. לא נוגע במסד ולא קשור לשום אורח."""
    check = hello_world_preflight(phone)
    if not check.ok:
        return check, None
    name, language = HELLO_WORLD
    result = send_template(phone=phone, name=name, language=language, body_params=[],
                           callback_data="veya:hello_world")
    return check, result


# ---- כלי בדיקה ידני: veya_inv_pilot ----
#
# תבנית ניסוי אחת שאושרה ב-Meta (2026-10-15): הזמנה של אירוע בדיקה, שפרטי
# האירוע (שמות, תאריך, אולם) כתובים בה כטקסט קבוע. **לא** נמצאת ב-
# ``whatsapp_templates.TEMPLATES`` ולא מחוברת להזמנות — אורח אמיתי היה מקבל
# את פרטי אירוע הבדיקה. נשלחת רק מכלי הבדיקה, באותם תנאי בטיחות של hello_world.
# מבנה (docs/whatsapp-templates.md): {{1}} בגוף = שם פרטי; כפתור ראשון דינמי =
# הקוד האישי (``/confirm/{{1}}``); כפתור שני (ניווט) קבוע — בלי ערך.

INV_PILOT = ("veya_inv_pilot", "he")
# קוד אישי של מוזמן: ``secrets.token_urlsafe`` (models.py) — אותיות, ספרות, ``-`` ו-``_``.
_GUEST_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def _inv_pilot_value_problems(guest_name: str, guest_code: str) -> list[str]:
    """Meta דוחה ערך משתנה עם ירידת שורה, טאב או 4 רווחים ברצף; קוד שאינו
    בפורמט של VEYA היה יוצר קישור שבור בכפתור."""
    problems: list[str] = []
    name = (guest_name or "").strip()
    if not name:
        problems.append("חסר שם פרטי (--name)")
    elif len(name) > 60 or re.search(r"[\n\r\t]| {4}", name):
        problems.append("השם הפרטי ארוך מדי או מכיל ירידת שורה/טאב/רווחים מרובים")
    if not _GUEST_CODE_RE.match((guest_code or "").strip()):
        problems.append("הקוד האישי חסר או לא בפורמט של VEYA (--code)")
    return problems


def inv_pilot_preflight(phone: str, guest_name: str, guest_code: str) -> HelloWorldCheck:
    """תנאי ``hello_world_preflight`` + תקינות השם והקוד."""
    check = hello_world_preflight(phone)
    reasons = check.reasons + _inv_pilot_value_problems(guest_name, guest_code)
    return HelloWorldCheck(ok=not reasons, reasons=reasons)


def send_inv_pilot(phone: str, guest_name: str, guest_code: str):
    """שולח את ``veya_inv_pilot`` — רק אם ``inv_pilot_preflight`` עבר. לא נוגע
    במסד; ``callback_data`` לא בפורמט ``veya:m…`` ולכן ה-webhook לא ישייך את
    הסטטוסים לאף הודעה (``known=no``)."""
    check = inv_pilot_preflight(phone, guest_name, guest_code)
    if not check.ok:
        return check, None
    name, language = INV_PILOT
    result = send_template(phone=phone, name=name, language=language,
                           body_params=[guest_name.strip()], url_suffix=guest_code.strip(),
                           callback_data="veya:inv_pilot")
    return check, result


# ---- כלי בדיקה ידני: veya_invitation_image ----
#
# בדיקה של תבנית ההזמנה עם תמונה, בלי אירוע ובלי מסד: התמונה נלקחת מקובץ
# מקומי, ופרטי האירוע בגוף הם ערכי הדוגמה שהוגשו עם התבנית ל-Meta. באותם
# תנאי בטיחות של hello_world. אם ההמרה או ההעלאה נכשלות — לא נשלח כלום.

INVITATION_IMAGE = ("veya_invitation_image", "he")
INVITATION_TEST_VALUES = ("חתונה", "דניאל ושירה", "12/11/2026")


def send_invitation_image_test(phone: str, guest_name: str, guest_code: str,
                               image: bytes, content_type: str):
    """מחזיר ``(check, result)``; ``result`` הוא ``None`` אם לא נשלח."""
    from app import media

    check = inv_pilot_preflight(phone, guest_name, guest_code)
    if not check.ok:
        return check, None
    try:
        jpeg = media.whatsapp_jpeg(image, content_type)
    except media.WhatsAppImageError as exc:
        return HelloWorldCheck(ok=False, reasons=[f"התמונה לא נשלחת ב-WhatsApp: {exc}"]), None
    media_id, detail = upload_media(jpeg, "image/jpeg")
    if not media_id:
        return HelloWorldCheck(ok=False, reasons=[f"העלאת התמונה נכשלה: {detail}"]), None
    name, language = INVITATION_IMAGE
    result = send_template(
        phone=phone, name=name, language=language,
        body_params=[guest_name.strip(), *INVITATION_TEST_VALUES],
        url_suffix=guest_code.strip(), callback_data="veya:invitation_image_test",
        header_image_id=media_id,
    )
    return check, result
