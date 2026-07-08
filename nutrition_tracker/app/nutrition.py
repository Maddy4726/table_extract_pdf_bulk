from __future__ import annotations

from .models import Nutrients


NUTRIENT_FIELDS = tuple(Nutrients.model_fields.keys())


def scale_nutrients(per_100g: Nutrients, weight_g: float) -> Nutrients:
    factor = weight_g / 100.0
    return Nutrients(**{field: getattr(per_100g, field) * factor for field in NUTRIENT_FIELDS})


def sum_nutrients(items: list[Nutrients]) -> Nutrients:
    totals = {field: 0.0 for field in NUTRIENT_FIELDS}
    for item in items:
        for field in NUTRIENT_FIELDS:
            totals[field] += getattr(item, field)
    return Nutrients(**totals)


def nutrients_from_row(row: dict) -> Nutrients:
    return Nutrients(**{field: float(row.get(field, 0) or 0) for field in NUTRIENT_FIELDS})
