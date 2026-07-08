from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class Nutrients(BaseModel):
    """Nutrition values for a given portion (scaled from per-100g basis)."""

    calories_kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    sugar_g: float = 0
    sodium_mg: float = 0
    potassium_mg: float = 0
    calcium_mg: float = 0
    iron_mg: float = 0
    magnesium_mg: float = 0
    zinc_mg: float = 0
    vitamin_a_mcg: float = 0
    vitamin_c_mg: float = 0
    vitamin_d_mcg: float = 0
    vitamin_e_mg: float = 0
    vitamin_k_mcg: float = 0
    vitamin_b6_mg: float = 0
    vitamin_b12_mcg: float = 0
    folate_mcg: float = 0


class FoodOut(BaseModel):
    id: int
    name: str
    category: str
    per_100g: Nutrients


class FoodSearchResult(BaseModel):
    id: int
    name: str
    category: str


class LogEntryCreate(BaseModel):
    food_id: int
    weight_g: float = Field(gt=0, le=10000)
    logged_date: Optional[date] = None
    meal: Optional[str] = Field(default=None, max_length=32)


class LogEntryOut(BaseModel):
    id: int
    food_id: int
    food_name: str
    weight_g: float
    meal: Optional[str]
    logged_date: date
    nutrients: Nutrients
    created_at: datetime


class DailySummary(BaseModel):
    date: date
    entry_count: int
    totals: Nutrients
    entries: list[LogEntryOut]
