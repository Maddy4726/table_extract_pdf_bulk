from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from .models import DailySummary, FoodOut, FoodSearchResult, LogEntryOut, Nutrients
from .nutrition import nutrients_from_row, scale_nutrients, sum_nutrients

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "nutrition.db"
SEED_PATH = DATA_DIR / "foods_seed.json"


class Base(DeclarativeBase):
    pass


class Food(Base):
    __tablename__ = "foods"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, default="General")
    calories_kcal = Column(Float, default=0)
    protein_g = Column(Float, default=0)
    carbs_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    fiber_g = Column(Float, default=0)
    sugar_g = Column(Float, default=0)
    sodium_mg = Column(Float, default=0)
    potassium_mg = Column(Float, default=0)
    calcium_mg = Column(Float, default=0)
    iron_mg = Column(Float, default=0)
    magnesium_mg = Column(Float, default=0)
    zinc_mg = Column(Float, default=0)
    vitamin_a_mcg = Column(Float, default=0)
    vitamin_c_mg = Column(Float, default=0)
    vitamin_d_mcg = Column(Float, default=0)
    vitamin_e_mg = Column(Float, default=0)
    vitamin_k_mcg = Column(Float, default=0)
    vitamin_b6_mg = Column(Float, default=0)
    vitamin_b12_mcg = Column(Float, default=0)
    folate_mcg = Column(Float, default=0)

    entries = relationship("LogEntry", back_populates="food")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True)
    food_id = Column(Integer, ForeignKey("foods.id"), nullable=False)
    weight_g = Column(Float, nullable=False)
    meal = Column(String, nullable=True)
    logged_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    food = relationship("Food", back_populates="entries")


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Food)) == 0:
            _seed_foods(session)


def _seed_foods(session: Session) -> None:
    if not SEED_PATH.exists():
        return
    foods = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for item in foods:
        session.add(Food(**item))
    session.commit()


def _food_to_nutrients(food: Food) -> Nutrients:
    return nutrients_from_row({c.name: getattr(food, c.name) for c in Food.__table__.columns})


def search_foods(query: str, limit: int = 20) -> list[FoodSearchResult]:
    with SessionLocal() as session:
        stmt = select(Food).order_by(Food.name)
        if query.strip():
            pattern = f"%{query.strip().lower()}%"
            stmt = stmt.where(func.lower(Food.name).like(pattern))
        rows = session.scalars(stmt.limit(limit)).all()
        return [FoodSearchResult(id=f.id, name=f.name, category=f.category) for f in rows]


def get_food(food_id: int) -> FoodOut | None:
    with SessionLocal() as session:
        food = session.get(Food, food_id)
        if not food:
            return None
        return FoodOut(
            id=food.id,
            name=food.name,
            category=food.category,
            per_100g=_food_to_nutrients(food),
        )


def preview_nutrients(food_id: int, weight_g: float) -> Nutrients | None:
    with SessionLocal() as session:
        food = session.get(Food, food_id)
        if not food:
            return None
        return scale_nutrients(_food_to_nutrients(food), weight_g)


def add_log_entry(
    food_id: int,
    weight_g: float,
    logged_date: date | None = None,
    meal: str | None = None,
) -> LogEntryOut | None:
    target_date = logged_date or date.today()
    with SessionLocal() as session:
        food = session.get(Food, food_id)
        if not food:
            return None
        entry = LogEntry(
            food_id=food_id,
            weight_g=weight_g,
            meal=meal,
            logged_date=target_date,
            created_at=datetime.utcnow(),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        nutrients = scale_nutrients(_food_to_nutrients(food), weight_g)
        return LogEntryOut(
            id=entry.id,
            food_id=food.id,
            food_name=food.name,
            weight_g=weight_g,
            meal=meal,
            logged_date=target_date,
            nutrients=nutrients,
            created_at=entry.created_at,
        )


def delete_log_entry(entry_id: int) -> bool:
    with SessionLocal() as session:
        entry = session.get(LogEntry, entry_id)
        if not entry:
            return False
        session.delete(entry)
        session.commit()
        return True


def get_daily_summary(target_date: date) -> DailySummary:
    with SessionLocal() as session:
        rows = session.scalars(
            select(LogEntry)
            .where(LogEntry.logged_date == target_date)
            .order_by(LogEntry.created_at.desc())
        ).all()
        entries: list[LogEntryOut] = []
        nutrient_list: list[Nutrients] = []
        for entry in rows:
            food = entry.food
            nutrients = scale_nutrients(_food_to_nutrients(food), entry.weight_g)
            nutrient_list.append(nutrients)
            entries.append(
                LogEntryOut(
                    id=entry.id,
                    food_id=food.id,
                    food_name=food.name,
                    weight_g=entry.weight_g,
                    meal=entry.meal,
                    logged_date=entry.logged_date,
                    nutrients=nutrients,
                    created_at=entry.created_at,
                )
            )
        return DailySummary(
            date=target_date,
            entry_count=len(entries),
            totals=sum_nutrients(nutrient_list),
            entries=entries,
        )
