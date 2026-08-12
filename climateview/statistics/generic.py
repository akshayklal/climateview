from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .models import (
    DataQualityStatistics,
    DescriptiveStatistics,
    ExtremeValue,
    RecentChangeStatistics,
    TrendStatistics,
    VariabilityStatistics,
)


MIN_TREND_OBSERVATIONS = 3
DEFAULT_SIGNIFICANCE_LEVEL = 0.05
DEFAULT_RECENT_FRACTION = 0.25

LOW_VARIABILITY_CV = 0.10
HIGH_VARIABILITY_CV = 0.30


def prepare_series(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
) -> pd.DataFrame:
    """
    Return a normalized two-column dataframe for statistical analysis.

    The returned dataframe:

    - contains only the period and value columns;
    - converts values to numeric;
    - removes rows with missing or non-finite values;
    - sorts rows by period;
    - resets the index.

    Duplicate periods are preserved because they may be valid for the
    selected aggregation.
    """

    if period_column not in dataframe.columns:
        raise ValueError(f"Period column not found: {period_column}")

    if value_column not in dataframe.columns:
        raise ValueError(f"Value column not found: {value_column}")

    prepared = dataframe[[period_column, value_column]].copy()

    prepared[value_column] = pd.to_numeric(
        prepared[value_column],
        errors="coerce",
    )

    prepared = prepared.dropna(subset=[period_column, value_column])

    finite_mask = np.isfinite(prepared[value_column].to_numpy(dtype=float))
    prepared = prepared.loc[finite_mask]

    prepared = prepared.sort_values(period_column).reset_index(drop=True)

    if prepared.empty:
        raise ValueError("No valid observations remain after data cleaning.")

    return prepared


def calculate_data_quality(
    dataframe: pd.DataFrame,
    period_column: str,
) -> DataQualityStatistics:
    """Describe the valid, sorted periods in a prepared dataframe."""

    return DataQualityStatistics(
        observation_count=len(dataframe),
        first_period=_to_python_scalar(dataframe.iloc[0][period_column]),
        last_period=_to_python_scalar(dataframe.iloc[-1][period_column]),
    )


def calculate_descriptive_statistics(
    values: pd.Series | Sequence[float],
) -> DescriptiveStatistics:
    """
    Calculate basic descriptive statistics for a numeric series.
    """

    numeric = _clean_numeric_values(values)

    if numeric.size == 0:
        raise ValueError("At least one valid numeric value is required.")

    return DescriptiveStatistics(mean=float(np.mean(numeric)))


def calculate_extremes(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
) -> tuple[ExtremeValue, ExtremeValue]:
    """
    Return the minimum and maximum observations.

    If multiple periods share the same extreme value, the earliest period is
    returned because the dataframe is sorted by period first.
    """

    minimum_index = dataframe[value_column].idxmin()
    maximum_index = dataframe[value_column].idxmax()

    minimum_row = dataframe.loc[minimum_index]
    maximum_row = dataframe.loc[maximum_index]

    minimum = ExtremeValue(
        period=_to_python_scalar(minimum_row[period_column]),
        value=float(minimum_row[value_column]),
    )

    maximum = ExtremeValue(
        period=_to_python_scalar(maximum_row[period_column]),
        value=float(maximum_row[value_column]),
    )

    return minimum, maximum


def calculate_ranked_extremes(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    limit: int = 10,
) -> dict[str, list[ExtremeValue]]:
    """Return verified highest and lowest observations in rank order."""
    if limit < 1:
        raise ValueError("Ranking limit must be at least 1.")

    def serialize(rows: pd.DataFrame) -> list[ExtremeValue]:
        return [
            ExtremeValue(
                period=_to_python_scalar(row[period_column]),
                value=float(row[value_column]),
            )
            for _, row in rows.iterrows()
        ]

    highest = dataframe.sort_values(
        [value_column, period_column],
        ascending=[False, True],
    ).head(limit)
    lowest = dataframe.sort_values(
        [value_column, period_column],
        ascending=[True, True],
    ).head(limit)

    return {
        "highest": serialize(highest),
        "lowest": serialize(lowest),
    }


def calculate_variability_statistics(
    values: pd.Series | Sequence[float],
) -> VariabilityStatistics:
    """
    Calculate spread and relative variability.

    Coefficient of variation is omitted when the mean is zero or very close
    to zero because relative variability would not be meaningful.
    """

    numeric = _clean_numeric_values(values)

    if numeric.size == 0:
        raise ValueError("At least one valid numeric value is required.")

    mean = float(np.mean(numeric))

    standard_deviation = (
        float(np.std(numeric, ddof=1))
        if numeric.size > 1
        else 0.0
    )

    if np.isclose(mean, 0.0):
        variability_level = _classify_variability_without_cv(
            numeric=numeric,
            standard_deviation=standard_deviation,
        )
    else:
        coefficient_of_variation = abs(standard_deviation / mean)
        variability_level = classify_variability(
            coefficient_of_variation
        )

    return VariabilityStatistics(variability_level=variability_level)


