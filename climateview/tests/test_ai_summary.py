from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from climateview.ai import summarize_analysis
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
    aggregate it into calendar-year totals.
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


def test_generate_real_precipitation_summary() -> None:
    """
    Generate an AI interpretation from the real San Francisco
    precipitation analysis.

    Run with pytest -s to display the generated summary.
    """

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not configured.")

    chart_df = load_san_francisco_annual_precipitation()

    analysis = analyze_series(
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

    response = summarize_analysis(analysis)

    assert response.text.strip()
    assert response.model.strip()

    print("\nAI SUMMARY:\n")
    print(response.text)
    print(f"\nMODEL: {response.model}\n")