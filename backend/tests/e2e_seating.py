"""עזר בדיקות מקצה-לקצה למערכת ההושבה — מריץ את ה-API האמיתי מול DB זמני.

לא בדיקה בפני עצמה: זו התשתית ש-``test_seating_flow.py`` משתמש בה, וגם כלי
נוח לבדיקה ידנית. מרים את האפליקציה המלאה (כולל המיגרציות שרצות ב-startup)
מול קובץ SQLite זמני, נרשם, פותח אירוע, ומחזיר לקוח מוכן לעבודה.

חשוב: ה-DB נקבע דרך משתנה הסביבה ``DATABASE_URL`` **לפני** ייבוא ``app`` —
``app.database`` קורא אותו בזמן הייבוא.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# לקוח יחיד לכל תהליך הבדיקה. חשוב: ``app.database`` יוצר את ה-engine בזמן
# הייבוא, ולכן אי אפשר להחליף DB בין בדיקה לבדיקה — ניסיון כזה משאיר את
# ה-engine מחובר לקובץ שנמחק ("attempt to write a readonly database").
# הבידוד בין בדיקות נעשה כמו במערכת עצמה: כל בדיקה מקבלת **משתמש ואירוע
# חדשים**, וכל השאילתות ממילא מסוננות לפי event_id.
_CLIENT = None
_DB_PATH = None


def make_client():
    """מחזיר (client, teardown) — TestClient מחובר ל-DB זמני משותף."""
    global _CLIENT, _DB_PATH
    if _CLIENT is not None:
        return _CLIENT, lambda: None

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _DB_PATH = tmp.name
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.name}"
    os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-usage")

    # ייבוא מאוחר בכוונה — אחרי שקבענו DATABASE_URL.
    from fastapi.testclient import TestClient

    from app.main import app

    _CLIENT = TestClient(app)
    _CLIENT.__enter__()  # מפעיל את אירוע ה-startup (create_all + מיגרציות)
    return _CLIENT, lambda: None


def shutdown() -> None:
    """סוגר את הלקוח ומוחק את ה-DB הזמני. נקרא פעם אחת בסוף קובץ הבדיקה."""
    global _CLIENT, _DB_PATH
    if _CLIENT is not None:
        _CLIENT.__exit__(None, None, None)
        _CLIENT = None
    if _DB_PATH:
        try:
            os.unlink(_DB_PATH)
        except OSError:
            pass
        _DB_PATH = None


def register(client) -> str:
    """נרשם כמשתמש חדש ומחזיר טוקן."""
    email = f"test-{uuid.uuid4().hex[:10]}@veya.test"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Test12345!",
            "phone": "0501234567",
            "accepted_terms": True,
        },
    )
    assert r.status_code == 201, f"register נכשל: {r.status_code} {r.text}"
    return r.json()["access_token"]


def create_event(client, token: str, event_type: str = "wedding") -> int:
    r = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "groom_name": "דני",
            "bride_name": "רותי",
            "event_type": event_type,
            "venue_name": "אולם הבדיקות",
        },
    )
    assert r.status_code == 201, f"יצירת אירוע נכשלה: {r.status_code} {r.text}"
    return r.json()["id"]


class Api:
    """עטיפה דקה — שומרת טוקן ומזהה אירוע כדי שהבדיקות יישארו קריאות."""

    def __init__(self, client, token: str, event_id: int) -> None:
        self.client = client
        self.token = token
        self.event_id = event_id

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Event-Id": str(self.event_id),
        }

    def add_guest(self, full_name: str, phone: str, **kwargs):
        body = {"full_name": full_name, "phone": phone}
        body.update(kwargs)
        r = self.client.post("/guests", headers=self.headers, json=body)
        assert r.status_code == 201, f"הוספת מוזמן נכשלה: {r.status_code} {r.text}"
        return r.json()

    def save_hall(self, tables: list[dict], elements: list[dict] | None = None,
                  seats_per_table: int = 12):
        r = self.client.put(
            "/hall",
            headers=self.headers,
            json={
                "tables": tables,
                "elements": elements or [],
                "seats_per_table": seats_per_table,
                "sketch": "",
            },
        )
        assert r.status_code == 200, f"שמירת אולם נכשלה: {r.status_code} {r.text}"
        return r.json()

    def get_hall(self):
        r = self.client.get("/hall", headers=self.headers)
        assert r.status_code == 200, f"קריאת אולם נכשלה: {r.status_code} {r.text}"
        return r.json()

    def generate(self, **kwargs):
        body = {"seats_per_table": 12, "persist": True}
        body.update(kwargs)
        r = self.client.post("/seating/generate", headers=self.headers, json=body)
        return r


def bootstrap(event_type: str = "wedding"):
    """הדרך המהירה: מחזיר (api, teardown) עם משתמש ואירוע **חדשים**.

    ``teardown`` הוא no-op (הבידוד הוא ברמת האירוע). ניקוי בפועל נעשה
    ב-``shutdown()`` פעם אחת בסוף קובץ הבדיקה.
    """
    client, teardown = make_client()
    token = register(client)
    event_id = create_event(client, token, event_type)
    return Api(client, token, event_id), teardown


if __name__ == "__main__":
    api, _ = bootstrap()
    try:
        api.add_guest("דני כהן", "0501111111")
        print("bootstrap OK — event", api.event_id)
        print("hall:", {k: v for k, v in api.get_hall().items() if k != "tables"})
    finally:
        shutdown()
