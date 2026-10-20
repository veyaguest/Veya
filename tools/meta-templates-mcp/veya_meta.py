"""הלוגיקה של כלי ניהול התבניות: קריאה ל-Meta, בדיקת טיוטות, התאמה לקוד של VEYA.

אין כאן שליחת הודעות — אין קריאה ל-``/messages`` ואין שום דבר שנוגע במספר
הטלפון. הכלי מדבר רק עם WhatsApp Business Management API (תבניות ופרטי חשבון).

## הטוקן
נקרא מ-macOS Keychain (``security find-generic-password``), לא מקובץ ולא
ממשתנה סביבה. לא מוחזר לשום כלי, לא נכתב ללוג, ומוסר מכל טקסט שגיאה (``scrub``).
מספיקה הרשאה אחת: ``whatsapp_business_management``.

## כתיבה ל-Meta
רק שתי פעולות: יצירת תבנית ועריכת תבנית. כל אחת בשני שלבים —
``prepare_*`` (בדיקה ותצוגה, בלי לגעת ב-Meta) ואז ``submit_*`` עם מזהה הטיוטה
ואישור מפורש (שם התבנית). שום מחיקה.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
TEMPLATES_DOC = REPO / "docs" / "whatsapp-templates.md"

KEYCHAIN_SERVICE = "veya-meta-templates"
KEYCHAIN_ACCOUNT = "veya"
REQUIRED_SCOPE = "whatsapp_business_management"

# הכתובת הקבועה של כפתור הקישור האישי (docs/whatsapp-templates.md).
VEYA_CONFIRM_URL = "https://veyaguest.co.il/confirm/{{1}}"
VEYA_LANGUAGE = "he"

# תבניות שלא עורכים (החלטת המייסד 2026-10-15: תבנית הניסוי נשארת כמו שהיא).
LOCKED_TEMPLATES = frozenset({"veya_inv_pilot"})

TIMEOUT = 20.0
DRAFT_TTL = 30 * 60

# נקודת החלפה לבדיקות.
_transport = None
_token_override: Optional[str] = None


def _graph_version() -> str:
    """אותה גרסה כמו בשרת (``whatsapp_meta.DEFAULT_GRAPH_VERSION``)."""
    try:
        sys.path.insert(0, str(BACKEND))
        from app.whatsapp_meta import DEFAULT_GRAPH_VERSION
        return DEFAULT_GRAPH_VERSION
    except Exception:  # noqa: BLE001
        return "v26.0"


GRAPH_VERSION = os.getenv("VEYA_META_GRAPH_VERSION") or _graph_version()
GRAPH = "https://graph.facebook.com"


# ---------------------------------------------------------------- הטוקן

_token_cache: Optional[str] = None


def read_token() -> str:
    """הטוקן מה-Keychain, או ריק. נקרא מחדש אם עדיין לא נמצא (אחרי שהוסיפו אותו)."""
    global _token_cache
    if _token_override is not None:
        return _token_override
    if _token_cache:
        return _token_cache
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:  # noqa: BLE001
        return ""
    if out.returncode != 0:
        return ""
    _token_cache = out.stdout.strip()
    return _token_cache


def forget_token() -> None:
    global _token_cache
    _token_cache = None


def scrub(value: Any) -> Any:
    """מוציא את הטוקן מכל מחרוזת (גם בתוך מבנים)."""
    token = read_token() if (_token_cache or _token_override) else ""
    if isinstance(value, str):
        return value.replace(token, "[redacted]") if token else value
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- שגיאות

# הסבר בעברית לפי קוד השגיאה הראשי של Meta. כשאין התאמה — מציגים את הטקסט
# של Meta עצמה (error_user_title / error_user_msg), שהוא בדרך כלל ברור.
ERROR_HELP = {
    190: "הטוקן לא תקף או פג. צרו טוקן חדש ל-System User (תוקף: Never) ועדכנו אותו ב-Keychain "
         "(הפקודה ב-tools/meta-templates-mcp/README.md).",
    200: "אין הרשאה. ודאו שלטוקן יש whatsapp_business_management ושה-System User משויך "
         "לחשבון ה-WhatsApp (Business Settings → System users → Assign assets).",
    10: "אין הרשאה לפעולה הזו. ודאו שה-System User משויך לחשבון ה-WhatsApp עם הרשאה לניהול תבניות.",
    3: "האפליקציה לא מורשית לפעולה. ודאו שמוצר WhatsApp מחובר לאפליקציה ב-developers.facebook.com.",
    4: "יותר מדי בקשות לאפליקציה. מחכים כמה דקות ומנסים שוב.",
    80008: "יותר מדי בקשות לחשבון ה-WhatsApp. מחכים ומנסים שוב מאוחר יותר.",
    100: "פרמטר לא תקין בבקשה. הפרטים מ-Meta למטה — בדרך כלל שם, שפה, משתנה בלי דוגמה או מבנה כפתור.",
    368: "החשבון חסום זמנית בגלל הפרת מדיניות. בודקים ב-WhatsApp Manager → Account quality.",
}

# הסבר לפי מילות מפתח בהודעה של Meta (כשהקוד הראשי כללי, כמו 100).
_KEYWORD_HELP = [
    ("already exists", "כבר קיימת תבנית בשם הזה ובשפה הזו. בוחרים שם אחר, או עורכים את הקיימת."),
    ("being deleted", "תבנית בשם הזה נמחקה לאחרונה, ו-Meta לא מאפשרת להשתמש בשם ובשפה עד שהמחיקה "
                      "מסתיימת (כמה שבועות). בוחרים שם אחר."),
    ("example", "חסר ערך דוגמה לאחד המשתנים (או לכפתור הקישור). לכל {{n}} צריך דוגמה."),
    ("sample", "חסר ערך דוגמה לאחד המשתנים. לכל {{n}} צריך דוגמה."),
    ("variable", "בעיה במשתנים: צריכים להיות ברצף {{1}}, {{2}}… ולא בתחילת הגוף או בסופו."),
    ("limit", "הגעתם למגבלה של Meta (מספר תבניות או מספר עריכות). הפרטים בהודעה של Meta."),
    ("category", "בעיה בקטגוריה. תבנית מאושרת לא משנה קטגוריה בעריכה."),
]

# סיבות דחייה של תבנית (rejected_reason).
REJECTION_HELP = {
    "INVALID_FORMAT": "המבנה לא תקין — לרוב משתנה בתחילת הגוף או בסופו, משתנים לא ברצף, "
                      "או יותר מדי משתנים ביחס לטקסט.",
    "PROMOTIONAL": "Meta זיהתה תוכן שיווקי בתבנית Utility. מורידים ניסוח שיווקי, או מגישים כ-Marketing.",
    "INCORRECT_CATEGORY": "הקטגוריה לא מתאימה לתוכן. מגישים מחדש בקטגוריה הנכונה.",
    "TAG_CONTENT_MISMATCH": "הקטגוריה לא מתאימה לתוכן. מגישים מחדש בקטגוריה הנכונה.",
    "ABUSIVE_CONTENT": "Meta סימנה את התוכן כפוגעני. משנים ניסוח ומגישים שוב.",
    "SCAM": "Meta חשדה בהונאה — לרוב קישור או ניסוח חשוד. בודקים את הקישור ואת הנוסח.",
    "NONE": "",
}

STATUS_HELP = {
    "APPROVED": "מאושרת — אפשר לשלוח אותה.",
    "PENDING": "ממתינה לאישור של Meta (לרוב דקות עד 24 שעות).",
    "REJECTED": "נדחתה. אפשר לערוך ולהגיש שוב.",
    "PAUSED": "מושהית בגלל משוב שלילי ממקבלים. אפשר לערוך, או לחכות שתחזור.",
    "DISABLED": "הושבתה בגלל משוב שלילי חוזר. צריך תבנית חדשה.",
    "IN_APPEAL": "בערעור.",
    "PENDING_DELETION": "בתהליך מחיקה.",
    "DELETED": "נמחקה.",
    "LIMIT_EXCEEDED": "חרגה ממגבלה של Meta.",
}


def explain_error(error: dict) -> dict:
    """שגיאת Meta (המבנה של ``error``) → מבנה מוסבר בעברית, בלי סודות."""
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    meta_text = " ".join(
        str(error.get(k) or "") for k in ("message", "error_user_title", "error_user_msg")
    ).strip()
    hints = []
    if code in ERROR_HELP:
        hints.append(ERROR_HELP[code])
    low = meta_text.lower()
    for word, hint in _KEYWORD_HELP:
        if word in low and hint not in hints:
            hints.append(hint)
    return scrub({
        "code": code,
        "subcode": error.get("error_subcode"),
        "meta_message": error.get("message"),
        "meta_user_title": error.get("error_user_title"),
        "meta_user_message": error.get("error_user_msg"),
        "fbtrace_id": error.get("fbtrace_id"),
        "explanation_he": " ".join(hints) or "שגיאה לא מוכרת — ההודעה של Meta למעלה.",
    })


# ---------------------------------------------------------------- HTTP

class MetaError(Exception):
    def __init__(self, info: dict):
        super().__init__(info.get("explanation_he") or "Meta error")
        self.info = info


def _request(method: str, path: str, *, params=None, json_body=None, content=None,
             headers=None, auth_scheme: str = "Bearer") -> dict:
    token = read_token()
    if not token:
        raise MetaError({
            "code": None,
            "explanation_he": "לא נמצא טוקן ב-Keychain (שירות veya-meta-templates). "
                              "ההוראות ב-tools/meta-templates-mcp/README.md.",
        })
    url = f"{GRAPH}/{GRAPH_VERSION}/{path.lstrip('/')}"
    hdrs = {"Authorization": f"{auth_scheme} {token}"}
    hdrs.update(headers or {})
    try:
        with httpx.Client(timeout=TIMEOUT, transport=_transport) as client:
            resp = client.request(method, url, params=params, json=json_body,
                                  content=content, headers=hdrs)
    except httpx.HTTPError as exc:
        raise MetaError({"code": None, "explanation_he":
                         f"לא ניתן להתחבר ל-Meta ({type(exc).__name__}). נסו שוב."})
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {}
    if resp.status_code >= 300 or (isinstance(body, dict) and "error" in body):
        err = body.get("error") if isinstance(body, dict) else None
        info = explain_error(err if isinstance(err, dict) else {"message": f"HTTP {resp.status_code}"})
        info["http_status"] = resp.status_code
        if info.get("code") == 190:
            forget_token()  # אולי הוחלף ב-Keychain — לקרוא מחדש בפעם הבאה
        raise MetaError(info)
    return scrub(body if isinstance(body, dict) else {})


def get(path, params=None):
    return _request("GET", path, params=params)


# ---------------------------------------------------------------- חיבור

def token_info() -> dict:
    """פרטי הטוקן (בלי הטוקן): תקף, סוג, תוקף, הרשאות, חשבונות WABA, מזהה אפליקציה."""
    data = get("debug_token", {"input_token": read_token()}).get("data", {})
    granular = data.get("granular_scopes") or []
    wabas: list[str] = []
    for g in granular:
        if g.get("scope") == REQUIRED_SCOPE:
            wabas.extend(g.get("target_ids") or [])
    exp = data.get("expires_at")
    scopes = data.get("scopes") or []
    return {
        "valid": bool(data.get("is_valid")),
        "type": data.get("type"),
        "app_id": data.get("app_id"),
        "app_name": data.get("application"),
        "expires": "never" if exp == 0 else (
            time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp)) if exp else None),
        "scopes": scopes,
        "has_required_scope": REQUIRED_SCOPE in scopes,
        "extra_scopes": [s for s in scopes if s not in (REQUIRED_SCOPE, "public_profile")],
        "waba_ids": sorted(set(wabas)),
    }


def resolve_waba(waba_id: Optional[str] = None) -> str:
    if waba_id:
        return str(waba_id)
    env = (os.getenv("VEYA_META_WABA_ID") or "").strip()
    if env:
        return env
    wabas = token_info()["waba_ids"]
    if len(wabas) == 1:
        return wabas[0]
    if not wabas:
        raise MetaError({"code": None, "explanation_he":
                         "הטוקן לא משויך לאף חשבון WhatsApp. ב-Business Settings → System users → "
                         "Assign assets → WhatsApp accounts, משייכים את החשבון של VEYA."})
    raise MetaError({"code": None, "explanation_he":
                     f"הטוקן משויך לכמה חשבונות WhatsApp ({len(wabas)}). מעבירים waba_id."})


def connection_status() -> dict:
    out: dict = {"keychain_token": bool(read_token()), "graph_version": GRAPH_VERSION}
    if not out["keychain_token"]:
        out["next_step_he"] = ("אין טוקן ב-Keychain. ההוראות ב-tools/meta-templates-mcp/README.md "
                               "(לא מדביקים טוקן בצ'אט).")
        return out
    if len(read_token()) == 128:
        out["warning_he"] = ("הטוקן ב-Keychain באורך 128 תווים בדיוק — כנראה נחתך בהדבקה "
                             "(macOS חותך שם קלט מוסתר ב-128). שומרים מחדש בפקודה שב-README.")
    try:
        info = token_info()
    except MetaError as exc:
        out["error"] = exc.info
        return out
    out["token"] = info
    warnings = []
    if not info["valid"]:
        warnings.append("הטוקן לא תקף.")
    if not info["has_required_scope"]:
        warnings.append("חסרה ההרשאה whatsapp_business_management.")
    if info["extra_scopes"]:
        warnings.append("לטוקן יש הרשאות מעבר לנדרש: " + ", ".join(info["extra_scopes"])
                        + ". לכלי הזה מספיקה whatsapp_business_management.")
    if info["expires"] not in ("never", None):
        warnings.append(f"הטוקן יפוג ב-{info['expires']}. עדיף טוקן System User עם תוקף Never.")
    accounts = []
    env_waba = (os.getenv("VEYA_META_WABA_ID") or "").strip()
    if not info["waba_ids"] and not env_waba:
        warnings.append("Meta לא מקשרת את הטוקן לחשבון מסוים — מגדירים VEYA_META_WABA_ID ב-.mcp.json.")
    for w in info["waba_ids"] or ([env_waba] if env_waba else []):
        acc = {"waba_id": w}
        try:
            acc.update(get(w, {"fields": "name,currency,timezone_id,account_review_status"}))
            phones = get(f"{w}/phone_numbers",
                         {"fields": "verified_name,display_phone_number,quality_rating,name_status"})
            acc["phone_numbers"] = [{
                "verified_name": p.get("verified_name"),
                "number_last4": (p.get("display_phone_number") or "")[-4:],
                "quality_rating": p.get("quality_rating"),
                "name_status": p.get("name_status"),
            } for p in phones.get("data", [])]
        except MetaError as exc:
            acc["error"] = exc.info
        accounts.append(acc)
    out["accounts"] = accounts
    out["warnings_he"] = warnings
    return out


# ---------------------------------------------------------------- קריאת תבניות

TEMPLATE_FIELDS = "id,name,language,status,category,components,rejected_reason,quality_score,parameter_format"


def fetch_templates(waba_id: Optional[str] = None, name: Optional[str] = None,
                    max_pages: int = 20) -> list[dict]:
    waba = resolve_waba(waba_id)
    params = {"limit": 100, "fields": TEMPLATE_FIELDS}
    if name:
        params["name"] = name  # Meta מסננת לפי הכלה, לא שוויון — מסננים שוב למטה
    out: list[dict] = []
    for _ in range(max_pages):
        page = get(f"{waba}/message_templates", params)
        out.extend(page.get("data", []))
        after = (page.get("paging") or {}).get("cursors", {}).get("after")
        if not after or not (page.get("paging") or {}).get("next"):
            break
        params = dict(params, after=after)
    return out


def variables_in(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\{\{\s*(\d+)\s*\}\}", text or "")]


def summarize(tpl: dict, full: bool = False) -> dict:
    """תבנית מ-Meta → תמצית קריאה: משתנים, Header, כפתורים, סטטוס מוסבר."""
    comps = {c.get("type"): c for c in tpl.get("components") or []}
    body = comps.get("BODY", {})
    header = comps.get("HEADER")
    buttons = (comps.get("BUTTONS") or {}).get("buttons") or []
    status = tpl.get("status")
    reason = tpl.get("rejected_reason")
    s = {
        "id": tpl.get("id"),
        "name": tpl.get("name"),
        "language": tpl.get("language"),
        "status": status,
        "status_he": STATUS_HELP.get(status or "", ""),
        "category": tpl.get("category"),
        "body_variables": len(set(variables_in(body.get("text", "")))),
        "header": (header or {}).get("format"),
        "buttons": [{
            "type": b.get("type"), "text": b.get("text"),
            "url": b.get("url"), "dynamic": bool(variables_in(b.get("url") or "")),
            # {{1}} שהוקלד בשדה של קישור קבוע (Static): Meta שומרת אותו מקודד, והכפתור
            # שולח את כולם לכתובת אחת שבורה.
            "literal_placeholder": "%7B%7B" in (b.get("url") or "").upper(),
        } for b in buttons],
    }
    if reason and reason != "NONE":
        s["rejected_reason"] = reason
        s["rejected_reason_he"] = REJECTION_HELP.get(reason, "")
    q = tpl.get("quality_score") or {}
    if q.get("score"):
        s["quality"] = q.get("score")
    if full:
        s["body_text"] = body.get("text")
        s["body_examples"] = ((body.get("example") or {}).get("body_text") or [[]])[0]
        if header:
            s["header_text"] = header.get("text")
        footer = comps.get("FOOTER")
        if footer:
            s["footer"] = footer.get("text")
        s["parameter_format"] = tpl.get("parameter_format")
        s["components_raw"] = tpl.get("components")
    return s


def find_template(templates: list[dict], name: str, language: Optional[str] = None) -> list[dict]:
    return [t for t in templates if t.get("name") == name
            and (language is None or t.get("language") == language)]


# ---------------------------------------------------------------- מה הקוד של VEYA מצפה

def code_expectations() -> list[dict]:
    """התבניות הקבועות שהקוד שולח (יום האירוע, שינוי מועד), רישום מפורש
    (``TEMPLATES``) וכלי הבדיקה (veya_inv_pilot). תבניות הספרייה — אחת לכל נוסח —
    נבדקות ב-``library_sync.check_sync``."""
    sys.path.insert(0, str(BACKEND))
    from app import whatsapp_meta, whatsapp_templates  # noqa: E402 — רק קבועים, בלי צד-לוואי

    out = []
    kinds = {"veya_event_day_table": "event_day", "veya_event_day": "event_day",
             "veya_postponement": "postponement", "veya_postponement_no_date": "postponement"}
    registered = list(whatsapp_templates.TEMPLATES.items()) + [
        (kinds[s.name], s) for s in whatsapp_templates.FIXED_TEMPLATES]
    for kind, spec in registered:
        for s in (spec, spec.with_image):
            if s is None:
                continue
            out.append({
                "name": s.name, "language": s.language, "kind": kind, "source": "code (TEMPLATES)",
                "body_variables": len(s.body_params), "body_params": list(s.body_params),
                "url_button": s.url_button, "header_image": s.header_image,
            })
    name, lang = whatsapp_meta.INV_PILOT
    out.append({
        "name": name, "language": lang, "kind": "test_tool", "source": "code (whatsapp_meta.INV_PILOT)",
        "body_variables": 1, "body_params": ["guest_name"], "url_button": True, "header_image": False,
    })
    return out


def doc_expectations(path: Path = TEMPLATES_DOC) -> dict[str, dict]:
    """הנוסחים המאושרים מ-docs/whatsapp-templates.md: שם → משתנים, כפתור, גוף."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"^### ", text, flags=re.M)[1:]
    out: dict[str, dict] = {}
    for sec in sections:
        heading = sec.splitlines()[0]
        names = re.findall(r"`(veya_[a-z0-9_]+)`", heading)
        names += re.findall(r"^\| `(veya_[a-z0-9_]+)` \|", sec, flags=re.M)
        if not names:
            continue
        m = re.search(r"^משתנים:(.*)$", sec, flags=re.M)
        params_line = m.group(1) if m else ""
        n_vars = len(re.findall(r"(\d+)=", params_line))
        bm = re.search(r"כפתור: \*\*(.+?)\*\*", params_line)
        no_button = "בלי כפתור" in params_line
        body = re.search(r"```\n(.*?)\n```", sec, flags=re.S)
        for n in dict.fromkeys(names):
            out[n] = {
                "body_variables": n_vars,
                "button_text": None if no_button else (bm.group(1) if bm else None),
                "url_button": (not no_button) and bool(bm),
                "body_text": body.group(1) if body else None,
            }
    return out


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def check_alignment(meta_templates: list[dict]) -> dict:
    """כל תבנית שהקוד או המסמך מצפים לה → קיימת? מאושרת? עברית? משתנים/כפתור/Header תואמים?"""
    docs = doc_expectations()
    code = {e["name"]: e for e in code_expectations()}
    names = list(dict.fromkeys(list(code) + list(docs)))
    results = []
    for name in names:
        exp = dict(docs.get(name, {}))
        exp.update({k: v for k, v in code.get(name, {}).items()})
        wired = name in code
        lang = exp.get("language", VEYA_LANGUAGE)
        problems, notes = [], []
        same_name = find_template(meta_templates, name)
        tpl = next((t for t in same_name if t.get("language") == lang), None)
        if tpl is None:
            if same_name:
                problems.append(f"קיימת ב-Meta רק בשפה {', '.join(t.get('language') for t in same_name)} "
                                f"— הקוד שולח '{lang}'.")
            else:
                (problems if wired else notes).append(
                    "לא קיימת ב-Meta." + ("" if wired else " (מתוכננת במסמך, עוד לא מחוברת בקוד)"))
            results.append({"name": name, "language": lang, "wired_in_code": wired,
                            "source": exp.get("source", "docs"), "exists": False,
                            "ok": not problems, "problems_he": problems, "notes_he": notes})
            continue
        s = summarize(tpl, full=True)
        if s["status"] != "APPROVED":
            (problems if wired else notes).append(f"סטטוס {s['status']}: {s['status_he']}")
        if "body_variables" in exp and s["body_variables"] != exp["body_variables"]:
            problems.append(f"בגוף ב-Meta יש {s['body_variables']} משתנים; "
                            f"הקוד/המסמך מעבירים {exp['body_variables']}.")
        want_header = exp.get("header_image", False)
        if want_header and s["header"] != "IMAGE":
            problems.append("הקוד שולח תמונה כ-Header, אבל בתבנית ב-Meta אין Header מסוג Image.")
        if not want_header and s["header"]:
            problems.append(f"בתבנית ב-Meta יש Header ({s['header']}) שהקוד לא ממלא.")
        url_buttons = [b for b in s["buttons"] if b["type"] == "URL"]
        first = s["buttons"][0] if s["buttons"] else None
        if exp.get("url_button"):
            if first and first.get("literal_placeholder"):
                problems.append(f"הכפתור הראשון הוא קישור קבוע (Static) שה-{{{{1}}}} נכתב בתוכו כטקסט "
                                f"({first['url']}). כל מוזמן יגיע לכתובת שבורה, ו-Meta תדחה את הקוד האישי "
                                "שהקוד שולח לכפתור. צריך כפתור מסוג Dynamic — תבנית חדשה או עריכה.")
            elif not first or first["type"] != "URL" or not first["dynamic"]:
                problems.append("הקוד שולח קישור אישי בכפתור הראשון (index 0), אבל הכפתור הראשון "
                                "ב-Meta אינו כפתור קישור דינמי.")
            elif first["url"] != VEYA_CONFIRM_URL:
                problems.append(f"כתובת הכפתור ב-Meta היא {first['url']} — מצופה {VEYA_CONFIRM_URL}.")
        elif any(b["dynamic"] for b in url_buttons):
            problems.append("בתבנית ב-Meta יש כפתור קישור דינמי, אבל הקוד/המסמך לא מעבירים לו ערך.")
        if exp.get("button_text") and first and first.get("text") != exp["button_text"]:
            problems.append(f"טקסט הכפתור ב-Meta '{first.get('text')}' — במסמך '{exp['button_text']}'.")
        if exp.get("body_text") and _norm(exp["body_text"]) != _norm(s["body_text"]):
            problems.append("נוסח הגוף ב-Meta שונה מהנוסח המאושר במסמך.")
        if s["category"] and s["category"] != "UTILITY":
            notes.append(f"קטגוריה {s['category']} (תוכנן Utility; משפיע על מחיר, לא חוסם).")
        results.append({
            "name": name, "language": lang, "wired_in_code": wired,
            "source": exp.get("source", "docs"), "exists": True, "status": s["status"],
            "category": s["category"], "ok": not problems,
            "problems_he": problems, "notes_he": notes,
        })
    extra = sorted({t.get("name") for t in meta_templates} - set(names))
    return {
        "graph_version": GRAPH_VERSION,
        "checked": results,
        "all_wired_ok": all(r["ok"] for r in results if r["wired_in_code"]),
        "in_meta_not_used_by_veya": extra,
    }


