from __future__ import annotations

import pandas as pd
import pytest

from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)


@pytest.fixture
def annual_precipitation_df() -> pd.DataFrame:
    """
    Synthetic annual precipitation data with:

    - a clear upward trend;
    - a minimum in 2000;
    - a maximum in 2019;
    - two complete decades.
    """

    years = list(range(2000, 2020))
    precipitation = [
        10.0,
        10.5,
        11.0,
        11.5,
        12.0,
        12.5,
        13.0,
        13.5,
        14.0,
        14.5,
        15.0,
        15.5,
        16.0,
        16.5,
        17.0,
        17.5,
        18.0,
        18.5,
        19.0,
        19.5,
    ]

    return pd.DataFrame(
        {
            "year": years,
            "precipitation_inches": precipitation,
        }
    )


@pytest.fixture
def analysis_context() -> AnalysisContext:
    return AnalysisContext(
        location="Test Location",
        metric="precipitation",
        unit="inches",
        aggregation="calendar_year",
        start_period=2000,
        end_period=2019,
    )


@pytest.fixture
def data_schema() -> DataSchema:
    return DataSchema(
        period_column="year",
        value_column="precipitation_inches",
    )


def test_analyze_precipitation_series(
    annual_precipitation_df: pd.DataFrame,
    analysis_context: AnalysisContext,
    data_schema: DataSchema,
) -> None:
    result = analyze_series(
        dataframe=annual_precipitation_df,
        context=analysis_context,
        schema=data_schema,
    )

    assert result.context == analysis_context

    assert result.data_quality.observation_count == 20
    assert result.data_quality.missing_count == 0
    assert result.data_quality.completeness_percent == pytest.approx(100.0)
    assert result.data_quality.first_period == 2000
    assert result.data_quality.last_period == 2019
    assert result.data_quality.duplicate_period_count == 0

    assert result.descriptive.mean == pytest.approx(14.75)
    assert result.descriptive.median == pytest.approx(14.75)
    assert result.descriptive.minimum == pytest.approx(10.0)
    assert result.descriptive.maximum == pytest.approx(19.5)

    assert result.minimum.period == 2000
    assert result.minimum.value == pytest.approx(10.0)

    assert result.maximum.period == 2019
    assert result.maximum.value == pytest.approx(19.5)

    assert [
        item.period
        for item in result.rankings["precipitation"]["highest"][:3]
    ] == [2019, 2018, 2017]
    assert [
        item.period
        for item in result.rankings["precipitation"]["lowest"][:3]
    ] == [2000, 2001, 2002]

    assert result.trend is not None
    assert result.trend.slope_per_period == pytest.approx(0.5)
    assert result.trend.total_fitted_change == pytest.approx(9.5)
    assert result.trend.direction == "increasing"
    assert result.trend.statistically_significant is True
    assert result.trend.r_squared == pytest.approx(1.0)

    assert result.recent_change is not None
    assert result.recent_change.recent_mean > (
        result.recent_change.baseline_mean
    )

    assert result.metric_specific["directionality"] == "context_dependent"

    decadal = result.metric_specific["decadal_analysis"]

    assert decadal["available"] is True
    assert len(decadal["decades"]) == 2
    assert decadal["decades"][0]["label"] == "2000s"
    assert decadal["decades"][1]["label"] == "2010s"
    assert decadal["decades"][0]["complete"] is True
    assert decadal["decades"][1]["complete"] is True
    assert decadal["current_decade_incomplete"] is False

    assert len(result.insights) > 0
    assert any(
        insight.insight_type == "significant_trend"
        for insight in result.insights
    )


def test_result_can_be_converted_to_dictionary(
    annual_precipitation_df: pd.DataFrame,
    analysis_context: AnalysisContext,
    data_schema: DataSchema,
) -> None:
    result = analyze_series(
        dataframe=annual_precipitation_df,
        context=analysis_context,
        schema=data_schema,
    )

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["context"]["metric"] == "precipitation"
    assert result_dict["context"]["location"] == "Test Location"
    assert result_dict["descriptive"]["mean"] == pytest.approx(14.75)
    assert result_dict["trend"]["direction"] == "increasing"
    assert isinstance(result_dict["insights"], list)


def test_invalid_value_column_raises_error(
    annual_precipitation_df: pd.DataFrame,
    analysis_context: AnalysisContext,
) -> None:
    invalid_schema = DataSchema(
        period_column="year",
        value_column="does_not_exist",
    )

    with pytest.raises(ValueError, match="Value column not found"):
        analyze_series(
            dataframe=annual_precipitation_df,
            context=analysis_context,
            schema=invalid_schema,
        )


def test_rows_with_missing_values_are_removed(
    analysis_context: AnalysisContext,
    data_schema: DataSchema,
) -> None:
    dataframe = pd.DataFrame(
        {
            "year": [2000, 2001, 2002, 2003],
            "precipitation_inches": [10.0, None, 12.0, 13.0],
        }
    )

    result = analyze_series(
        dataframe=dataframe,
        context=analysis_context,
        schema=data_schema,
    )

    assert result.data_quality.observation_count == 3
    assert result.minimum.period == 2000
    assert result.maximum.period == 2003


def test_additional_series_can_be_ranked(
    annual_precipitation_df: pd.DataFrame,
    analysis_context: AnalysisContext,
) -> None:
    dataframe = annual_precipitation_df.assign(
        secondary=list(reversed(range(20)))
    )
    result = analyze_series(
        dataframe=dataframe,
        context=analysis_context,
        schema=DataSchema(
            period_column="year",
            value_column="precipitation_inches",
            ranked_value_columns={"secondary metric": "secondary"},
        ),
    )

    assert result.rankings["secondary metric"]["highest"][0].period == 2000
    assert result.rankings["secondary metric"]["lowest"][0].period == 2019
