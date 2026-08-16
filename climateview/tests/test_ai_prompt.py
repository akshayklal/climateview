import pandas as pd

from climateview.ai.prompt_builder import (
    QUESTION_INSTRUCTIONS,
    SUMMARY_INSTRUCTIONS,
    build_ai_request,
    build_summary_payload,
)
from climateview.charts import select_referenced_periods
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)


def test_decade_payload_explains_period_semantics() -> None:
    dataframe = pd.DataFrame(
        {
            "decade": [1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020],
            "temperature_f": [51.0, 51.2, 51.1, 51.4, 50.3, 51.6, 52.4, 53.1, 54.6],
        }
    )
    analysis = analyze_series(
        dataframe=dataframe,
        context=AnalysisContext(
            location="Boise Air Terminal, ID",
            metric="temperature",
            unit="degrees Fahrenheit",
            aggregation="decade",
            start_period=1940,
            end_period=2025,
        ),
        schema=DataSchema(
            period_column="decade",
            value_column="temperature_f",
        ),
    )

    payload = build_summary_payload(analysis)
    assert "decade buckets" in payload["chart_context"]["period_note"]
    assert payload["chart_context"]["data_period"] == ["1940s", "2020s"]
    assert "data_quality" not in payload
    assert payload["descriptive_statistics"]["minimum"]["period"] == "1980s"
    assert payload["descriptive_statistics"]["maximum"]["period"] == "2020s"
    assert payload["recent_change"]["baseline_period"] == "1940s–1990s"
    assert payload["recent_change"]["recent_period"] == "2000s–2020s"
    instructions, prompt = build_ai_request(analysis)
    assert instructions == SUMMARY_INSTRUCTIONS
    assert "not record endpoints" in instructions
    assert "70 to 110 words" in instructions
    assert "no more than ten referenced_periods" in instructions
    assert "never as a percentage" in instructions
    assert "2020s are decade buckets" in prompt
    assert "percent_change" not in payload["recent_change"]
    assert "chart_findings" in payload
    assert "Use at most one" in instructions
    assert "Never enumerate" in instructions

    instructions, prompt = build_ai_request(
        analysis,
        "Which decade was warmest?",
    )
    assert instructions == QUESTION_INSTRUCTIONS
    assert "Which decade was warmest?" in prompt
    assert "referenced_periods" in instructions

    highlighted = select_referenced_periods(
        dataframe,
        "decade",
        ["2020s"],
    )
    assert highlighted["decade"].tolist() == [2020]


def test_annual_payload_prioritizes_first_and_latest_ten_years() -> None:
    dataframe = pd.DataFrame(
        {
            "year": range(1980, 2010),
            "rainfall": [10.0] * 10 + [15.0] * 10 + [12.0] * 10,
        }
    )
    analysis = analyze_series(
        dataframe=dataframe,
        context=AnalysisContext(
            location="Example, NV",
            metric="precipitation",
            unit="inches",
            aggregation="year",
            start_period=1980,
            end_period=2009,
        ),
        schema=DataSchema(period_column="year", value_column="rainfall"),
    )

    payload = build_summary_payload(analysis)

    assert payload["period_comparison"] == {
        "first_period": "1980–1989",
        "latest_period": "2000–2009",
        "first_mean": 10.0,
        "latest_mean": 12.0,
        "absolute_change": 2.0,
        "percent_change": 20.0,
    }
    assert "recent_change" not in payload
