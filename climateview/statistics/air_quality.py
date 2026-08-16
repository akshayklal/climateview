from __future__ import annotations

from typing import Any

import pandas as pd

from .generic import calculate_period_comparison, calculate_trend_statistics


def calculate_air_quality_period_statistics(
    data: pd.DataFrame,
    *,
    value_column: str,
    display_scale: float,
    unit: str,
    period_size: int = 10,
    minimum_days_per_year: int = 90,
) -> dict[str, Any]:
    """Compare a pollutant's first/latest qualifying annual periods."""
    if data.empty or not {"date", value_column}.issubset(data.columns):
        return {"available": False}

    working = data.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working[value_column] = pd.to_numeric(
        working[value_column], errors="coerce"
    )
    working = working.dropna(subset=["date", value_column])
    working["year"] = working["date"].dt.year
    working["display_value"] = working[value_column] * display_scale
    annual = (
        working.groupby("year", as_index=False)
        .agg(value=("display_value", "mean"), days=("display_value", "count"))
    )
    annual = annual[annual["days"] >= minimum_days_per_year]
    comparison = calculate_period_comparison(
        annual,
        period_column="year",
        value_column="value",
        period_size=period_size,
    )
    if comparison is None:
        return {"available": False, "qualifying_years": int(len(annual))}

    trend = calculate_trend_statistics(annual, "year", "value")
    direction_matches = bool(
        trend
        and (
            (comparison.absolute_change > 0 and trend.direction == "increasing")
            or (
                comparison.absolute_change < 0
                and trend.direction == "decreasing"
            )
        )
    )
    return {
        "available": True,
        **comparison.__dict__,
        "unit": unit,
        "significant_change": bool(
            trend and trend.statistically_significant and direction_matches
        ),
    }
