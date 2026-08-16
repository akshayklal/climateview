from __future__ import annotations

from typing import Any

import pandas as pd

from .generic import calculate_period_comparison
from .preprocessing import (
    aggregate_complete_years,
    prepare_daily_data,
    trend_supports_change,
)


SEASONS = {
    12: "winter",
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "fall",
    10: "fall",
    11: "fall",
}


def calculate_temperature_period_statistics(
    data: pd.DataFrame,
    *,
    period_size: int = 10,
    minimum_days_per_year: int = 300,
) -> dict[str, Any]:
    """Compare annual and seasonal temperature in the first/latest periods."""
    working = prepare_daily_data(data, ["tmax_f", "tmin_f"])
    if working.empty:
        return {"available": False}

    working["daily_mean_f"] = (working["tmax_f"] + working["tmin_f"]) / 2.0
    annual = aggregate_complete_years(
        working, "daily_mean_f", "mean", minimum_days_per_year
    )
    comparison = calculate_period_comparison(
        annual,
        period_column="year",
        value_column="value",
        period_size=period_size,
        require_consecutive=True,
    )
    if comparison is None:
        return {"available": False}

    baseline_start = int(str(comparison.baseline_period).split("–", 1)[0])
    recent_start = int(str(comparison.recent_period).split("–", 1)[0])
    strongest = calculate_strongest_seasonal_temperature_change(
        working,
        baseline_years=set(range(baseline_start, baseline_start + period_size)),
        recent_years=set(range(recent_start, recent_start + period_size)),
        overall_change=comparison.absolute_change,
    )
    result = {
        "available": True,
        **comparison.__dict__,
        "trend_supported": trend_supports_change(
            annual, comparison.absolute_change
        ),
    }
    if strongest:
        result["strongest_seasonal_change"] = strongest
    return result


def calculate_strongest_seasonal_temperature_change(
    data: pd.DataFrame,
    *,
    baseline_years: set[int],
    recent_years: set[int],
    overall_change: float,
) -> dict[str, Any] | None:
    """Find the seasonal daytime/nighttime change leading the overall move."""
    seasonal = data.copy()
    seasonal["season"] = seasonal["date"].dt.month.map(SEASONS)
    yearly = (
        seasonal.groupby(["year", "season"], as_index=False)
        .agg(
            daytime=("tmax_f", "mean"),
            nighttime=("tmin_f", "mean"),
            days=("date", "count"),
        )
    )
    yearly = yearly[yearly["days"] >= 60]

    candidates = []
    for season in ("winter", "spring", "summer", "fall"):
        rows = yearly[yearly["season"] == season]
        baseline = rows[rows["year"].isin(baseline_years)]
        recent = rows[rows["year"].isin(recent_years)]
        if len(baseline) < 8 or len(recent) < 8:
            continue
        for column, time_of_day in (
            ("daytime", "days"),
            ("nighttime", "nights"),
        ):
            change = float(recent[column].mean() - baseline[column].mean())
            candidates.append(
                {
                    "season": season,
                    "time_of_day": time_of_day,
                    "change_f": change,
                    "trend_supported": trend_supports_change(
                        rows, change, "year", column
                    ),
                }
            )

    if not candidates:
        return None
    if overall_change >= 0:
        return max(candidates, key=lambda item: item["change_f"])
    return min(candidates, key=lambda item: item["change_f"])