# ---------------------------------------------------------------- טיוטה ובדיקה מקומית

_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
# אמוג'י (טווחים עיקריים). 📅 מותר לפי המסמך.
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
ALLOWED_EMOJI = {"📅"}


def build_components(d: dict, header_handle: Optional[str] = None) -> list[dict]:
    """טיוטה שטוחה (כמו בכלי) → ``components`` בפורמט של Meta."""
    comps: list[dict] = []
    ht = (d.get("header_type") or "none").lower()
    if ht == "text":
        h = {"type": "HEADER", "format": "TEXT", "text": d.get("header_text", "")}
        if variables_in(h["text"]):
            h["example"] = {"header_text": [d.get("header_example", "")]}
        comps.append(h)
    elif ht == "image":
        comps.append({"type": "HEADER", "format": "IMAGE",
                      "example": {"header_handle": [header_handle or "<יועלה בשליחה>"]}})
    body = {"type": "BODY", "text": d.get("body", "")}
    if variables_in(body["text"]):
        body["example"] = {"body_text": [list(d.get("body_examples") or [])]}
    comps.append(body)
    if d.get("footer"):
        comps.append({"type": "FOOTER", "text": d["footer"]})
    btns = []
    for b in d.get("buttons") or []:
        t = (b.get("type") or "").lower()
        if t == "url":
            bb = {"type": "URL", "text": b.get("text", ""), "url": b.get("url", "")}
            if variables_in(bb["url"]):
                bb["example"] = [b.get("url_example", "")]
            btns.append(bb)
        elif t == "quick_reply":
            btns.append({"type": "QUICK_REPLY", "text": b.get("text", "")})
        elif t == "phone":
            btns.append({"type": "PHONE_NUMBER", "text": b.get("text", ""),
                         "phone_number": b.get("phone", "")})
        else:
            btns.append({"type": (b.get("type") or "?").upper(), "text": b.get("text", "")})
    if btns:
        comps.append({"type": "BUTTONS", "buttons": btns})
    return comps


