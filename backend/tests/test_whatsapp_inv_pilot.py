"""כלי הבדיקה — תבנית הניסוי ``veya_inv_pilot`` (2026-10-15). מול Meta מזויפת, בלי רשת.

מכסה:
1. גוף הבקשה תואם לתבנית שאושרה: שם, שפה ``he``, ערך אחד לגוף (השם הפרטי),
   הקוד האישי לכפתור הראשון בלבד, בלי ערך לכפתור הניווט הקבוע.
2. אותם תנאי בטיחות של hello_world (mock / meta / production / לא ברשימה /
   רשימה ריקה / חסר טוקן / עצירת חירום) + שם וקוד תקינים — אחרת שום בקשה.
3. הסקריפט: בלי ``--send`` לא שולח; ``--send`` = בקשה אחת; לא מדפיס טוקן, טלפון
   או קוד אישי מלא; בלי ``--template`` נשאר hello_world.
4. התבנית לא מחוברת להזמנות — לא קיימת ב-``whatsapp_templates.TEMPLATES``.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import shutdown  # noqa: E402
from tests.test_whatsapp_meta_api import (  # noqa: E402
    _NO_ENV, TOKEN, FakeMeta, _captured, meta_env, ok,
)
from tests.test_whatsapp_safety import _phone  # noqa: E402

CODE = "AbCdEf123456"


def test_inv_pilot_payload_matches_approved_template() -> None:
    from app import whatsapp_meta as wm

    me = _phone()
    with meta_env(mode="meta_test", recipients=me, fake=FakeMeta(ok("wamid.pilot"))) as fake:
        check, res = wm.send_inv_pilot(me, " דנה ", CODE)
    assert check.ok and res.ok and len(fake.requests) == 1
    body = fake.bodies()[0]
    assert body["to"] == "972" + me[1:]
    assert body["template"] == {
        "name": "veya_inv_pilot", "language": {"code": "he"},
        "components": [
            {"type": "body", "parameters": [{"type": "text", "text": "דנה"}]},
            {"type": "button", "sub_type": "url", "index": "0",
             "parameters": [{"type": "text", "text": CODE}]},
        ],
    }
    assert body["biz_opaque_callback_data"] == "veya:inv_pilot"
    print("✓ 1: הבקשה תואמת לתבנית — he, שם בגוף, קוד בכפתור הראשון, בלי ערך לניווט")


def test_inv_pilot_refuses_like_hello_world_and_on_bad_values() -> None:
    from app import messaging
    from app import whatsapp_meta as wm

    me = _phone()
    refusals = {
        "mock": (dict(mode="mock", recipients=me), "דנה", CODE),
        "meta (לא בדיקה)": (dict(mode="meta", recipients=me), "דנה", CODE),
        "production": (dict(mode="meta_test", recipients=me, VEYA_ENV="production"), "דנה", CODE),
        "לא ברשימה": (dict(mode="meta_test", recipients=_phone()), "דנה", CODE),
        "רשימה ריקה": (dict(mode="meta_test", recipients=""), "דנה", CODE),
        "חסר טוקן": (dict(mode="meta_test", recipients=me, token=None), "דנה", CODE),
        "שם ריק": (dict(mode="meta_test", recipients=me), "  ", CODE),
        "ירידת שורה בשם": (dict(mode="meta_test", recipients=me), "דנה\nכהן", CODE),
        "4 רווחים בשם": (dict(mode="meta_test", recipients=me), "דנה    כהן", CODE),
        "קוד ריק": (dict(mode="meta_test", recipients=me), "דנה", ""),
        "קוד עם תווים זרים": (dict(mode="meta_test", recipients=me), "דנה", "abc/../x?y=1"),
        "קוד קצר": (dict(mode="meta_test", recipients=me), "דנה", "abc"),
    }
    for label, (kw, name, code) in refusals.items():
        with meta_env(**kw) as fake:
            check, res = wm.send_inv_pilot(me, name, code)
        assert not check.ok and res is None and fake.requests == [], label
    real_stop = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        with meta_env(mode="meta_test", recipients=me) as fake:
            check, res = wm.send_inv_pilot(me, "דנה", CODE)
        assert not check.ok and "עצירת החירום פעילה" in check.reasons and fake.requests == []
    finally:
        messaging.emergency_stop_active = real_stop
    print(f"✓ 2: שולח רק כשכל התנאים מתקיימים; {len(refusals) + 1} סירובים")


def test_inv_pilot_script_dry_run_send_and_no_leaks() -> None:
    from scripts import whatsapp_hello_world as script

    me = _phone()
    pilot = ["--to", me, "--template", "veya_inv_pilot", "--name", "דנה", "--code", CODE,
             "--env-file", _NO_ENV]
    with meta_env(mode="meta_test", recipients=me) as fake:
        code, out = _captured(lambda: script.main(pilot))
    assert code == 0 and fake.requests == [] and "בדיקה בלבד" in out and "veya_inv_pilot" in out
    for leak in (TOKEN, me, CODE, "1234567890"):
        assert leak not in out
    assert "***456" in out

    with meta_env(mode="meta_test", recipients=me, fake=FakeMeta(ok("wamid.s"))) as fake:
        code, out = _captured(lambda: script.main(pilot + ["--send"]))
    assert code == 0 and len(fake.requests) == 1
    assert fake.bodies()[0]["template"]["name"] == "veya_inv_pilot"
    assert TOKEN not in out and CODE not in out and me not in out

    # בלי --code — מסרב, גם עם --send.
    no_code = ["--to", me, "--template", "veya_inv_pilot", "--name", "דנה", "--send",
               "--env-file", _NO_ENV]
    with meta_env(mode="meta_test", recipients=me) as fake:
        code, out = _captured(lambda: script.main(no_code))
    assert code == 2 and fake.requests == [] and "--code" in out

    # בלי --template — hello_world כמו קודם.
    with meta_env(mode="meta_test", recipients=me, fake=FakeMeta(ok("wamid.h"))) as fake:
        code, _ = _captured(lambda: script.main(["--to", me, "--send", "--env-file", _NO_ENV]))
    assert code == 0 and fake.bodies()[0]["template"]["name"] == "hello_world"
    print("✓ 3: הסקריפט — בלי --send לא שולח; בלי דליפת טוקן/טלפון/קוד; ברירת המחדל hello_world")


def test_inv_pilot_is_not_wired_to_invitations() -> None:
    from app import whatsapp_templates

    names = {spec.name for spec in whatsapp_templates.TEMPLATES.values()}
    assert "veya_inv_pilot" not in names
    print("✓ 4: veya_inv_pilot לא מחוברת להזמנות (לא ב-TEMPLATES)")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("\n=== כלי הבדיקה — veya_inv_pilot — עבר ===")
    finally:
        shutdown()
