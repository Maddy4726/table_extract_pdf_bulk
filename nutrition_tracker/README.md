# Nutrition Tracker

Log food by weight (grams) and track daily **macros** (calories, protein, carbs, fat) and **micros** (vitamins, minerals, fiber, etc.).

## Features

- Search 35+ common foods (chicken, rice, fruits, vegetables, legumes, and more)
- Enter portion weight in grams — nutrition scales automatically from per-100g data
- Live preview of macros and micros before logging
- Daily dashboard with running totals and meal history
- Optional meal labels (breakfast, lunch, dinner, snack)
- SQLite storage — your log persists between sessions

## Quick start

```bash
cd nutrition_tracker
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

## How it works

1. **Search** for a food (e.g. "salmon", "oats").
2. **Set weight** in grams (default 100 g).
3. **Preview** macros and micros for that portion.
4. **Add to log** — totals update on the daily summary panel.

Nutrition values are stored per 100 g and scaled with:

`actual = per_100g × (weight_g / 100)`

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/foods/search?q=` | Search foods |
| `GET /api/foods/{id}/preview?weight_g=` | Preview nutrients for a portion |
| `POST /api/log` | Log a food entry |
| `GET /api/daily?day=YYYY-MM-DD` | Daily summary and entries |
| `DELETE /api/log/{id}` | Remove an entry |

## Extending

- Add more foods by editing `data/foods_seed.json` (values per 100 g), then delete `data/nutrition.db` to re-seed.
- For a larger food database, you can integrate the [USDA FoodData Central API](https://fdc.nal.usda.gov/api-guide.html) with an API key.