def _check_vars(text: str, label: str, errors: list, max_vars: Optional[int] = None) -> int:
    nums = variables_in(text)
    uniq = sorted(set(nums))
    if uniq and uniq != list(range(1, len(uniq) + 1)):
        errors.append(f"{label}: המשתנים חייבים להיות ברצף מ-{{{{1}}}} (נמצא {uniq}).")
    if re.search(r"\{\{(?!\s*\d+\s*\}\})", text or ""):
        errors.append(f"{label}: משתנה לא תקין — רק {{{{1}}}}, {{{{2}}}}…")
    if max_vars is not None and len(uniq) > max_vars:
        errors.append(f"{label}: מותר עד {max_vars} משתנים.")
    return len(uniq)


def validate_draft(d: dict) -> dict:
    """בדיקה מקומית לפי הכללים של Meta + הכללים של VEYA. לא פונה ל-Meta."""
    errors, warnings = [], []
    name = d.get("name") or ""
    if not _NAME_RE.match(name):
        errors.append("שם: רק אותיות אנגליות קטנות, ספרות וקו תחתון (למשל veya_reminder_1).")
    lang = d.get("language") or VEYA_LANGUAGE
    if lang != VEYA_LANGUAGE:
        warnings.append(f"שפה '{lang}' — הקוד של VEYA שולח 'he'.")
    cat = (d.get("category") or "UTILITY").upper()
    if cat not in ("UTILITY", "MARKETING", "AUTHENTICATION"):
        errors.append("קטגוריה: UTILITY, MARKETING או AUTHENTICATION.")
    elif cat != "UTILITY":
        warnings.append(f"קטגוריה {cat} — התבניות של VEYA תוכננו כ-Utility.")

    body = d.get("body") or ""
    if not body.strip():
        errors.append("גוף ההודעה ריק.")
    if len(body) > 1024:
        errors.append(f"הגוף ארוך מדי ({len(body)} תווים; עד 1024).")
    n = _check_vars(body, "גוף", errors)
    stripped = body.strip()
    if re.match(r"^\{\{\s*\d+\s*\}\}", stripped) or re.search(r"\{\{\s*\d+\s*\}\}$", stripped):
        errors.append("גוף: Meta דוחה תבנית שמתחילה או נגמרת במשתנה. מוסיפים טקסט לפני/אחרי.")
    if re.search(r"\}\}\s*\{\{", body):
        warnings.append("גוף: שני משתנים צמודים — Meta נוטה לדחות.")
    if n and len(re.sub(r"\{\{\s*\d+\s*\}\}", "", body).split()) < n * 3:
        warnings.append("גוף: הרבה משתנים ביחס לטקסט — Meta עלולה לדחות (INVALID_FORMAT).")
    ex = list(d.get("body_examples") or [])
    if len(ex) != n:
        errors.append(f"דוגמאות: לגוף יש {n} משתנים ו-{len(ex)} דוגמאות. צריך דוגמה לכל משתנה, לפי הסדר.")
    for i, v in enumerate(ex, 1):
        v = str(v)
        if not v.strip():
            errors.append(f"דוגמה {i} ריקה.")
        if re.search(r"[\n\r\t]| {4}", v):
            errors.append(f"דוגמה {i}: בלי ירידת שורה, טאב או 4 רווחים.")
    bad_emoji = sorted(set(_EMOJI_RE.findall(body)) - ALLOWED_EMOJI)
    if bad_emoji:
        warnings.append("אמוג'י " + " ".join(bad_emoji) + " — לפי המסמך, רק 📅 ליד תאריך.")

    ht = (d.get("header_type") or "none").lower()
    if ht not in ("none", "text", "image"):
        errors.append("header_type: none / text / image.")
    if ht == "text":
        htxt = d.get("header_text") or ""
        if not htxt.strip() or len(htxt) > 60:
            errors.append("כותרת טקסט: חובה, עד 60 תווים.")
        if _check_vars(htxt, "כותרת", errors, max_vars=1) and not d.get("header_example"):
            errors.append("כותרת: חסרה דוגמה למשתנה.")
    if ht == "image":
        p = d.get("header_image_path")
        if not p:
            errors.append("Header תמונה: חסר header_image_path (קובץ JPEG/PNG מקומי, עד 5MB).")
        else:
            fp = Path(p).expanduser()
            if not fp.is_file():
                errors.append(f"קובץ התמונה לא נמצא: {p}")
            else:
                if fp.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    errors.append("תמונה: רק JPEG או PNG.")
                if fp.stat().st_size > 5 * 1024 * 1024:
                    errors.append("תמונה: עד 5MB.")
    footer = d.get("footer") or ""
    if footer:
        if len(footer) > 60:
            errors.append("Footer: עד 60 תווים.")
        if variables_in(footer):
            errors.append("Footer: בלי משתנים.")

    buttons = d.get("buttons") or []
    if len(buttons) > 10:
        errors.append("עד 10 כפתורים.")
    urls = [b for b in buttons if (b.get("type") or "").lower() == "url"]
    phones = [b for b in buttons if (b.get("type") or "").lower() == "phone"]
    if len(urls) > 2:
        errors.append("עד 2 כפתורי קישור.")
    if len(phones) > 1:
        errors.append("עד כפתור טלפון אחד.")
    for i, b in enumerate(buttons, 1):
        t = (b.get("type") or "").lower()
        txt = b.get("text") or ""
        if t not in ("url", "quick_reply", "phone"):
            errors.append(f"כפתור {i}: סוג url / quick_reply / phone.")
        if not txt.strip() or len(txt) > 25:
            errors.append(f"כפתור {i}: טקסט חובה, עד 25 תווים.")
        if t == "url":
            url = b.get("url") or ""
            if not url.startswith("https://"):
                errors.append(f"כפתור {i}: הקישור חייב להתחיל ב-https://")
            uv = variables_in(url)
            if uv:
                if uv != [1] or not re.search(r"\{\{\s*1\s*\}\}$", url):
                    errors.append(f"כפתור {i}: בקישור דינמי מותר משתנה אחד, {{{{1}}}}, בסוף הכתובת.")
                ue = b.get("url_example") or ""
                if not ue.startswith("https://"):
                    errors.append(f"כפתור {i}: חסרה דוגמה מלאה לקישור (url_example).")
                if url != VEYA_CONFIRM_URL:
                    warnings.append(f"כפתור {i}: הקישור האישי של VEYA הוא {VEYA_CONFIRM_URL}.")
        if t == "phone" and not re.match(r"^\+\d{8,15}$", b.get("phone") or ""):
            errors.append(f"כפתור {i}: מספר טלפון בפורמט בינלאומי (+972…).")
    if urls and (buttons[0].get("type") or "").lower() != "url":
        warnings.append("הקוד של VEYA ממלא את הקישור האישי בכפתור הראשון (index 0) — "
                        "כדאי שכפתור הקישור יהיה ראשון.")

    return {"ok": not errors, "errors_he": errors, "warnings_he": warnings,
            "body_variables": n, "category": cat, "language": lang}


