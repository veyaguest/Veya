"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine

app = FastAPI(title="VEYA API", version="0.1.0")

# מאפשר ל-Frontend (Vite, פורט 5173) לפנות ל-API בזמן פיתוח.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # יוצר את קובץ מסד הנתונים ואת הטבלאות הקיימות (עדיין אין — יתווספו בשלב 2).
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