def classify_variability(
    coefficient_of_variation: float,
) -> str:
    """
    Convert coefficient of variation into a broad descriptive category.

    These thresholds are intentionally generic. Metric-specific modules may
    override the interpretation when more appropriate thresholds are known.
    """

    if coefficient_of_variation < 0:
        raise ValueError(
            "Coefficient of variation must not be negative."
        )

    if coefficient_of_variation < LOW_VARIABILITY_CV:
        return "low"

    if coefficient_of_variation < HIGH_VARIABILITY_CV:
        return "moderate"

    return "high"


def calculate_trend_statistics(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> TrendStatistics | None:
    """
    Calculate a least-squares linear trend.

    Numeric periods are used directly. Datetimes are converted to elapsed
    years.

    Returns None when fewer than three valid observations are available or
    when the x-axis has no variation.
    """

    if not 0.0 < significance_level < 1.0:
        raise ValueError(
            "significance_level must be between 0 and 1."
        )

    if len(dataframe) < MIN_TREND_OBSERVATIONS:
        return None

    x = _periods_to_numeric(dataframe[period_column])
    y = dataframe[value_column].to_numpy(dtype=float)

    if np.allclose(x, x[0]):
        return None

    regression = stats.linregress(x, y)

    slope = float(regression.slope)
    statistically_significant = bool(regression.pvalue < significance_level)
    direction = "stable"
    if statistically_significant:
        direction = "increasing" if slope > 0 else "decreasing"

    return TrendStatistics(
        direction=direction,
        statistically_significant=statistically_significant,
    )


def calculate_recent_change_statistics(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    recent_fraction: float = DEFAULT_RECENT_FRACTION,
    minimum_recent_observations: int = 3,
) -> RecentChangeStatistics | None:
    """
    Compare the most recent portion of the series with the earlier baseline.

    By default, the newest 25% of observations form the recent period. The
    earlier observations form the baseline period.
    """

    if not 0.0 < recent_fraction < 1.0:
        raise ValueError(
            "recent_fraction must be between 0 and 1."
        )

    if minimum_recent_observations < 1:
        raise ValueError(
            "minimum_recent_observations must be at least 1."
        )

    observation_count = len(dataframe)

    recent_count = max(
        minimum_recent_observations,
        int(round(observation_count * recent_fraction)),
    )

    if recent_count >= observation_count:
        return None

    baseline = dataframe.iloc[:-recent_count]
    recent = dataframe.iloc[-recent_count:]

    if baseline.empty or recent.empty:
        return None

    baseline_mean = float(baseline[value_column].mean())
    recent_mean = float(recent[value_column].mean())
    absolute_change = recent_mean - baseline_mean

    percent_change = (
        absolute_change / abs(baseline_mean) * 100.0
        if not np.isclose(baseline_mean, 0.0)
        else None
    )

    baseline_period = _format_period_range(
        baseline.iloc[0][period_column],
        baseline.iloc[-1][period_column],
    )

    recent_period = _format_period_range(
        recent.iloc[0][period_column],
        recent.iloc[-1][period_column],
    )

    return RecentChangeStatistics(
        baseline_mean=baseline_mean,
        recent_mean=recent_mean,
        absolute_change=float(absolute_change),
        percent_change=(
            float(percent_change)
            if percent_change is not None
            else None
        ),
        baseline_period=baseline_period,
        recent_period=recent_period,
    )


def _clean_numeric_values(
    values: pd.Series | Sequence[float],
) -> np.ndarray:
    series = pd.Series(values, dtype="object")
    numeric = pd.to_numeric(series, errors="coerce")
    numeric = numeric[np.isfinite(numeric.to_numpy(dtype=float))]

    return numeric.to_numpy(dtype=float)


def _periods_to_numeric(periods: pd.Series) -> np.ndarray:
    if pd.api.types.is_numeric_dtype(periods):
        return periods.to_numpy(dtype=float)

    if pd.api.types.is_datetime64_any_dtype(periods):
        datetimes = pd.to_datetime(periods)
        elapsed_days = (
            datetimes - datetimes.iloc[0]
        ).dt.total_seconds() / 86_400.0

        return elapsed_days.to_numpy(dtype=float) / 365.2425

    raise ValueError("Period values must be numeric or datetimes.")


def _classify_variability_without_cv(
    numeric: np.ndarray,
    standard_deviation: float,
) -> str:
    if np.isclose(standard_deviation, 0.0):
        return "low"

    median_absolute_value = float(np.median(np.abs(numeric)))

    if np.isclose(median_absolute_value, 0.0):
        return "not_comparable"

    relative_spread = standard_deviation / median_absolute_value
    return classify_variability(relative_spread)


def _format_period_range(
    first_period: Any,
    last_period: Any,
) -> str:
    first = _to_python_scalar(first_period)
    last = _to_python_scalar(last_period)

    if first == last:
        return str(first)

    return f"{first}–{last}"


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    return value
