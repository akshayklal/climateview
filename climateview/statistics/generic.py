from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
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

    Duplicate periods are preserved so that data-quality checks can report
    them. The engine or calling code should decide whether duplicates are
    expected for the selected aggregation.
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
    value_column: str,
    expected_periods: Sequence[Any] | None = None,
) -> DataQualityStatistics:
    """
    Calculate observation counts, missing periods, completeness, and duplicates.

    When expected_periods is supplied, missing_count and completeness_percent
    are calculated against that sequence. Otherwise, completeness is based on
    the rows provided to the function.
    """

    if period_column not in dataframe.columns:
        raise ValueError(f"Period column not found: {period_column}")

    if value_column not in dataframe.columns:
        raise ValueError(f"Value column not found: {value_column}")

    working = dataframe[[period_column, value_column]].copy()
    numeric_values = pd.to_numeric(working[value_column], errors="coerce")

    valid_mask = (
        working[period_column].notna()
        & numeric_values.notna()
        & np.isfinite(numeric_values.fillna(np.nan).to_numpy(dtype=float))
    )

    valid = working.loc[valid_mask].copy()
    valid[value_column] = numeric_values.loc[valid_mask]

    if valid.empty:
        raise ValueError("No valid observations are available.")

    observation_count = len(valid)
    duplicate_period_count = int(valid[period_column].duplicated().sum())

    if expected_periods is not None:
        expected = list(expected_periods)
        expected_observation_count = len(expected)

        observed_periods = set(valid[period_column].tolist())
        missing_count = sum(
            1 for period in expected if period not in observed_periods
        )

        completeness_percent = (
            100.0 * (expected_observation_count - missing_count)
            / expected_observation_count
            if expected_observation_count > 0
            else 0.0
        )
    else:
        expected_observation_count = len(working)
        missing_count = int(len(working) - observation_count)

        completeness_percent = (
            100.0 * observation_count / expected_observation_count
            if expected_observation_count > 0
            else 0.0
        )

    sorted_valid = valid.sort_values(period_column)

    return DataQualityStatistics(
        observation_count=observation_count,
        missing_count=missing_count,
        completeness_percent=float(completeness_percent),
        first_period=_to_python_scalar(
            sorted_valid.iloc[0][period_column]
        ),
        last_period=_to_python_scalar(
            sorted_valid.iloc[-1][period_column]
        ),
        expected_observation_count=expected_observation_count,
        duplicate_period_count=duplicate_period_count,
    )


