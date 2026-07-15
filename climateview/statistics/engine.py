from __future__ import annotations

from typing import Any

import pandas as pd

from .generic import (
    calculate_data_quality,
    calculate_descriptive_statistics,
    calculate_extremes,
    calculate_recent_change_statistics,
    calculate_trend_statistics,
    calculate_variability_statistics,
    prepare_series,
)
from .insight_selector import select_insights
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
        value_column=value_column,
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

    # ------------------------------------------------------------------
    # Metric-specific statistics
    # ------------------------------------------------------------------

    metric_specific = _calculate_metric_statistics(
        dataframe=prepared,
        context=context,
        schema=schema,
    )

    # ------------------------------------------------------------------
    # Select important findings
    # ------------------------------------------------------------------

    insights = select_insights(
        context=context,
        data_quality=data_quality,
        descriptive=descriptive,
        trend=trend,
        variability=variability,
        minimum=minimum,
        maximum=maximum,
        recent_change=recent_change,
        metric_specific=metric_specific,
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
        metric_specific=metric_specific,
        insights=insights,
    )


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
