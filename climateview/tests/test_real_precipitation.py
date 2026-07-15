from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PRECIPITATION_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "noaa-precipitation"
    / "USW00023174_daily_precipitation.csv"
)


def load_san_francisco_annual_precipitation() -> pd.DataFrame:
    """
    Load the processed San Francisco/SFO daily precipitation file and
    aggregate it into calendar-year totals, matching the chart view.
    """

    if not PRECIPITATION_FILE.exists():
        pytest.skip(
            f"Processed precipitation file not found: "
            f"{PRECIPITATION_FILE}"
        )

    dataframe = pd.read_csv(
        PRECIPITATION_FILE,
        parse_dates=["date"],
    )

    dataframe["year"] = dataframe["date"].dt.year

    annual = (
        dataframe.groupby("year", as_index=False)["prcp_in"]
        .sum()
        .sort_values("year")
        .reset_index(drop=True)
    )

    return annual[
        annual["year"].between(1946, 2025)
    ].reset_index(drop=True)


def test_real_san_francisco_precipitation() -> None:
    chart_df = load_san_francisco_annual_precipitation()

    context = AnalysisContext(
        location="San Francisco / SFO, CA",
        metric="precipitation",
        unit="inches",
        aggregation="calendar_year",
        start_period=1946,
        end_period=2025,
    )

    schema = DataSchema(
        period_column="year",
        value_column="prcp_in",
    )

    result = analyze_series(
        dataframe=chart_df,
        context=context,
        schema=schema,
    )

    assert result.data_quality.observation_count == 80
    assert result.data_quality.first_period == 1946
    assert result.data_quality.last_period == 2025

    assert result.descriptive.mean == pytest.approx(
        11.953625,
        abs=0.000001,
    )

    assert result.minimum.period == 1947
    assert result.minimum.value == pytest.approx(3.12)

    assert result.maximum.period == 1983
    assert result.maximum.value == pytest.approx(29.46)

    assert result.trend is not None
    assert result.trend.slope_per_period == pytest.approx(
        0.0209176,
        abs=0.000001,
    )
    assert result.trend.statistically_significant is False
    assert result.trend.direction == "stable"

    assert (
        result.metric_specific["directionality"]
        == "context_dependent"
    )

    decadal = result.metric_specific["decadal_analysis"]

    assert decadal["available"] is True
    assert decadal["current_decade_incomplete"] is True

    assert len(result.insights) > 0

    assert any(
        insight.insight_type == "high_variability"
        for insight in result.insights
    )

    assert any(
        insight.insight_type == "recent_decadal_decline"
        for insight in result.insights
    )


def test_print_real_san_francisco_analysis() -> None:
    """
    Diagnostic test used to inspect the complete statistics-engine output.

    Run pytest with -s to see the printed JSON.
    """

    chart_df = load_san_francisco_annual_precipitation()

    result = analyze_series(
        dataframe=chart_df,
        context=AnalysisContext(
            location="San Francisco / SFO, CA",
            metric="precipitation",
            unit="inches",
            aggregation="calendar_year",
            start_period=1946,
            end_period=2025,
        ),
        schema=DataSchema(
            period_column="year",
            value_column="prcp_in",
        ),
    )

    import json

    print(json.dumps(result.to_dict(), indent=2))