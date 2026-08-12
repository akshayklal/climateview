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

    working = prepared.copy()
    working["_year"] = years
    working["_decade_start"] = (working["_year"] // 10) * 10

    grouped = (
        working.groupby("_decade_start", as_index=False)
        .agg(
            mean_value=(value_column, "mean"),
            observation_count=(value_column, "count"),
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
                "complete": observation_count == expected_count,
            }
        )

    complete_decades = [
        decade for decade in decades if decade["complete"]
    ]

    recent_pattern = _recent_decadal_pattern(complete_decades)

    return {
        "available": True,
        "decades": decades,
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


def _extract_years(periods: pd.Series) -> np.ndarray:
    years = pd.to_numeric(periods, errors="raise").astype(int).to_numpy()
    if not np.all((years >= 1000) & (years <= 3000)):
        raise ValueError("Annual precipitation periods must be years.")
    return years


def _extract_month_numbers(
    periods: pd.Series,
) -> np.ndarray:
    return pd.to_datetime(periods, errors="raise").dt.month.to_numpy(dtype=int)


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
