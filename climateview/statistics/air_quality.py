from __future__ import annotations

from typing import Any

import pandas as pd

from .generic import calculate_period_comparison
from .preprocessing import (
    aggregate_complete_years,
    prepare_daily_data,
    trend_supports_change,
)


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
    working = prepare_daily_data(data, [value_column])
    if working.empty:
        return {"available": False}
    working["display_value"] = working[value_column] * display_scale
    annual = aggregate_complete_years(
        working, "display_value", "mean", minimum_days_per_year
    )
    comparison = calculate_period_comparison(
        annual,
        period_column="year",
        value_column="value",
        period_size=period_size,
    )
    if comparison is None:
        return {"available": False}

    return {
        "available": True,
        **comparison.__dict__,
        "unit": unit,
        "significant_change": trend_supports_change(
            annual, comparison.absolute_change
        ),
    }
