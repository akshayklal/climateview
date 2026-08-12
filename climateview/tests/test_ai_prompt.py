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
    semantics = payload["chart_context"]["period_semantics"]

    assert semantics["period_type"] == "decade_bucket"
    assert semantics["within_bucket_completeness_known"] is False
    assert "not the final source-data year" in semantics["label_meaning"]
    assert "not establish" in payload["data_quality"]["observation_count_scope"]
    assert "completeness_percent" not in payload["data_quality"]
    assert payload["data_quality"]["first_period"] == "1940s"
    assert payload["data_quality"]["last_period"] == "2020s"
    assert payload["descriptive_statistics"]["minimum"]["period"] == "1980s"
    assert payload["descriptive_statistics"]["maximum"]["period"] == "2020s"
    assert payload["recent_change"]["baseline_period"] == "1940s–1990s"
    assert payload["recent_change"]["recent_period"] == "2000s–2020s"
    instructions, prompt = build_ai_request(analysis)
    assert instructions == SUMMARY_INSTRUCTIONS
    assert "Never describe completeness" in instructions
    assert "not record endpoints" in instructions
    assert '"last_period": "2020s"' in prompt

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
