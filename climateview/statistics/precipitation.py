from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .generic import prepare_series


DEFAULT_DRY_THRESHOLD_RATIO = 0.75
DEFAULT_WET_THRESHOLD_RATIO = 1.25


def calculate_precipitation_statistics(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    aggregation: str,
) -> dict[str, Any]:
    """
    Calculate precipitation-specific statistics.

    The input dataframe should be the same filtered and aggregated dataframe
    used to render the visible chart.
    """

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    values = prepared[value_column].to_numpy(dtype=float)
    mean_value = float(np.mean(values))

    result: dict[str, Any] = {
        "directionality": "context_dependent",
        "wettest_period": _extreme_period(
            prepared,
            period_column,
            value_column,
            find_maximum=True,
        ),
        "driest_period": _extreme_period(
            prepared,
            period_column,
            value_column,
            find_maximum=False,
        ),
        "dry_wet_periods": calculate_dry_wet_periods(
            dataframe=prepared,
            period_column=period_column,
            value_column=value_column,
            baseline_mean=mean_value,
        ),
        "consecutive_runs": calculate_precipitation_runs(
            dataframe=prepared,
            value_column=value_column,
            baseline_mean=mean_value,
        ),
    }

    aggregation_key = aggregation.strip().lower().replace(" ", "_")

    if aggregation_key in {
        "calendar_year",
        "rain_year",
        "water_year",
        "annual",
        "year",
    }:
        result["decadal_analysis"] = calculate_decadal_statistics(
            dataframe=prepared,
            period_column=period_column,
            value_column=value_column,
        )

    if aggregation_key in {
        "month",
        "monthly",
        "calendar_month",
    }:
        result["seasonality"] = calculate_monthly_seasonality(
            dataframe=prepared,
            period_column=period_column,
            value_column=value_column,
        )

    return result


def calculate_dry_wet_periods(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    baseline_mean: float | None = None,
    dry_threshold_ratio: float = DEFAULT_DRY_THRESHOLD_RATIO,
    wet_threshold_ratio: float = DEFAULT_WET_THRESHOLD_RATIO,
) -> dict[str, Any]:
    """
    Count unusually dry and wet periods relative to the selected-period mean.

    A dry period is below 75% of the mean by default.
    A wet period is above 125% of the mean by default.
    """

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    if baseline_mean is None:
        baseline_mean = float(prepared[value_column].mean())

    if baseline_mean <= 0:
        return {
            "baseline_mean": baseline_mean,
            "dry_threshold": None,
            "wet_threshold": None,
            "dry_period_count": 0,
            "wet_period_count": 0,
            "dry_periods": [],
            "wet_periods": [],
        }

    dry_threshold = baseline_mean * dry_threshold_ratio
    wet_threshold = baseline_mean * wet_threshold_ratio

    dry_rows = prepared[prepared[value_column] < dry_threshold]
    wet_rows = prepared[prepared[value_column] > wet_threshold]

    return {
        "baseline_mean": float(baseline_mean),
        "dry_threshold": float(dry_threshold),
        "wet_threshold": float(wet_threshold),
        "dry_period_count": int(len(dry_rows)),
        "wet_period_count": int(len(wet_rows)),
        "dry_periods": [
            {
                "period": _to_python_scalar(row[period_column]),
                "value": float(row[value_column]),
            }
            for _, row in dry_rows.iterrows()
        ],
        "wet_periods": [
            {
                "period": _to_python_scalar(row[period_column]),
                "value": float(row[value_column]),
            }
            for _, row in wet_rows.iterrows()
        ],
    }


