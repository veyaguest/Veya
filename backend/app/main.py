"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  — נדרש כדי לרשום את הטבלאות
from app.database import Base, SessionLocal, engine
from app.deps import get_default_event
from app.routers import guests, import_guests

app = FastAPI(title="VEYA API", version="0.1.0")

# מאפשר ל-Frontend (Vite, פורט 5173) לפנות ל-API בזמן פיתוח.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(guests.router)
app.include_router(import_guests.router)


@app.on_event("startup")
def on_startup() -> None:
    # יוצר את קובץ מסד הנתונים ואת הטבלאות.
    Base.metadata.create_all(bind=engine)
    # מוודא שקיים אירוע ברירת-מחדל אחד.
    db = SessionLocal()
    try:
        get_default_event(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