# ---------------------------------------------------------------- טיוטות ממתינות

_drafts: dict[str, dict] = {}


def _draft_id(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return "d_" + hashlib.sha256(raw).hexdigest()[:12]


def _save_draft(kind: str, payload: dict, extra: dict) -> str:
    did = _draft_id({"kind": kind, **payload, **{k: str(v) for k, v in extra.items()}})
    _drafts[did] = {"kind": kind, "payload": payload, "created": time.time(), **extra}
    return did


def _take_draft(draft_id: str, kind: str, confirm_name: str) -> dict:
    d = _drafts.get(draft_id)
    if not d or d["kind"] != kind:
        raise MetaError({"code": None, "explanation_he":
                         "מזהה טיוטה לא מוכר (או שהשרת הופעל מחדש). מכינים שוב."})
    if time.time() - d["created"] > DRAFT_TTL:
        _drafts.pop(draft_id, None)
        raise MetaError({"code": None, "explanation_he": "הטיוטה פגה (30 דקות). מכינים שוב."})
    if confirm_name != d["name"]:
        raise MetaError({"code": None, "explanation_he":
                         f"האישור לא תואם: confirm צריך להיות בדיוק שם התבנית ({d['name']})."})
    return d


# ---------------------------------------------------------------- יצירה

def prepare_create(d: dict) -> dict:
    v = validate_draft(d)
    payload = {
        "name": d.get("name"), "language": d.get("language") or VEYA_LANGUAGE,
        "category": v["category"], "components": build_components(d),
    }
    out = {"validation": v, "payload_preview": payload, "touches_meta": False}
    if not v["ok"]:
        out["next_step_he"] = "יש שגיאות — מתקנים ומכינים שוב. שום דבר לא נשלח ל-Meta."
        return out
    waba = resolve_waba(d.get("waba_id"))
    existing = find_template(fetch_templates(waba, name=payload["name"]), payload["name"])
    same_lang = [t for t in existing if t.get("language") == payload["language"]]
    if same_lang:
        out["validation"]["ok"] = False
        out["validation"]["errors_he"].append(
            f"כבר קיימת תבנית {payload['name']} בשפה {payload['language']} "
            f"(סטטוס {same_lang[0].get('status')}). לעריכה — prepare_template_update.")
        return out
    did = _save_draft("create", payload, {"name": payload["name"], "waba": waba,
                                          "image": d.get("header_image_path") or ""})
    out["draft_id"] = did
    out["next_step_he"] = ("טיוטה מוכנה ולא נשלחה. להגשה ל-Meta: submit_template_create עם "
                           f"draft_id={did} ו-confirm={payload['name']} — רק אחרי אישור הבעלים.")
    return out


def _upload_header_image(path: str, app_id: str) -> str:
    """Resumable Upload API → header_handle לתבנית עם Header תמונה."""
    fp = Path(path).expanduser()
    data = fp.read_bytes()
    mime = "image/png" if fp.suffix.lower() == ".png" else "image/jpeg"
    sess = _request("POST", f"{app_id}/uploads",
                    params={"file_name": fp.name, "file_length": len(data), "file_type": mime})
    upload_id = sess.get("id")
    if not upload_id:
        raise MetaError({"code": None, "explanation_he": "Meta לא החזירה מזהה העלאה לתמונה."})
    res = _request("POST", upload_id, content=data, headers={"file_offset": "0"}, auth_scheme="OAuth")
    handle = res.get("h")
    if not handle:
        raise MetaError({"code": None, "explanation_he": "Meta לא החזירה מזהה לתמונה שהועלתה."})
    return handle


def submit_create(draft_id: str, confirm: str) -> dict:
    d = _take_draft(draft_id, "create", confirm)
    payload = json.loads(json.dumps(d["payload"]))
    if d.get("image"):
        handle = _upload_header_image(d["image"], token_info()["app_id"])
        for c in payload["components"]:
            if c.get("type") == "HEADER" and c.get("format") == "IMAGE":
                c["example"] = {"header_handle": [handle]}
    res = _request("POST", f"{d['waba']}/message_templates", json_body=payload)
    _drafts.pop(draft_id, None)
    status = res.get("status")
    return {"created": True, "id": res.get("id"), "name": d["name"], "status": status,
            "category_assigned_by_meta": res.get("category"),
            "status_he": STATUS_HELP.get(status or "", ""),
            "next_step_he": "לבדיקת האישור: get_template_status / check_veya_alignment."}


# ---------------------------------------------------------------- עריכה

EDITABLE_STATUSES = ("APPROVED", "REJECTED", "PAUSED")


def prepare_update(d: dict) -> dict:
    name = d.get("name") or ""
    lang = d.get("language") or VEYA_LANGUAGE
    if name in LOCKED_TEMPLATES and not d.get("override_lock"):
        raise MetaError({"code": None, "explanation_he":
                         f"{name} נעולה (החלטת המייסד: תבנית הניסוי נשארת כמו שהיא). "
                         "רק אם הבעלים ביקש במפורש — override_lock=true."})
    waba = resolve_waba(d.get("waba_id"))
    found = find_template(fetch_templates(waba, name=name), name, lang)
    if not found:
        raise MetaError({"code": None, "explanation_he": f"לא נמצאה תבנית {name} בשפה {lang}."})
    cur = found[0]
    v = validate_draft(dict(d, name=name, language=lang,
                            category=d.get("category") or cur.get("category")))
    notes = ["Meta בודקת שוב תבנית אחרי עריכה.",
             "שם ושפה לא משתנים בעריכה.",
             "לפי התיעוד של Meta: תבנית מאושרת נערכת עד פעם ב-24 שעות ועד 10 פעמים ב-30 יום, "
             "ובלי שינוי קטגוריה."]
    if cur.get("status") not in EDITABLE_STATUSES:
        v["ok"] = False
        v["errors_he"].append(f"אי אפשר לערוך תבנית בסטטוס {cur.get('status')} "
                              f"(רק {', '.join(EDITABLE_STATUSES)}).")
    new_cat = (d.get("category") or "").upper()
    payload: dict = {"components": build_components(d)}
    if new_cat and new_cat != cur.get("category"):
        if cur.get("status") == "APPROVED":
            v["ok"] = False
            v["errors_he"].append("תבנית מאושרת לא משנה קטגוריה. יוצרים תבנית חדשה.")
        else:
            payload["category"] = new_cat
    if name in {e["name"] for e in code_expectations()}:
        notes.insert(0, "התבנית מחוברת בקוד של VEYA — עד שהעריכה תאושר, ייתכן שלא תהיה זמינה לשליחה.")
    out = {"validation": v, "current": summarize(cur, full=True), "new_payload_preview": payload,
           "notes_he": notes, "touches_meta": False}
    if not v["ok"]:
        return out
    did = _save_draft("update", payload, {"name": name, "template_id": cur.get("id"),
                                          "image": d.get("header_image_path") or ""})
    out["draft_id"] = did
    out["next_step_he"] = (f"טיוטת עריכה מוכנה ולא נשלחה. להגשה: submit_template_update עם draft_id={did} "
                           f"ו-confirm={name} — רק אחרי אישור הבעלים.")
    return out


def submit_update(draft_id: str, confirm: str) -> dict:
    d = _take_draft(draft_id, "update", confirm)
    payload = json.loads(json.dumps(d["payload"]))
    if d.get("image"):
        handle = _upload_header_image(d["image"], token_info()["app_id"])
        for c in payload["components"]:
            if c.get("type") == "HEADER" and c.get("format") == "IMAGE":
                c["example"] = {"header_handle": [handle]}
    res = _request("POST", d["template_id"], json_body=payload)
    _drafts.pop(draft_id, None)
    return {"updated": bool(res.get("success")), "name": d["name"],
            "next_step_he": "לבדיקת האישור מחדש: get_template_status."}