def calculate_precipitation_runs(
    dataframe: pd.DataFrame,
    value_column: str,
    baseline_mean: float | None = None,
    dry_threshold_ratio: float = DEFAULT_DRY_THRESHOLD_RATIO,
    wet_threshold_ratio: float = DEFAULT_WET_THRESHOLD_RATIO,
) -> dict[str, int]:
    """
    Calculate longest consecutive dry and wet runs.

    Run lengths are measured in observations.
    """

    values = dataframe[value_column].to_numpy(dtype=float)

    if baseline_mean is None:
        baseline_mean = float(np.mean(values))

    if baseline_mean <= 0:
        return {
            "longest_dry_run": 0,
            "longest_wet_run": 0,
        }

    dry_mask = values < baseline_mean * dry_threshold_ratio
    wet_mask = values > baseline_mean * wet_threshold_ratio

    return {
        "longest_dry_run": _longest_boolean_run(dry_mask),
        "longest_wet_run": _longest_boolean_run(wet_mask),
    }


def calculate_decadal_statistics(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
) -> dict[str, Any]:
    """
    Calculate averages and changes for calendar decades.

    This expects the period column to contain years or year-like values.
    """

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    years = _extract_years(prepared[period_column])

    if years is None:
        return {
            "available": False,
            "reason": "Period values could not be converted to years.",
        }

    working = prepared.copy()
    working["_year"] = years
    working["_decade_start"] = (working["_year"] // 10) * 10

    grouped = (
        working.groupby("_decade_start", as_index=False)
        .agg(
            mean_value=(value_column, "mean"),
            observation_count=(value_column, "count"),
            first_year=("_year", "min"),
            last_year=("_year", "max"),
        )
        .sort_values("_decade_start")
        .reset_index(drop=True)
    )

    decades: list[dict[str, Any]] = []

    for _, row in grouped.iterrows():
        decade_start = int(row["_decade_start"])
        expected_count = 10
        observation_count = int(row["observation_count"])

        decades.append(
            {
                "decade_start": decade_start,
                "label": f"{decade_start}s",
                "mean": float(row["mean_value"]),
                "observation_count": observation_count,
                "expected_observation_count": expected_count,
                "complete": observation_count == expected_count,
                "first_year": int(row["first_year"]),
                "last_year": int(row["last_year"]),
            }
        )

    changes: list[dict[str, Any]] = []

    for previous, current in zip(decades, decades[1:]):
        absolute_change = current["mean"] - previous["mean"]

        percent_change = (
            absolute_change / abs(previous["mean"]) * 100.0
            if not np.isclose(previous["mean"], 0.0)
            else None
        )

        changes.append(
            {
                "from_decade": previous["label"],
                "to_decade": current["label"],
                "absolute_change": float(absolute_change),
                "percent_change": (
                    float(percent_change)
                    if percent_change is not None
                    else None
                ),
                "direction": _change_direction(absolute_change),
                "to_decade_complete": current["complete"],
            }
        )

    complete_decades = [
        decade for decade in decades if decade["complete"]
    ]

    recent_pattern = _recent_decadal_pattern(complete_decades)

    return {
        "available": True,
        "decades": decades,
        "changes": changes,
        "recent_pattern": recent_pattern,
        "current_decade_incomplete": bool(
            decades and not decades[-1]["complete"]
        ),
    }


def calculate_monthly_seasonality(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
) -> dict[str, Any]:
    """
    Estimate precipitation seasonality from monthly observations.

    The period column may contain month numbers, month names, or dates.
    """

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    month_numbers = _extract_month_numbers(prepared[period_column])

    if month_numbers is None:
        return {
            "available": False,
            "reason": "Period values could not be converted to months.",
        }

    working = prepared.copy()
    working["_month"] = month_numbers

    monthly = (
        working.groupby("_month", as_index=False)[value_column]
        .mean()
        .rename(columns={value_column: "mean_value"})
        .sort_values("_month")
    )

    total_monthly_mean = float(monthly["mean_value"].sum())

    if np.isclose(total_monthly_mean, 0.0):
        concentration_index = None
    else:
        shares = monthly["mean_value"] / total_monthly_mean
        concentration_index = float(np.sum(np.square(shares)))

    wettest_row = monthly.loc[monthly["mean_value"].idxmax()]
    driest_row = monthly.loc[monthly["mean_value"].idxmin()]

    top_three_total = float(
        monthly.nlargest(3, "mean_value")["mean_value"].sum()
    )

    top_three_share = (
        top_three_total / total_monthly_mean * 100.0
        if not np.isclose(total_monthly_mean, 0.0)
        else None
    )

    return {
        "available": True,
        "monthly_means": [
            {
                "month": int(row["_month"]),
                "mean": float(row["mean_value"]),
            }
            for _, row in monthly.iterrows()
        ],
        "wettest_month": {
            "month": int(wettest_row["_month"]),
            "mean": float(wettest_row["mean_value"]),
        },
        "driest_month": {
            "month": int(driest_row["_month"]),
            "mean": float(driest_row["mean_value"]),
        },
        "top_three_month_share_percent": (
            float(top_three_share)
            if top_three_share is not None
            else None
        ),
        "concentration_index": concentration_index,
        "seasonality_level": _classify_seasonality(top_three_share),
    }


def _extreme_period(
    dataframe: pd.DataFrame,
    period_column: str,
    value_column: str,
    find_maximum: bool,
) -> dict[str, Any]:
    index = (
        dataframe[value_column].idxmax()
        if find_maximum
        else dataframe[value_column].idxmin()
    )

    row = dataframe.loc[index]

    return {
        "period": _to_python_scalar(row[period_column]),
        "value": float(row[value_column]),
    }


def _recent_decadal_pattern(
    complete_decades: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(complete_decades) < 2:
        return {
            "direction": "insufficient_data",
            "consecutive_declines": 0,
            "consecutive_increases": 0,
        }

    means = [decade["mean"] for decade in complete_decades]
    differences = np.diff(means)

    declining = _trailing_boolean_run(differences < 0)
    increasing = _trailing_boolean_run(differences > 0)

    if declining > 0:
        direction = "declining"
    elif increasing > 0:
        direction = "increasing"
    else:
        direction = "mixed_or_stable"

    return {
        "direction": direction,
        "consecutive_declines": declining,
        "consecutive_increases": increasing,
        "start_decade": complete_decades[-(max(declining, increasing) + 1)][
            "label"
        ]
        if max(declining, increasing) > 0
        else None,
        "end_decade": complete_decades[-1]["label"],
    }


def _extract_years(periods: pd.Series) -> np.ndarray | None:
    numeric = pd.to_numeric(periods, errors="coerce")

    if numeric.notna().all():
        years = numeric.astype(int).to_numpy()

        if np.all((years >= 1000) & (years <= 3000)):
            return years

    datetimes = pd.to_datetime(periods, errors="coerce")

    if datetimes.notna().all():
        return datetimes.dt.year.to_numpy(dtype=int)

    return None


def _extract_month_numbers(
    periods: pd.Series,
) -> np.ndarray | None:
    numeric = pd.to_numeric(periods, errors="coerce")

    if numeric.notna().all():
        months = numeric.astype(int).to_numpy()

        if np.all((months >= 1) & (months <= 12)):
            return months

    datetimes = pd.to_datetime(periods, errors="coerce")

    if datetimes.notna().all():
        return datetimes.dt.month.to_numpy(dtype=int)

    month_names = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    mapped = periods.astype(str).str.strip().str.lower().map(month_names)

    if mapped.notna().all():
        return mapped.to_numpy(dtype=int)

    return None


def _classify_seasonality(
    top_three_share_percent: float | None,
) -> str:
    if top_three_share_percent is None:
        return "unknown"

    if top_three_share_percent >= 60.0:
        return "strong"

    if top_three_share_percent >= 45.0:
        return "moderate"

    return "low"


def _change_direction(change: float) -> str:
    if np.isclose(change, 0.0):
        return "stable"

    return "increasing" if change > 0 else "decreasing"


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


def _trailing_boolean_run(mask: np.ndarray) -> int:
    count = 0

    for value in reversed(mask):
        if bool(value):
            count += 1
        else:
            break

    return count


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    return value