from collections.abc import Callable, Iterable

import pandas as pd

from .generic import calculate_trend_statistics


def prepare_daily_data(
    data: pd.DataFrame,
    value_columns: Iterable[str],
) -> pd.DataFrame:
    """Validate and normalize dated numeric observations."""
    value_columns = tuple(value_columns)
    required = {"date", *value_columns}
    if data.empty or not required.issubset(data.columns):
        return pd.DataFrame()

    prepared = data.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    for column in value_columns:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared = prepared.dropna(subset=["date", *value_columns])
    prepared["year"] = prepared["date"].dt.year
    return prepared


def aggregate_complete_years(
    data: pd.DataFrame,
    value_column: str,
    reducer: str | Callable,
    minimum_days: int,
) -> pd.DataFrame:
    """Aggregate daily values and retain sufficiently complete years."""
    annual = data.groupby("year", as_index=False).agg(
        value=(value_column, reducer), days=(value_column, "count")
    )
    return annual[annual["days"] >= minimum_days]


def trend_supports_change(
    data: pd.DataFrame,
    change: float,
    period_column: str = "year",
    value_column: str = "value",
) -> bool:
    """Return whether a significant trend agrees with a period change."""
    trend = calculate_trend_statistics(data, period_column, value_column)
    if not trend or not trend.statistically_significant:
        return False
    expected_direction = "increasing" if change > 0 else "decreasing"
    return change != 0 and trend.direction == expected_direction
