from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import database
from .models import DailySummary, FoodOut, FoodSearchResult, LogEntryCreate, LogEntryOut, Nutrients

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Nutrition Tracker", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    database.init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/foods/search", response_model=list[FoodSearchResult])
def api_search_foods(q: str = Query(default="", max_length=100)) -> list[FoodSearchResult]:
    return database.search_foods(q)


@app.get("/api/foods/{food_id}", response_model=FoodOut)
def api_get_food(food_id: int) -> FoodOut:
    food = database.get_food(food_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    return food


@app.get("/api/foods/{food_id}/preview", response_model=Nutrients)
def api_preview(food_id: int, weight_g: float = Query(gt=0, le=10000)) -> Nutrients:
    nutrients = database.preview_nutrients(food_id, weight_g)
    if not nutrients:
        raise HTTPException(status_code=404, detail="Food not found")
    return nutrients


@app.post("/api/log", response_model=LogEntryOut)
def api_log_entry(payload: LogEntryCreate) -> LogEntryOut:
    entry = database.add_log_entry(
        food_id=payload.food_id,
        weight_g=payload.weight_g,
        logged_date=payload.logged_date,
        meal=payload.meal,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Food not found")
    return entry


@app.delete("/api/log/{entry_id}")
def api_delete_entry(entry_id: int) -> dict[str, bool]:
    if not database.delete_log_entry(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True}


@app.get("/api/daily", response_model=DailySummary)
def api_daily_summary(day: date | None = None) -> DailySummary:
    target = day or date.today()
    return database.get_daily_summary(target)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