def calculate_descriptive_statistics(
    values: pd.Series | Sequence[float],
    include_sum: bool = False,
) -> DescriptiveStatistics:
    """
    Calculate basic descriptive statistics for a numeric series.
    """

    numeric = _clean_numeric_values(values)

    if numeric.size == 0:
        raise ValueError("At least one valid numeric value is required.")

    standard_deviation = (
        float(np.std(numeric, ddof=1))
        if numeric.size > 1
        else 0.0
    )

    return DescriptiveStatistics(
        mean=float(np.mean(numeric)),
        median=float(np.median(numeric)),
        minimum=float(np.min(numeric)),
        maximum=float(np.max(numeric)),
        standard_deviation=standard_deviation,
        sum=float(np.sum(numeric)) if include_sum else None,
    )


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

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    minimum_index = prepared[value_column].idxmin()
    maximum_index = prepared[value_column].idxmax()

    minimum_row = prepared.loc[minimum_index]
    maximum_row = prepared.loc[maximum_index]

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

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    def serialize(rows: pd.DataFrame) -> list[ExtremeValue]:
        return [
            ExtremeValue(
                period=_to_python_scalar(row[period_column]),
                value=float(row[value_column]),
            )
            for _, row in rows.iterrows()
        ]

    highest = prepared.sort_values(
        [value_column, period_column],
        ascending=[False, True],
    ).head(limit)
    lowest = prepared.sort_values(
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

    range_value = float(np.max(numeric) - np.min(numeric))

    interquartile_range = (
        float(stats.iqr(numeric, rng=(25, 75)))
        if numeric.size > 1
        else 0.0
    )

    if np.isclose(mean, 0.0):
        coefficient_of_variation = None
        variability_level = _classify_variability_without_cv(
            numeric=numeric,
            standard_deviation=standard_deviation,
        )
    else:
        coefficient_of_variation = abs(standard_deviation / mean)
        variability_level = classify_variability(
            coefficient_of_variation
        )

    return VariabilityStatistics(
        standard_deviation=standard_deviation,
        coefficient_of_variation=(
            float(coefficient_of_variation)
            if coefficient_of_variation is not None
            else None
        ),
        variability_level=variability_level,
        range_value=range_value,
        interquartile_range=interquartile_range,
    )


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

    The period column may contain numeric values, datetimes, or labels.
    Numeric periods are used directly. Datetimes are converted to elapsed
    years. Other labels are converted to sequential positions.

    Returns None when fewer than three valid observations are available or
    when the x-axis has no variation.
    """

    if not 0.0 < significance_level < 1.0:
        raise ValueError(
            "significance_level must be between 0 and 1."
        )

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    if len(prepared) < MIN_TREND_OBSERVATIONS:
        return None

    x = _periods_to_numeric(prepared[period_column])
    y = prepared[value_column].to_numpy(dtype=float)

    if np.allclose(x, x[0]):
        return None

    regression = stats.linregress(x, y)

    slope = float(regression.slope)
    p_value = float(regression.pvalue)
    standard_error = float(regression.stderr)

    degrees_of_freedom = len(x) - 2

    if degrees_of_freedom > 0 and isfinite(standard_error):
        critical_value = float(
            stats.t.ppf(
                1.0 - significance_level / 2.0,
                degrees_of_freedom,
            )
        )

        margin = critical_value * standard_error
        confidence_interval_low = slope - margin
        confidence_interval_high = slope + margin
    else:
        confidence_interval_low = None
        confidence_interval_high = None

    x_span = float(np.max(x) - np.min(x))
    total_fitted_change = slope * x_span

    statistically_significant = (
        isfinite(p_value) and p_value < significance_level
    )

    direction = classify_trend_direction(
        slope=slope,
        confidence_interval_low=confidence_interval_low,
        confidence_interval_high=confidence_interval_high,
        statistically_significant=statistically_significant,
    )

    return TrendStatistics(
        slope_per_period=slope,
        total_fitted_change=float(total_fitted_change),
        direction=direction,
        statistically_significant=statistically_significant,
        p_value=p_value if isfinite(p_value) else None,
        confidence_interval_low=(
            float(confidence_interval_low)
            if confidence_interval_low is not None
            else None
        ),
        confidence_interval_high=(
            float(confidence_interval_high)
            if confidence_interval_high is not None
            else None
        ),
        r_squared=float(regression.rvalue**2),
    )


def classify_trend_direction(
    slope: float,
    confidence_interval_low: float | None,
    confidence_interval_high: float | None,
    statistically_significant: bool,
) -> str:
    """
    Classify a regression trend as increasing, decreasing, or stable.

    A non-significant slope is labeled stable because the engine should avoid
    presenting weak evidence as a meaningful directional trend.
    """

    if not statistically_significant:
        return "stable"

    if (
        confidence_interval_low is not None
        and confidence_interval_high is not None
        and confidence_interval_low <= 0.0 <= confidence_interval_high
    ):
        return "stable"

    if slope > 0:
        return "increasing"

    if slope < 0:
        return "decreasing"

    return "stable"


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

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    observation_count = len(prepared)

    recent_count = max(
        minimum_recent_observations,
        int(round(observation_count * recent_fraction)),
    )

    if recent_count >= observation_count:
        return None

    baseline = prepared.iloc[:-recent_count]
    recent = prepared.iloc[-recent_count:]

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


def calculate_standardized_anomalies(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
) -> pd.DataFrame:
    """
    Return the cleaned series with a z_score column.

    When the series has zero standard deviation, every z-score is set to 0.
    """

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    values = prepared[value_column].to_numpy(dtype=float)
    mean = float(np.mean(values))

    standard_deviation = (
        float(np.std(values, ddof=1))
        if values.size > 1
        else 0.0
    )

    if np.isclose(standard_deviation, 0.0):
        prepared["z_score"] = 0.0
    else:
        prepared["z_score"] = (
            prepared[value_column] - mean
        ) / standard_deviation

    return prepared


def calculate_consecutive_direction_runs(
    values: pd.Series | Sequence[float],
) -> dict[str, int]:
    """
    Calculate the longest consecutive increasing and decreasing runs.

    Run lengths represent the number of transitions, not the number of data
    points. For example, values [1, 2, 3] contain two increasing transitions.
    """

    numeric = _clean_numeric_values(values)

    if numeric.size < 2:
        return {
            "longest_increasing_run": 0,
            "longest_decreasing_run": 0,
        }

    differences = np.diff(numeric)

    longest_increasing = _longest_boolean_run(differences > 0)
    longest_decreasing = _longest_boolean_run(differences < 0)

    return {
        "longest_increasing_run": longest_increasing,
        "longest_decreasing_run": longest_decreasing,
    }


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

    parsed_datetimes = pd.to_datetime(periods, errors="coerce")

    if parsed_datetimes.notna().all():
        elapsed_days = (
            parsed_datetimes - parsed_datetimes.iloc[0]
        ).dt.total_seconds() / 86_400.0

        return elapsed_days.to_numpy(dtype=float) / 365.2425

    return np.arange(len(periods), dtype=float)


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


def _longest_boolean_run(mask: np.ndarray) -> int:
    longest = 0
    current = 0

    for value in mask:
        if bool(value):
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return longest


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    return value
