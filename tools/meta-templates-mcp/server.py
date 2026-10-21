"""שרת MCP מקומי לניהול תבניות WhatsApp של VEYA (stdio, JSON-RPC 2.0).

בלי תלויות מעבר ל-httpx שכבר בסביבה של ה-backend (ה-SDK הרשמי של MCP דורש
Python 3.10+, וה-venv על 3.9). הלוגיקה ב-``veya_meta.py``.

אין כאן כלי שליחה. כתיבה ל-Meta — רק ``submit_template_create`` /
``submit_template_update``, ורק עם טיוטה שהוכנה קודם ואישור בשם התבנית.

stdout שמור לפרוטוקול; לוגים (בלי סודות) ל-stderr.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import veya_meta as vm  # noqa: E402
import library_sync as ls  # noqa: E402

SERVER_INFO = {"name": "veya-meta-templates", "version": "0.1.0"}
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

_WABA = {"waba_id": {"type": "string", "description": "מזהה חשבון WhatsApp. ריק = מזוהה מהטוקן."}}

_DRAFT_PROPS = {
    "name": {"type": "string", "description": "שם התבנית: a-z, 0-9, _ (למשל veya_reminder_1)"},
    "language": {"type": "string", "default": "he"},
    "category": {"type": "string", "enum": ["UTILITY", "MARKETING", "AUTHENTICATION"], "default": "UTILITY"},
    "body": {"type": "string", "description": "גוף ההודעה עם {{1}}, {{2}}…"},
    "body_examples": {"type": "array", "items": {"type": "string"},
                      "description": "ערך דוגמה לכל משתנה בגוף, לפי הסדר"},
    "header_type": {"type": "string", "enum": ["none", "text", "image"], "default": "none"},
    "header_text": {"type": "string"},
    "header_example": {"type": "string"},
    "header_image_path": {"type": "string", "description": "קובץ JPEG/PNG מקומי עד 5MB (header_type=image)"},
    "footer": {"type": "string"},
    "buttons": {"type": "array", "items": {"type": "object", "properties": {
        "type": {"type": "string", "enum": ["url", "quick_reply", "phone"]},
        "text": {"type": "string"},
        "url": {"type": "string", "description": "לקישור האישי: https://veyaguest.co.il/confirm/{{1}}"},
        "url_example": {"type": "string"},
        "phone": {"type": "string"},
    }, "required": ["type", "text"]}},
    **_WABA,
}

TOOLS = [
    {
        "name": "meta_connection_status",
        "description": "בודק את החיבור ל-Meta: האם יש טוקן ב-Keychain, האם תקף, הרשאות (והאם יש "
                       "מיותרות), תוקף, חשבונות WhatsApp ומספרים (4 ספרות אחרונות בלבד). קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {}},
        "readOnlyHint": True,
    },
    {
        "name": "list_templates",
        "description": "מציג את התבניות בחשבון WhatsApp: שם, שפה, סטטוס אישור, קטגוריה, משתנים, "
                       "כפתורים. סינון אופציונלי. קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "string", "description": "APPROVED / PENDING / REJECTED / PAUSED…"},
            "name_contains": {"type": "string"},
            "language": {"type": "string"},
            **_WABA,
        }},
        "readOnlyHint": True,
    },
    {
        "name": "get_template",
        "description": "פרטים מלאים של תבנית: נוסח, משתנים ודוגמאות, Header, כפתורים, סטטוס וסיבת "
                       "דחייה מוסברת. קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string"}, "language": {"type": "string"}, **_WABA,
        }, "required": ["name"]},
        "readOnlyHint": True,
    },
    {
        "name": "get_template_status",
        "description": "סטטוס האישור של תבנית אחת (או כמה, מופרדים בפסיק) עם הסבר בעברית. קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {
            "names": {"type": "string", "description": "שם אחד או כמה, מופרדים בפסיק"}, **_WABA,
        }, "required": ["names"]},
        "readOnlyHint": True,
    },
    {
        "name": "check_veya_alignment",
        "description": "משווה את התבניות ב-Meta למה שהקוד של VEYA שולח (whatsapp_templates.TEMPLATES, "
                       "veya_inv_pilot) ולנוסחים המאושרים ב-docs/whatsapp-templates.md: קיימת, מאושרת, "
                       "שפה he, מספר משתנים, Header תמונה, כפתור קישור אישי בכפתור הראשון, נוסח. קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {**_WABA}},
        "readOnlyHint": True,
    },
    {
        "name": "validate_template_draft",
        "description": "בודק טיוטת תבנית מקומית לפי הכללים של Meta ושל VEYA. לא פונה ל-Meta בכלל.",
        "inputSchema": {"type": "object", "properties": _DRAFT_PROPS, "required": ["name", "body"]},
        "readOnlyHint": True,
    },
    {
        "name": "prepare_template_create",
        "description": "מכין יצירת תבנית: בודק, מוודא שהשם פנוי (קריאה מ-Meta), ומחזיר תצוגה ו-draft_id. "
                       "לא יוצר כלום ב-Meta.",
        "inputSchema": {"type": "object", "properties": _DRAFT_PROPS, "required": ["name", "body"]},
        "readOnlyHint": True,
    },
    {
        "name": "submit_template_create",
        "description": "כותב ל-Meta: מגיש לאישור תבנית שהוכנה ב-prepare_template_create. לקרוא רק אחרי "
                       "שהבעלים ראה את התצוגה ואישר במפורש בצ'אט. confirm = שם התבנית בדיוק.",
        "inputSchema": {"type": "object", "properties": {
            "draft_id": {"type": "string"}, "confirm": {"type": "string"},
        }, "required": ["draft_id", "confirm"]},
        "destructiveHint": False,
    },
    {
        "name": "prepare_template_update",
        "description": "מכין עריכה של תבנית קיימת (רק APPROVED / REJECTED / PAUSED): מציג את הנוכחית "
                       "מול החדשה, מגבלות Meta, ו-draft_id. לא משנה כלום ב-Meta. הטיוטה מחליפה את "
                       "כל הרכיבים — מעבירים גוף, כפתורים ו-Header מלאים.",
        "inputSchema": {"type": "object", "properties": {
            **_DRAFT_PROPS,
            "override_lock": {"type": "boolean", "description": "רק אם הבעלים ביקש לערוך תבנית נעולה"},
        }, "required": ["name", "body"]},
        "readOnlyHint": True,
    },
    {
        "name": "submit_template_update",
        "description": "כותב ל-Meta: מגיש עריכה שהוכנה ב-prepare_template_update. לקרוא רק אחרי אישור "
                       "מפורש של הבעלים בצ'אט. confirm = שם התבנית בדיוק.",
        "inputSchema": {"type": "object", "properties": {
            "draft_id": {"type": "string"}, "confirm": {"type": "string"},
        }, "required": ["draft_id", "confirm"]},
        "destructiveHint": True,
    },
    {
        "name": "check_library_sync",
        "description": "משווה אחד-לאחד את ספריית הנוסחים של VEYA (אותם נוסחים שבדף veyaguest.co.il/nuschim) "
                       "לתבניות ב-Meta: זהות, שונות, חסרות, וכאלה שצריכות תיקון בספרייה כדי להיות זהות. "
                       "סינון לפי סוג אירוע/הודעה. קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {
            "event_type": {"type": "string", "enum": list(ls.EVENT_CODES)},
            "message_type": {"type": "string", "enum": list(ls.MESSAGE_CODES)},
            **_WABA,
        }},
        "readOnlyHint": True,
    },
    {
        "name": "prepare_library_batch",
        "description": "מכין מנה של תבניות חסרות מהספרייה (זהות לדף באתר), כולל גרסת תמונה לכל הזמנה, "
                       "בודק את תקרת התבניות, ומחזיר batch_id ותצוגה. לא יוצר כלום ב-Meta.",
        "inputSchema": {"type": "object", "properties": {
            "event_type": {"type": "string", "enum": list(ls.EVENT_CODES)},
            "message_type": {"type": "string", "enum": list(ls.MESSAGE_CODES)},
            "limit": {"type": "integer"},
            "category": {"type": "string", "enum": ["AUTO", "UTILITY", "MARKETING"], "default": "AUTO",
                         "description": "AUTO = הזמנה שיווקית, השאר שירות"},
            **_WABA,
        }},
        "readOnlyHint": True,
    },
    {
        "name": "submit_library_batch",
        "description": "כותב ל-Meta: מגיש את המנה שהוכנה. לקרוא רק אחרי אישור מפורש של הבעלים בצ'אט. "
                       "confirm = מספר התבניות במנה.",
        "inputSchema": {"type": "object", "properties": {
            "batch_id": {"type": "string"}, "confirm": {"type": "string"},
        }, "required": ["batch_id", "confirm"]},
        "destructiveHint": False,
    },
    {
        "name": "explain_meta_error",
        "description": "מסביר בעברית שגיאה של Meta (קוד, או סיבת דחייה כמו INVALID_FORMAT) ואיך לתקן.",
        "inputSchema": {"type": "object", "properties": {
            "code": {"type": "integer"}, "message": {"type": "string"},
            "rejected_reason": {"type": "string"},
        }},
        "readOnlyHint": True,
    },
]


def _tool_defs():
    out = []
    for t in TOOLS:
        d = {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
        ann = {k: t[k] for k in ("readOnlyHint", "destructiveHint") if k in t}
        if ann:
            d["annotations"] = ann
        out.append(d)
    return out


# ---------------------------------------------------------------- מימוש הכלים

def t_list_templates(a):
    items = [vm.summarize(t) for t in vm.fetch_templates(a.get("waba_id"))]
    if a.get("status"):
        items = [i for i in items if i["status"] == a["status"].upper()]
    if a.get("name_contains"):
        items = [i for i in items if a["name_contains"] in (i["name"] or "")]
    if a.get("language"):
        items = [i for i in items if i["language"] == a["language"]]
    return {"count": len(items), "templates": items}


def t_get_template(a):
    found = vm.find_template(vm.fetch_templates(a.get("waba_id"), name=a["name"]),
                             a["name"], a.get("language"))
    if not found:
        return {"found": False, "name": a["name"]}
    return {"found": True, "templates": [vm.summarize(t, full=True) for t in found]}


def t_get_template_status(a):
    names = [n.strip() for n in a["names"].split(",") if n.strip()]
    all_t = vm.fetch_templates(a.get("waba_id"))
    out = []
    for n in names:
        found = vm.find_template(all_t, n)
        if not found:
            out.append({"name": n, "exists": False})
        for t in found:
            s = vm.summarize(t)
            out.append({k: s.get(k) for k in ("name", "language", "status", "status_he", "category",
                                               "rejected_reason", "rejected_reason_he", "quality")
                        if s.get(k) is not None})
    return {"templates": out}


def t_check_alignment(a):
    return vm.check_alignment(vm.fetch_templates(a.get("waba_id")))


def t_explain(a):
    out = vm.explain_error({"code": a.get("code"), "message": a.get("message") or ""}) \
        if a.get("code") is not None or a.get("message") else {}
    r = (a.get("rejected_reason") or "").upper()
    if r:
        out["rejected_reason"] = r
        out["rejected_reason_he"] = vm.REJECTION_HELP.get(r, "סיבה לא מוכרת — בודקים ב-WhatsApp Manager.")
    return out


HANDLERS = {
    "meta_connection_status": lambda a: vm.connection_status(),
    "list_templates": t_list_templates,
    "get_template": t_get_template,
    "get_template_status": t_get_template_status,
    "check_veya_alignment": t_check_alignment,
    "validate_template_draft": vm.validate_draft,
    "prepare_template_create": vm.prepare_create,
    "submit_template_create": lambda a: vm.submit_create(a["draft_id"], a["confirm"]),
    "prepare_template_update": vm.prepare_update,
    "submit_template_update": lambda a: vm.submit_update(a["draft_id"], a["confirm"]),
    "explain_meta_error": t_explain,
    "check_library_sync": lambda a: ls.check_sync(vm.fetch_templates(a.get("waba_id")), ls.fetch_library(),
                                                  a.get("event_type"), a.get("message_type")),
    "prepare_library_batch": lambda a: ls.prepare_batch(a.get("event_type"), a.get("message_type"),
                                                        a.get("limit"), a.get("category") or "AUTO",
                                                        a.get("waba_id")),
    "submit_library_batch": lambda a: ls.submit_batch(a["batch_id"], a["confirm"]),
}


def call_tool(name, args):
    handler = HANDLERS.get(name)
    if handler is None:
        return {"content": [{"type": "text", "text": f"כלי לא מוכר: {name}"}], "isError": True}
    try:
        result, is_error = handler(args or {}), False
    except vm.MetaError as exc:
        result, is_error = {"error": exc.info}, True
    except KeyError as exc:
        result, is_error = {"error": {"explanation_he": f"חסר פרמטר: {exc}"}}, True
    except Exception as exc:  # noqa: BLE001
        print("[veya-meta-templates] " + vm.scrub(traceback.format_exc()), file=sys.stderr, flush=True)
        result, is_error = {"error": {"explanation_he": f"שגיאה פנימית בכלי ({type(exc).__name__})."}}, True
    text = json.dumps(vm.scrub(result), ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


# ---------------------------------------------------------------- פרוטוקול

def handle(msg):
    """הודעת JSON-RPC אחת → תשובה (או None להתראות)."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # notification (למשל notifications/initialized)
    if method == "initialize":
        req = (msg.get("params") or {}).get("protocolVersion")
        version = req if req in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": SERVER_INFO,
                  "instructions": "ניהול תבניות WhatsApp של VEYA דרך Meta. אין כלי שליחה. "
                                  "submit_* כותבים ל-Meta — רק אחרי אישור מפורש של הבעלים בצ'אט."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _tool_defs()}
    elif method == "tools/call":
        p = msg.get("params") or {}
        result = call_tool(p.get("name"), p.get("arguments"))
    else:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            out = handle(msg) if isinstance(msg, dict) else None
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
