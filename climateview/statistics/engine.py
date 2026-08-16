from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .generic import (
    calculate_data_quality,
    calculate_descriptive_statistics,
    calculate_extremes,
    calculate_recent_change_statistics,
    calculate_ranked_extremes,
    calculate_trend_statistics,
    calculate_variability_statistics,
    prepare_series,
    to_python_scalar,
)
from .models import (
    AnalysisContext,
    AnalysisResult,
    DataSchema,
)
from .precipitation import calculate_precipitation_statistics


def analyze_series(
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    schema: DataSchema,
) -> AnalysisResult:
    """
    Analyze a filtered climate time series.

    This is the main entry point into the statistics engine.

    Parameters
    ----------
    dataframe
        The SAME dataframe used to render the visible chart.

    context
        Describes the chart being analyzed.

    Returns
    -------
    AnalysisResult
    """

    period_column = schema.period_column
    value_column = schema.value_column

    # ------------------------------------------------------------------
    # Normalize / clean
    # ------------------------------------------------------------------

    prepared = prepare_series(
        dataframe=dataframe,
        period_column=period_column,
        value_column=value_column,
    )

    # ------------------------------------------------------------------
    # Generic statistics
    # ------------------------------------------------------------------

    data_quality = calculate_data_quality(
        dataframe=prepared,
        period_column=period_column,
    )

    descriptive = calculate_descriptive_statistics(
        prepared[value_column]
    )

    minimum, maximum = calculate_extremes(
        dataframe=prepared,
        period_column=period_column,
        value_column=value_column,
    )

    variability = calculate_variability_statistics(
        prepared[value_column]
    )

    trend = calculate_trend_statistics(
        dataframe=prepared,
        period_column=period_column,
        value_column=value_column,
    )

    recent_change = calculate_recent_change_statistics(
        dataframe=prepared,
        period_column=period_column,
        value_column=value_column,
    )

    rankings = {
        context.metric: calculate_ranked_extremes(
            dataframe=prepared,
            period_column=period_column,
            value_column=value_column,
        )
    }
    for label, ranking_value_column in schema.ranked_value_columns.items():
        ranking_series = prepare_series(
            dataframe=dataframe,
            period_column=period_column,
            value_column=ranking_value_column,
        )
        rankings[label] = calculate_ranked_extremes(
            dataframe=ranking_series,
            period_column=period_column,
            value_column=ranking_value_column,
        )

    # ------------------------------------------------------------------
    # Metric-specific statistics
    # ------------------------------------------------------------------

    metric_specific = _calculate_metric_statistics(
        dataframe=prepared,
        context=context,
        schema=schema,
    )
    noteworthy_findings = _calculate_noteworthy_findings(
        dataframe=dataframe,
        context=context,
        schema=schema,
        primary_trend=trend,
    )

    # ------------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------------

    return AnalysisResult(
        context=context,
        data_quality=data_quality,
        descriptive=descriptive,
        trend=trend,
        variability=variability,
        minimum=minimum,
        maximum=maximum,
        recent_change=recent_change,
        rankings=rankings,
        metric_specific=metric_specific,
        noteworthy_findings=noteworthy_findings,
    )


def _calculate_noteworthy_findings(
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    schema: DataSchema,
    primary_trend,
) -> list[dict[str, Any]]:
    """Identify verified observations within the currently displayed chart."""
    series = {context.metric: schema.value_column, **schema.ranked_value_columns}
    findings: list[dict[str, Any]] = []
    slopes: dict[str, float] = {}

    for label, value_column in series.items():
        prepared = prepare_series(
            dataframe,
            schema.period_column,
            value_column,
        )
        trend = primary_trend
        if label != context.metric:
            trend = calculate_trend_statistics(
                prepared,
                schema.period_column,
                value_column,
            )
            if trend and trend.statistically_significant:
                findings.append(
                    {
                        "type": "supporting_series_trend",
                        "series": label,
                        "direction": trend.direction,
                        "slope_per_year": round(trend.slope, 4),
                    }
                )
        if trend and trend.slope is not None:
            slopes[label] = trend.slope

        if len(prepared) < 8:
            continue
        recent_count = max(3, round(len(prepared) * 0.25))
        recent = prepared.tail(recent_count)
        recent_periods = set(recent[schema.period_column])
        ranked_count = min(10, max(3, round(len(prepared) * 0.15)))
        threshold = max(2, int(np.ceil(ranked_count * 0.6)))
        for direction, ascending in (("highest", False), ("lowest", True)):
            ranked_periods = prepared.sort_values(
                value_column,
                ascending=ascending,
            ).head(ranked_count)[schema.period_column]
            count = sum(period in recent_periods for period in ranked_periods)
            if count >= threshold:
                findings.append(
                    {
                        "type": "recent_extremes_cluster",
                        "series": label,
                        "direction": direction,
                        "count": count,
                        "ranked_count": ranked_count,
                        "recent_start": to_python_scalar(
                            recent.iloc[0][schema.period_column]
                        ),
                        "recent_end": to_python_scalar(
                            recent.iloc[-1][schema.period_column]
                        ),
                    }
                )

    if "temperature" in context.metric.lower() and len(slopes) >= 3:
        supporting = {
            label: slope
            for label, slope in slopes.items()
            if label != context.metric
        }
        if len(supporting) >= 2:
            fastest = max(supporting, key=supporting.get)
            slowest = min(supporting, key=supporting.get)
            if abs(supporting[fastest] - supporting[slowest]) >= 0.01:
                findings.append(
                    {
                        "type": "series_trend_difference",
                        "faster_series": fastest,
                        "faster_slope_per_year": round(supporting[fastest], 4),
                        "slower_series": slowest,
                        "slower_slope_per_year": round(supporting[slowest], 4),
                    }
                )

    return findings


def _calculate_metric_statistics(
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    schema: DataSchema,
) -> dict[str, Any]:
    """
    Dispatch to the appropriate metric-specific analyzer.
    """

    metric = context.metric.lower()

    if metric == "precipitation":
        return calculate_precipitation_statistics(
            dataframe=dataframe,
            period_column=schema.period_column,
            value_column=schema.value_column,
            aggregation=context.aggregation,
        )

    #
    # Future metrics
    #

    # if metric == "temperature":
    #     return calculate_temperature_statistics(...)

    # if metric in {"pm2.5", "ozone"}:
    #     return calculate_air_quality_statistics(...)

    return {}
