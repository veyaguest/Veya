"""הזמנה עם תמונת האירוע (2026-10-15) — מול Meta מזויפת, בלי רשת.

מכסה:
1. לאירוע עם תמונה: העלאה אחת ל-Meta למנה (JPEG), אותו מזהה לכל המוזמנים,
   ``veya_invitation_image`` עם Header תמונה, ערכים וקוד אישי בכפתור.
2. לאירוע בלי תמונה: ``veya_invitation`` בלי Header ובלי העלאה.
3. תמונה שאי אפשר להמיר (SVG / חסרה במסד) — שום בקשה ושום שורה; חסימה.
4. העלאה נכשלה — אף הודעה לא יוצאת ואף שורה לא נרשמת; מנה מאוחרת יותר יוצאת.
5. לכל אירוע התמונה שלו — גם כשאותו מופע ספק משמש שני אירועים.
6. שגיאת מדיה בשליחה (מזהה פג) — העלאה מחדש לפני ההודעה הבאה; אם גם היא
   נכשלת — ההודעות הבאות לא יוצאות בלי תמונה.
7. ההמרה: WebP/PNG → JPEG עד 5MB; SVG/מונפש נחסמים; מה ששמור לא משתנה.
8. שליחת ההזמנות מהמסך — 409 עם הסבר ("JPEG או PNG") כשהתמונה נחסמת.
9. כלי הבדיקה — בלי ``--send`` לא מעלה ולא שולח; עם ``--send``: העלאה + הודעה.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_meta_api import (  # noqa: E402
    _NO_ENV, TOKEN, FakeMeta, _captured, err, meta_env, ok,
)
from tests.test_whatsapp_safety import _db, _engine, _event, _guest, _phone  # noqa: E402


import pytest  # noqa: E402


def _register_invitation_templates() -> dict:
    """המסלול של התמונה נבדק כאן מול תבנית הזמנה רשומה במפורש (``TEMPLATES``) —
    מאז 2026-10-20 התבנית נבחרת לפי הנוסח מהספרייה (``test_whatsapp_library_routing``),
    אבל ההעלאה, ההמרה והחסימה זהות לכל תבנית עם Header תמונה."""
    from app import whatsapp_templates as wt

    saved = dict(wt.TEMPLATES)
    params = ("guest_name", "event_type", "host_names", "event_date")
    wt.TEMPLATES["invitation"] = wt.TemplateSpec(
        name="veya_invitation", body_params=params, url_button=True,
        with_image=wt.TemplateSpec(name="veya_invitation_image", body_params=params,
                                   url_button=True, header_image=True),
    )
    return saved


@pytest.fixture(autouse=True)
def _invitation_templates():
    from app import whatsapp_templates as wt

    saved = _register_invitation_templates()
    yield
    wt.TEMPLATES.clear()
    wt.TEMPLATES.update(saved)


def _image_bytes(color=(200, 30, 30), fmt="WEBP", size=(600, 800)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _uploaded(media_id: str):
    return 200, {"id": media_id}


def _store_image(db: Session, data: bytes, content_type: str, blob_id: str) -> str:
    from app import models

    db.add(models.MediaBlob(id=blob_id, content_type=content_type, data=data))
    db.commit()
    return f"/media/{blob_id}"


def _setup(db: Session, n_guests=3, image=None, content_type="image/webp", blob_id=None):
    from app import outbound

    ev = _event(db)
    if image is not None:
        ev.invite_image = _store_image(db, image, content_type, blob_id or f"inv-{ev.id}")
        db.commit()
    phones = [_phone() for _ in range(n_guests)]
    guests = [_guest(db, ev.id, p, name=f"אורח{i} בדיקה") for i, p in enumerate(phones)]
    items = [outbound.OutboundItem(guest=g, phone=g.phone, text="x", kind="invitation") for g in guests]
    return ev, guests, items, phones


def _split(fake):
    uploads = [r for r in fake.requests if r.url.path.endswith("/media")]
    messages = [r for r in fake.requests if r.url.path.endswith("/messages")]
    import json

    return uploads, [json.loads(r.content) for r in messages]


def _rows(db: Session, event_id: int):
    from app import models

    return db.scalars(select(models.Message).where(models.Message.event_id == event_id)
                      .order_by(models.Message.id)).all()


def _header_id(body: dict):
    comps = body["template"].get("components", [])
    header = [c for c in comps if c["type"] == "header"]
    return header[0]["parameters"][0]["image"]["id"] if header else None


def test_image_uploaded_once_and_reused_for_every_guest() -> None:
    from app import outbound

    db = Session(_engine())
    ev, guests, items, phones = _setup(db, image=_image_bytes())
    fake = FakeMeta(_uploaded("MEDIA-A"), ok("wamid.1"), ok("wamid.2"), ok("wamid.3"))
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=fake):
        result = outbound.send_batch(db, ev, items)
        db.commit()
    uploads, bodies = _split(fake)
    assert len(uploads) == 1 and result.sent == 3 and result.image_blocked == 0
    up = uploads[0]
    up.read()
    assert b"\xff\xd8\xff" in up.content, "הועלה JPEG (לא ה-WebP השמור)"
    for g, body in zip(guests, bodies):
        assert body["template"]["name"] == "veya_invitation_image"
        assert _header_id(body) == "MEDIA-A"
        comps = {c["type"]: c for c in body["template"]["components"]}
        assert [p["text"] for p in comps["body"]["parameters"]] == [
            g.full_name.split()[0], "חתונה", "יואב ודנה", "08/09/2026"]
        assert comps["button"]["parameters"][0]["text"] == g.guest_token
    rows = _rows(db, ev.id)
    assert [r.status for r in rows] == ["sent"] * 3
    assert all("[תמונת ההזמנה]" in r.body and "veya_invitation_image" in r.body for r in rows)
    print("✓ 1: העלאה אחת למנה, אותו מזהה ל-3 מוזמנים, JPEG, ערכים וקוד בכפתור")


def test_event_without_image_uses_text_template() -> None:
    from app import outbound

    db = Session(_engine())
    ev, guests, items, phones = _setup(db, n_guests=2)
    fake = FakeMeta(ok("wamid.1"), ok("wamid.2"))
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=fake):
        result = outbound.send_batch(db, ev, items)
        db.commit()
    uploads, bodies = _split(fake)
    assert uploads == [] and result.sent == 2
    assert all(b["template"]["name"] == "veya_invitation" and _header_id(b) is None for b in bodies)
    print("✓ 2: בלי תמונה — veya_invitation, בלי Header ובלי העלאה")


def test_unsupported_or_missing_image_blocks_everything() -> None:
    from app import outbound, whatsapp_templates

    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    cases = {
        "SVG": dict(image=svg, content_type="image/svg+xml"),
        "GIF": dict(image=_image_bytes(fmt="GIF"), content_type="image/gif"),
    }
    for label, kw in cases.items():
        db = Session(_engine())
        ev, guests, items, phones = _setup(db, **kw)
        with meta_env(mode="meta_test", recipients=",".join(phones)) as fake:
            result = outbound.send_batch(db, ev, items)
            db.commit()
        assert fake.requests == [] and _rows(db, ev.id) == [], label
        assert (result.image_blocked, result.image_reason) == (3, whatsapp_templates.IMAGE_UNSUPPORTED)
        assert result.sent == result.failed == 0
    # התמונה רשומה על האירוע אבל לא קיימת במסד.
    db = Session(_engine())
    ev, guests, items, phones = _setup(db)
    ev.invite_image = "/media/does-not-exist"
    db.commit()
    with meta_env(mode="meta_test", recipients=",".join(phones)) as fake:
        result = outbound.send_batch(db, ev, items)
    assert fake.requests == [] and result.image_reason == whatsapp_templates.IMAGE_UNSUPPORTED
    print("✓ 3: SVG / GIF / תמונה חסרה — שום בקשה ושום שורה; לא נופלים לנוסח בלי תמונה")


def test_upload_failure_blocks_batch_and_round_is_not_consumed() -> None:
    from app import outbound, whatsapp_templates

    db = Session(_engine())
    ev, guests, items, phones = _setup(db, image=_image_bytes())
    with meta_env(mode="meta_test", recipients=",".join(phones),
                  fake=FakeMeta(err(100, "Invalid parameter"))) as fake:
        result = outbound.send_batch(db, ev, items)
        db.commit()
    uploads, bodies = _split(fake)
    assert len(uploads) == 1 and bodies == [] and _rows(db, ev.id) == []
    assert (result.image_blocked, result.image_reason) == (3, whatsapp_templates.IMAGE_UNAVAILABLE)
    # timeout בהעלאה — גם הוא "לא הועלתה" (לא "לא ידוע"): לא נשלח כלום.
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=FakeMeta("timeout")) as fake:
        result = outbound.send_batch(db, ev, items)
    assert _split(fake)[1] == [] and result.image_blocked == 3
    # מנה מאוחרת יותר, כשההעלאה מצליחה — יוצאת לכולם.
    fake = FakeMeta(_uploaded("MEDIA-LATER"), ok("w1"), ok("w2"), ok("w3"))
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=fake):
        result = outbound.send_batch(db, ev, items)
        db.commit()
    assert result.sent == 3 and all(_header_id(b) == "MEDIA-LATER" for b in _split(fake)[1])
    print("✓ 4: העלאה נכשלה (שגיאה / timeout) — אף הודעה ואף שורה; מנה מאוחרת יוצאת")


def test_each_event_gets_its_own_image_even_with_shared_provider() -> None:
    from app import messaging, outbound

    db = Session(_engine())
    ev_a, _, items_a, phones_a = _setup(db, n_guests=1, image=_image_bytes((255, 0, 0)), blob_id="img-a")
    ev_b, _, items_b, phones_b = _setup(db, n_guests=1, image=_image_bytes((0, 0, 255)), blob_id="img-b")
    fake = FakeMeta(_uploaded("MEDIA-A"), ok("wa"), _uploaded("MEDIA-B"), ok("wb"))
    with meta_env(mode="meta", fake=fake):
        provider = messaging.MetaProvider()  # אותו מופע לשני האירועים — הגנה כפולה
        outbound.send_batch(db, ev_a, items_a, provider=provider)
        outbound.send_batch(db, ev_b, items_b, provider=provider)
        db.commit()
    uploads, bodies = _split(fake)
    assert len(uploads) == 2
    assert [_header_id(b) for b in bodies] == ["MEDIA-A", "MEDIA-B"]
    assert bodies[0]["to"] == "972" + phones_a[0][1:] and bodies[1]["to"] == "972" + phones_b[0][1:]
    # התמונה שהועלתה לאירוע ב' היא התמונה של ב' (כחולה), לא של א'.
    for up, expected in zip(uploads, ((255, 0, 0), (0, 0, 255))):
        up.read()
        start = up.content.index(b"\xff\xd8\xff")
        end = up.content.index(b"\xff\xd9", start) + 2
        pixel = Image.open(io.BytesIO(up.content[start:end])).convert("RGB").getpixel((5, 5))
        assert all(abs(a - b) < 40 for a, b in zip(pixel, expected)), (pixel, expected)
    print("✓ 5: לכל אירוע התמונה שלו — גם כשאותו מופע ספק משמש שני אירועים")


def test_media_error_reuploads_and_never_sends_without_image() -> None:
    from app import outbound

    db = Session(_engine())
    ev, guests, items, phones = _setup(db, image=_image_bytes())
    fake = FakeMeta(_uploaded("MEDIA-1"), err(131053, "Media upload error"),
                    _uploaded("MEDIA-2"), ok("w2"), ok("w3"))
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=fake):
        result = outbound.send_batch(db, ev, items)
        db.commit()
    uploads, bodies = _split(fake)
    assert len(uploads) == 2 and [_header_id(b) for b in bodies] == ["MEDIA-1", "MEDIA-2", "MEDIA-2"]
    assert (result.sent, result.failed) == (2, 1)

    # העלאה חוזרת נכשלת — ההודעות הבאות לא יוצאות בלי תמונה (נרשמות כנכשלו).
    db = Session(_engine())
    ev, guests, items, phones = _setup(db, image=_image_bytes())
    fake = FakeMeta(_uploaded("MEDIA-1"), err(131053, "Media upload error"), err(100, "bad"))
    with meta_env(mode="meta_test", recipients=",".join(phones), fake=fake):
        result = outbound.send_batch(db, ev, items)
        db.commit()
    uploads, bodies = _split(fake)
    assert len(bodies) == 1, "רק ההודעה הראשונה יצאה — עם התמונה"
    assert _header_id(bodies[0]) == "MEDIA-1"
    assert (result.sent, result.failed) == (0, 3)
    rows = _rows(db, ev.id)
    assert all(r.status == "failed" for r in rows)
    assert "תמונת ההזמנה לא צורפה" in rows[2].failure_reason
    print("✓ 6: מזהה פג — העלאה מחדש; אם נכשלת — אין הודעה בלי תמונה")


def test_conversion_to_whatsapp_jpeg() -> None:
    from app import media

    for fmt, ctype in (("WEBP", "image/webp"), ("PNG", "image/png"), ("JPEG", "image/jpeg")):
        out = media.whatsapp_jpeg(_image_bytes(fmt=fmt), ctype)
        assert out[:3] == b"\xff\xd8\xff" and len(out) <= media.WHATSAPP_IMAGE_MAX_BYTES, fmt
    rgba = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(rgba, format="PNG")
    assert Image.open(io.BytesIO(media.whatsapp_jpeg(rgba.getvalue(), "image/png"))).mode == "RGB"
    big = Image.effect_noise((2500, 2500), 100).convert("RGB")
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    assert len(media.whatsapp_jpeg(buf.getvalue(), "image/png")) <= media.WHATSAPP_IMAGE_MAX_BYTES
    for bad, ctype in ((b"<svg/>", "image/svg+xml"), (b"x", "image/heic"), (b"notanimage", "image/png")):
        try:
            media.whatsapp_jpeg(bad, ctype)
            raise AssertionError(f"{ctype} היה אמור להיחסם")
        except media.WhatsAppImageError:
            pass
    frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0))]
    anim = io.BytesIO()
    frames[0].save(anim, format="WEBP", save_all=True, append_images=frames[1:])
    try:
        media.whatsapp_jpeg(anim.getvalue(), "image/webp")
        raise AssertionError("תמונה מונפשת הייתה אמורה להיחסם")
    except media.WhatsAppImageError:
        pass
    # מה ששמור לא משתנה.
    db = Session(_engine())
    original = _image_bytes()
    stored = _store_image(db, original, "image/webp", "keep-me")
    raw, ctype = media.load_stored_image(db, stored)
    media.whatsapp_jpeg(raw, ctype)
    from app import models

    assert db.get(models.MediaBlob, "keep-me").data == original and ctype == "image/webp"
    print("✓ 7: המרה — WebP/PNG/JPEG → JPEG עד 5MB; SVG/HEIC/פגום/מונפש נחסמים; השמור לא משתנה")


def test_send_invitations_endpoint_explains_block() -> None:
    from app import models
    from tests.test_whatsapp_meta_test_mode import _set_invitation_content

    api, _ = bootstrap()
    phone = _phone()
    g = api.add_guest("מורשה בדיקה", phone)
    _set_invitation_content(api)
    db = _db()
    try:
        ev = db.get(models.Event, api.event_id)
        ev.event_date = "2026-12-01"
        ev.invite_image = _store_image(db, b"<svg/>", "image/svg+xml", f"svg-{api.event_id}")
        db.commit()
    finally:
        db.close()
    with meta_env(mode="meta_test", recipients=phone) as fake:
        r = api.client.post("/automation/track/activate", headers=api.headers, json={})
    assert r.status_code == 409, r.text
    assert "JPEG או PNG" in r.json()["detail"] and fake.requests == []
    db = _db()
    try:
        assert db.scalars(select(models.Message).where(
            models.Message.guest_id == g["id"])).all() == []
    finally:
        db.close()
    print("✓ 8: שליחת הזמנות — 409 עם הסבר 'JPEG או PNG'; שום בקשה ושום שורה")


def test_test_tool_image_option(tmp_path=None) -> None:
    import tempfile

    from scripts import whatsapp_hello_world as script

    me = _phone()
    code = "AbCdEf123456"
    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "invite.png"
        img.write_bytes(_image_bytes(fmt="PNG"))
        args = ["--to", me, "--template", "veya_invitation_image", "--name", "דנה",
                "--code", code, "--image", str(img), "--env-file", _NO_ENV]
        with meta_env(mode="meta_test", recipients=me) as fake:
            rc, out = _captured(lambda: script.main(args))
        assert rc == 0 and fake.requests == [] and "בדיקה בלבד" in out and "JPEG" in out
        fake = FakeMeta(_uploaded("MEDIA-T"), ok("wamid.t"))
        with meta_env(mode="meta_test", recipients=me, fake=fake):
            rc, out = _captured(lambda: script.main(args + ["--send"]))
        assert rc == 0, out
        uploads, bodies = _split(fake)
        assert len(uploads) == 1 and bodies[0]["template"]["name"] == "veya_invitation_image"
        assert _header_id(bodies[0]) == "MEDIA-T"
        for leak in (TOKEN, me, code):
            assert leak not in out
        svg = Path(tmp) / "invite.svg"
        svg.write_text("<svg/>")
        bad = ["--to", me, "--template", "veya_invitation_image", "--name", "דנה", "--code", code,
               "--image", str(svg), "--send", "--env-file", _NO_ENV]
        with meta_env(mode="meta_test", recipients=me) as fake:
            rc, out = _captured(lambda: script.main(bad))
        assert rc == 2 and fake.requests == [] and "JPEG או PNG" in out
    print("✓ 9: כלי הבדיקה — בלי --send לא מעלה; עם --send העלאה + הודעה; SVG נחסם")


if __name__ == "__main__":
    _register_invitation_templates()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("\n=== הזמנה עם תמונה — עבר ===")
    finally:
        shutdown()
