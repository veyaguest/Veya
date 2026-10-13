"""``scripts/whatsapp_webhook_probe.py`` — בלי רשת: מול האפליקציה בתוך הבדיקה.

מכסה: החתימה והמבנה הם בדיוק מה שהשרת מצפה לו (200 ו-"known=no"), שום נתון
לא משתנה, ה-wamid מדומה וייחודי, בלי ``--send`` אין שום בקשה, חסר משתנה מקומי —
לא שולח, והפלט לא מכיל את הסוד או את מזהה המספר המלא.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

SECRET = "probe-test-secret-" + "z" * 20
PNID = "100000000000077"
_NO_ENV = os.path.join(tempfile.gettempdir(), "veya-no-such-env-file.env")


def _with_env(**values):
    prev = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    return prev


def _restore(prev):
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_probe_is_accepted_by_the_webhook_and_changes_nothing() -> None:
    from app import models
    from app.database import SessionLocal
    from scripts import whatsapp_webhook_probe as probe

    api, _ = bootstrap()
    wamid = probe.new_probe_wamid()
    body = probe.encode(probe.build_payload(PNID, wamid, 1790000000))
    db = SessionLocal()
    try:
        before = db.scalar(select(func.count()).select_from(models.Message))
    finally:
        db.close()
    prev = _with_env(WHATSAPP_APP_SECRET=SECRET, WHATSAPP_WEBHOOK_PHONE_NUMBER_ID=PNID)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            r = api.client.post("/messaging/webhook", content=body, headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": probe.sign(body, SECRET)})
            wrong = api.client.post("/messaging/webhook", content=body, headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": probe.sign(body, "other-secret")})
    finally:
        _restore(prev)
    assert r.status_code == 200 and r.json() == {"received": True}
    assert wrong.status_code == 403
    assert "status delivered known=no" in buf.getvalue()
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(models.Message)) == before
        assert db.scalar(select(models.Message).where(models.Message.provider_message_id == wamid)) is None
    finally:
        db.close()
    print("✓ 1: חתימה ומבנה תואמים לשרת — 200, 'known=no', שום שורה לא השתנתה")


def test_probe_wamid_is_fake_and_unique() -> None:
    from scripts import whatsapp_webhook_probe as probe

    ids = {probe.new_probe_wamid() for _ in range(200)}
    assert len(ids) == 200
    assert all(i.startswith("wamid.VEYA-PROBE-") and not i.startswith("wamid.HBg") for i in ids)
    print("✓ 2: wamid מדומה (לא בפורמט של Meta) וייחודי בכל הרצה")


def test_dry_run_sends_nothing_and_prints_no_secrets() -> None:
    import httpx

    from scripts import whatsapp_webhook_probe as probe

    real_post = httpx.post

    def _no_network(*a, **k):
        raise AssertionError("dry-run לא אמור לשלוח")

    httpx.post = _no_network
    prev = _with_env(WHATSAPP_APP_SECRET=SECRET, WHATSAPP_WEBHOOK_PHONE_NUMBER_ID=PNID)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = probe.main(["--env-file", _NO_ENV])
    finally:
        httpx.post = real_post
        _restore(prev)
    out = buf.getvalue()
    assert code == 0 and "הצגה בלבד" in out
    assert SECRET not in out and PNID not in out and "***0077" in out
    assert probe.sign(b"x", SECRET)[7:] not in out
    print("✓ 3: בלי --send — שום בקשה; הפלט בלי הסוד, בלי החתימה, ומזהה המספר מצונזר")


def test_missing_local_values_refuse() -> None:
    import httpx

    from scripts import whatsapp_webhook_probe as probe

    real_post = httpx.post
    httpx.post = lambda *a, **k: (_ for _ in ()).throw(AssertionError("לא אמור לשלוח"))
    try:
        for env in ({"WHATSAPP_APP_SECRET": "", "WHATSAPP_WEBHOOK_PHONE_NUMBER_ID": PNID},
                    {"WHATSAPP_APP_SECRET": SECRET, "WHATSAPP_WEBHOOK_PHONE_NUMBER_ID": ""},
                    {"WHATSAPP_APP_SECRET": SECRET, "WHATSAPP_WEBHOOK_PHONE_NUMBER_ID": " , "}):
            prev = _with_env(**env)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = probe.main(["--send", "--env-file", _NO_ENV])
            finally:
                _restore(prev)
            assert code == 2 and "לא נשלח" in buf.getvalue(), env
            assert SECRET not in buf.getvalue()
    finally:
        httpx.post = real_post
    print("✓ 4: חסר סוד או מזהה מקומי — לא שולח (גם עם --send), בלי ערך ברירת מחדל")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("\n=== סקריפט בדיקת ה-webhook — עבר ===")
    finally:
        shutdown()
