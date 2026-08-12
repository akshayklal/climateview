from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from climateview.ai.summarizer import generate_analysis_response
from climateview.statistics import AnalysisContext, DataSchema, analyze_series


@pytest.fixture
def analysis():
    return analyze_series(
        pd.DataFrame({"year": [2020, 2021, 2022], "value": [1.0, 2.0, 3.0]}),
        AnalysisContext("Test", "temperature", "°F", "year", 2020, 2022),
        DataSchema("year", "value"),
    )


def test_generate_analysis_response_preserves_structured_references(
    analysis,
) -> None:
    parsed = SimpleNamespace(
        text=" 2022 was highest. ",
        referenced_periods=["2022"],
        referenced_series=["temperature"],
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(output_parsed=parsed)
        )
    )

    with patch("climateview.ai.summarizer.OpenAI", return_value=client):
        response = generate_analysis_response(
            analysis,
            "Which year was highest?",
            api_key="test-key",
            model="test-model",
        )

    assert response.text == "2022 was highest."
    assert response.model == "test-model"
    assert response.referenced_periods == ("2022",)
    assert response.referenced_series == ("temperature",)


def test_generate_analysis_response_rejects_blank_question(analysis) -> None:
    with pytest.raises(ValueError, match="Question must not be empty"):
        generate_analysis_response(analysis, "   ", api_key="test-key")
