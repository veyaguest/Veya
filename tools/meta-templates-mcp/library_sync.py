"""סנכרון אחד-לאחד: ספריית הנוסחים של VEYA ↔ תבניות WhatsApp ב-Meta.

## מקור האמת
``GET /public/library`` בשרת של VEYA — אותן שורות ``MessageDefaultOption`` שהמוצר
משתמש בהן ושמהן נבנה דף הנוסחים באתר (``frontend/scripts/build-nuschim.mjs``).
כל נוסח (סוג אירוע × סוג הודעה × מספר סגנון) = תבנית אחת ב-Meta, בשם קבוע:
``veya_{אירוע}_{הודעה}_{סגנון}`` — למשל ``veya_wed_rem1_03``.

## ההמרה (כמו שהדף באתר מציג את הנוסח)
- ``{{guest_name}}`` וחבריו → ``{{1}}``, ``{{2}}``… לפי סדר ההופעה הראשונה.
- שורת ``{{rsvp_link}}`` → כפתור "אישור הגעה" (בהזמנה: "לצפייה בהזמנה"), ושורת התווית שלפניה
  ("לאישור הגעה:") יוצאת מהגוף — בדיוק כמו בדף. ``{{navigation_link}}`` → כפתור
  "ניווט למקום".
- **התבנית זהה לדף באתר, או שהיא לא נוצרת** (החלטת הבעלים 2026-10-19). Meta
  דוחה גוף שנגמר במשתנה (למשל חתימת השמות): נוסח כזה מסומן "צריך תיקון במקור"
  ולא נוצר — לא מוסיפים לו טקסט. מתקנים את הנוסח בספרייה, וכך האתר והתבנית
  משתנים יחד ונשארים זהים.

## כתיבה
רק ``prepare_batch`` (בדיקה, בלי לכתוב) ואז ``submit_batch`` עם האישור = מספר
התבניות במנה. שום מחיקה ושום עריכה מכאן.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter
from typing import Optional

import httpx

import veya_meta as vm

LIBRARY_URL = os.getenv("VEYA_LIBRARY_URL") or "https://veya-backend-u41w.onrender.com/public/library"
# תקרת התבניות לחשבון בלי אימות עסקי (WATI, נבדק 2026-10-19). ניתן לעקוף אחרי אימות.
TEMPLATE_CAP = int(os.getenv("VEYA_META_TEMPLATE_CAP") or 250)
BATCH_TTL = 30 * 60

EVENT_CODES = {"wedding": "wed", "henna": "henna", "bar_mitzvah": "barm", "bat_mitzvah": "batm",
               "brit": "brit", "brita": "brita", "business": "biz"}
MESSAGE_CODES = {"invitation": "inv", "rsvp_request": "rsvp", "reminder_1": "rem1",
                 "reminder_2": "rem2", "final_reminder": "rem3", "thank_you": "thx"}
# כמו בדף הנוסחים באתר (build-nuschim.mjs). בהזמנה הקישור האישי הוא "לצפייה בהזמנה":
# אישור ההגעה נפתח רק מהיום הראשון של אישורי ההגעה (החלטת הבעלים 2026-10-20).
BUTTONS = {"rsvp_link": "אישור הגעה", "navigation_link": "ניווט למקום"}
INVITATION_LINK_BUTTON = "לצפייה בהזמנה"
MAPS_URL = "https://www.google.com/maps/search/?api=1&query={{1}}"
SAMPLES = {"guest_name": "דנה", "host_names": "יונתן ושירה", "groom_name": "יונתן",
           "bride_name": "שירה", "event_date": "14/05/2026", "event_time": "19:30",
           "venue_name": "גן האירועים", "address": "הזורע 12, רמת גן"}
LINK_TOKENS = ("rsvp_link", "navigation_link", "maps_link", "gift_link")
_LINK_RE = re.compile(r"\{\{(%s)\}\}" % "|".join(LINK_TOKENS))
_LABEL_RE = re.compile(r"^.{0,32}:\s*$")
_ENDS_VAR = re.compile(r"\{\{\s*\w+\s*\}\}\s*$")

# נקודת החלפה לבדיקות.
_library_override: Optional[dict] = None


def fetch_library() -> dict:
    """הספרייה מהשרת של VEYA. בלי טוקן של Meta — זו בקשה ציבורית לשרת שלנו."""
    if _library_override is not None:
        return _library_override
    try:
        resp = httpx.get(LIBRARY_URL, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        raise vm.MetaError({"code": None, "explanation_he":
                            f"לא ניתן לקרוא את ספריית הנוסחים מהשרת של VEYA ({type(exc).__name__}). "
                            "ייתכן שהשרת ב-Render ישן — נסו שוב בעוד דקה."})


def wordings(lib: dict) -> list[dict]:
    return [w for c in lib.get("categories", []) for w in c.get("wordings", [])]


def template_name(w: dict) -> str:
    return f"veya_{EVENT_CODES[w['event_type']]}_{MESSAGE_CODES[w['message_type']]}_{int(w['option_number']):02d}"


def _split_links(content: str) -> tuple[str, list[str]]:
    """כמו ``render`` ב-build-nuschim.mjs: שורת קישור ושורת התווית שלפניה יוצאות."""
    links, kept = [], []
    for line in content.split("\n"):
        found = _LINK_RE.findall(line)
        if found:
            links += found
            if kept and kept[-1].strip() and _LABEL_RE.match(kept[-1].strip()):
                kept.pop()
            rest = _LINK_RE.sub("", line).strip()
            if rest and not _LABEL_RE.match(rest):
                kept.append(rest)
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), links


def to_draft(w: dict, category: str = "MARKETING") -> dict:
    """נוסח מהספרייה → טיוטת תבנית + מצב (ok / needs_source_fix / invalid)."""
    name = template_name(w)
    body, links = _split_links(w["content"])
    order: list[str] = []
    for t in re.findall(r"\{\{(\w+)\}\}", body):
        if t not in order:
            order.append(t)
    positional = body
    for i, t in enumerate(order, 1):
        positional = positional.replace("{{%s}}" % t, "{{%d}}" % i)
    buttons = []
    for ln in dict.fromkeys(links):
        if ln == "rsvp_link":
            text = INVITATION_LINK_BUTTON if w["message_type"] == "invitation" else BUTTONS[ln]
            buttons.append({"type": "url", "text": text, "url": vm.VEYA_CONFIRM_URL,
                            "url_example": "https://veyaguest.co.il/confirm/AbCdEf123456"})
        elif ln == "navigation_link":
            buttons.append({"type": "url", "text": BUTTONS[ln], "url": MAPS_URL,
                            "url_example": "https://www.google.com/maps/search/?api=1&query=Tel+Aviv"})
    draft = {"name": name, "language": "he", "category": category, "body": positional,
             "body_examples": [SAMPLES.get(t, "דוגמה") for t in order], "buttons": buttons}
    problems = []
    unknown = [t for t in order if t not in SAMPLES]
    if unknown:
        problems.append("משתנה שהכלי לא מכיר: " + ", ".join(unknown))
    unsupported = [ln for ln in links if ln not in BUTTONS]
    if unsupported:
        problems.append("קישור שאין לו כפתור: " + ", ".join(unsupported))
    v = vm.validate_draft(draft)
    errors = [e for e in v["errors_he"]]
    state = "ok"
    if _ENDS_VAR.search(positional):
        state = "needs_source_fix"
        problems.append("הנוסח נגמר במשתנה (למשל חתימת השמות), ו-Meta דוחה תבנית כזו. "
                        "מתקנים את הנוסח בספרייה כך שיסתיים בטקסט — והאתר והתבנית יישארו זהים.")
        errors = [e for e in errors if "מתחילה או נגמרת" not in e]
    if errors or unknown or unsupported:
        state = "invalid" if state == "ok" else state
    return {
        "name": name, "event_type": w["event_type"], "message_type": w["message_type"],
        "option_number": w["option_number"], "tone": w.get("tone"), "params": order,
        "draft": draft, "state": state,
        "problems_he": problems + errors,
    }


def _matches(want: dict, tpl: dict) -> list[str]:
    """מה שונה בין הטיוטה מהספרייה לתבנית ב-Meta (ריק = זהה)."""
    s = vm.summarize(tpl, full=True)
    diffs = []
    if vm._norm(s.get("body_text")) != vm._norm(want["body"]):
        diffs.append("נוסח הגוף שונה")
    want_btns = [(b["text"], b["url"]) for b in want["buttons"]]
    have_btns = [(b["text"], b["url"]) for b in s["buttons"]]
    if want_btns != have_btns:
        diffs.append(f"כפתורים שונים (בספרייה {want_btns}, ב-Meta {have_btns})")
    if s.get("header"):
        diffs.append(f"ב-Meta יש Header ({s['header']}) שאין בספרייה")
    return diffs


def _filter(items: list[dict], event_type: Optional[str], message_type: Optional[str]) -> list[dict]:
    return [d for d in items
            if (not event_type or d["event_type"] == event_type)
            and (not message_type or d["message_type"] == message_type)]


def check_sync(meta_templates: list[dict], lib: dict, event_type: Optional[str] = None,
               message_type: Optional[str] = None) -> dict:
    """השוואה אחד-לאחד. קריאה בלבד."""
    drafts = _filter([to_draft(w) for w in wordings(lib)], event_type, message_type)
    by_name = {}
    for t in meta_templates:
        if t.get("language") == "he":
            by_name[t.get("name")] = t
    rows = {"in_sync": [], "differs": [], "missing": [], "needs_source_fix": [], "invalid": []}
    for d in drafts:
        tpl = by_name.get(d["name"])
        if tpl is not None:
            diffs = _matches(d["draft"], tpl)
            rows["differs" if diffs else "in_sync"].append(
                {"name": d["name"], "status": tpl.get("status"), "category": tpl.get("category"),
                 **({"differences_he": diffs} if diffs else {})})
        elif d["state"] == "ok":
            rows["missing"].append(d["name"])
        else:
            rows[d["state"]].append({"name": d["name"], "problems_he": d["problems_he"]})
    lib_names = {d["name"] for d in [to_draft(w) for w in wordings(lib)]}
    pattern = re.compile(r"^veya_(%s)_(%s)_\d{2}$" % ("|".join(EVENT_CODES.values()),
                                                     "|".join(MESSAGE_CODES.values())))
    orphans = sorted(n for n in by_name if pattern.match(n or "") and n not in lib_names)
    statuses = Counter(r["status"] for r in rows["in_sync"])
    return {
        "library_total": len(drafts),
        "counts": {k: len(v) for k, v in rows.items()},
        "approved_in_sync": statuses.get("APPROVED", 0),
        "in_meta_not_in_library": orphans,
        "meta_template_count": len(meta_templates),
        "template_cap": TEMPLATE_CAP,
        "details": rows,
    }


# ---------------------------------------------------------------- מנות

_batches: dict[str, dict] = {}


def prepare_batch(event_type: Optional[str] = None, message_type: Optional[str] = None,
                  limit: Optional[int] = None, category: str = "MARKETING",
                  waba_id: Optional[str] = None) -> dict:
    """בודק ומכין מנה של תבניות חסרות. לא כותב ל-Meta."""
    category = (category or "MARKETING").upper()
    waba = vm.resolve_waba(waba_id)
    meta = vm.fetch_templates(waba)
    lib = fetch_library()
    report = check_sync(meta, lib, event_type, message_type)
    wanted = report["details"]["missing"]
    if limit:
        wanted = wanted[: int(limit)]
    drafts = {d["name"]: d for d in (to_draft(w, category) for w in wordings(lib))}
    out = {
        "touches_meta": False, "count": len(wanted), "category": category,
        "sync": {k: report[k] for k in ("library_total", "counts", "meta_template_count", "template_cap")},
        "not_included_he": {
            "needs_source_fix": [r["name"] for r in report["details"]["needs_source_fix"]],
            "invalid": report["details"]["invalid"],
            "differs (עריכה, לא יצירה)": [r["name"] for r in report["details"]["differs"]],
        },
    }
    if not wanted:
        out["next_step_he"] = "אין תבניות חסרות במסנן הזה."
        return out
    room = TEMPLATE_CAP - len(meta)
    if len(wanted) > room:
        out["error_he"] = (f"יש בחשבון {len(meta)} תבניות, והתקרה היא {TEMPLATE_CAP}. "
                           f"נשאר מקום ל-{max(room, 0)} — מקטינים את המנה (limit) או מסיימים אימות עסקי.")
        return out
    payloads = [{"name": n, "language": "he", "category": category,
                 "components": vm.build_components(drafts[n]["draft"])} for n in wanted]
    raw = json.dumps(payloads, sort_keys=True, ensure_ascii=False).encode()
    bid = "b_" + hashlib.sha256(raw).hexdigest()[:12]
    _batches[bid] = {"waba": waba, "payloads": payloads, "created": time.time()}
    out["batch_id"] = bid
    out["names"] = wanted
    out["preview"] = [{"name": n, "body": drafts[n]["draft"]["body"],
                       "params": drafts[n]["params"],
                       "buttons": [b["text"] for b in drafts[n]["draft"]["buttons"]]}
                      for n in wanted[:3]]
    out["next_step_he"] = (f"מנה של {len(wanted)} תבניות מוכנה ולא נשלחה. להגשה: submit_library_batch "
                           f"עם batch_id={bid} ו-confirm={len(wanted)} — רק אחרי אישור הבעלים.")
    return out


# קודים שאחריהם עוצרים את המנה (מגבלת קצב/הרשאה) — ממשיכים בפעם אחרת.
_STOP_CODES = {4, 10, 190, 200, 80008, 368}


def submit_batch(batch_id: str, confirm: str, pause: float = 0.5) -> dict:
    b = _batches.get(batch_id)
    if not b:
        raise vm.MetaError({"code": None, "explanation_he": "מזהה מנה לא מוכר (או שהשרת הופעל מחדש). מכינים שוב."})
    if time.time() - b["created"] > BATCH_TTL:
        _batches.pop(batch_id, None)
        raise vm.MetaError({"code": None, "explanation_he": "המנה פגה (30 דקות). מכינים שוב."})
    if str(confirm).strip() != str(len(b["payloads"])):
        raise vm.MetaError({"code": None, "explanation_he":
                            f"האישור לא תואם: confirm צריך להיות מספר התבניות במנה ({len(b['payloads'])})."})
    _batches.pop(batch_id, None)
    created, failed, not_sent = [], [], []
    for i, p in enumerate(b["payloads"]):
        try:
            res = vm._request("POST", f"{b['waba']}/message_templates", json_body=p)
            created.append({"name": p["name"], "status": res.get("status"), "category": res.get("category")})
        except vm.MetaError as exc:
            failed.append({"name": p["name"], "error": exc.info})
            if exc.info.get("code") in _STOP_CODES:
                not_sent = [q["name"] for q in b["payloads"][i + 1:]]
                break
        if pause:
            time.sleep(pause)
    return {
        "created": len(created), "failed": len(failed), "not_sent": len(not_sent),
        "categories": dict(Counter(c["category"] for c in created)),
        "created_list": created, "failed_list": failed, "not_sent_list": not_sent,
        "next_step_he": "לבדיקת אישור: check_library_sync." + (
            " חלק לא נשלח בגלל מגבלה של Meta — מכינים מנה חדשה מאוחר יותר." if not_sent else ""),
    }
