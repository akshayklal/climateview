from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from climateview.location_summaries import (
    _build_summary_sentence,
    _temperature_sentence,
    analyze_air_quality,
    analyze_precipitation,
    analyze_temperature,
    build_explorable_patterns,
    build_map_metrics,
)
from climateview.statistics.models import TrendStatistics


def _write_temperature(path: Path) -> None:
    rows = []
    for year in range(2000, 2020):
        for date in pd.date_range(f"{year}-01-01", f"{year}-12-31"):
            recent = year >= 2010
            seasonal_night_change = (
                4.0 if recent and date.month in (6, 7, 8) else 0.0
            )
            rows.append(
                {
                    "date": date,
                    "tmax_f": 70.0 + (2.0 if recent else 0.0),
                    "tmin_f": 50.0 + (2.0 if recent else 0.0)
                    + seasonal_night_change,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_precipitation(path: Path) -> None:
    rows = []
    for year in range(2000, 2020):
        annual_total = 10.0 + (year - 2000)
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        for date in dates:
            rows.append(
                {"date": date, "prcp_in": annual_total / len(dates)}
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_temperature_summary_compares_decades_and_finds_summer_nights(
    tmp_path: Path,
) -> None:
    path = tmp_path / "temperature.csv"
    _write_temperature(path)

    result = analyze_temperature(path)

    assert result["available"] is True
    assert result["baseline_period"] == "2000–2009"
    assert result["recent_period"] == "2010–2019"
    assert result["absolute_change"] > 2.0
    assert result["strongest_seasonal_change"]["season"] == "summer"
    assert result["strongest_seasonal_change"]["time_of_day"] == "nights"
    assert result["strongest_seasonal_change"]["trend_supported"] is True
    sentence = _temperature_sentence(result)
    assert "°F warmer" in sentence
    assert "summer nights" in sentence


def test_temperature_support_requires_matching_trend_direction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "temperature.csv"
    _write_temperature(path)

    with patch(
        "climateview.statistics.preprocessing.calculate_trend_statistics",
        return_value=TrendStatistics(
            direction="decreasing",
            statistically_significant=True,
        ),
    ):
        result = analyze_temperature(path)

    assert result["absolute_change"] > 0
    assert result["trend_supported"] is False
    assert result["strongest_seasonal_change"]["change_f"] > 0
    assert (
        result["strongest_seasonal_change"]["trend_supported"] is False
    )


def test_precipitation_summary_marks_clear_change_as_significant(
    tmp_path: Path,
) -> None:
    path = tmp_path / "precipitation.csv"
    _write_precipitation(path)

    result = analyze_precipitation(path)

    assert result["available"] is True
    assert result["significant_change"] is True
    assert result["percent_change"] == pytest.approx(68.9655, rel=0.01)


def test_air_quality_requires_two_complete_ten_year_periods(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pm25.csv"
    rows = []
    for year in range(2001, 2020):
        for day in range(100):
            rows.append(
                {
                    "date": pd.Timestamp(year=year, month=1, day=1)
                    + pd.Timedelta(days=day),
                    "value": 12.0,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)

    result = analyze_air_quality(path, "pm25")

    assert result == {"available": False}


def test_summary_sentence_omits_unchanged_precipitation() -> None:
    sentence = _build_summary_sentence(
        {
            "available": True,
            "absolute_change": 2.4,
            "baseline_period": "1950–1959",
        },
        {
            "available": True,
            "significant_change": False,
            "percent_change": -12.4,
            "baseline_period": "1950–1959",
        },
        {
            "pm25": {
                "available": True,
                "significant_change": True,
                "percent_change": -35.2,
                "baseline_period": "2000–2009",
            },
            "ozone": {"available": False},
        },
    )

    assert sentence == (
        "2.4°F warmer than 1950–1959; "
        "fine-particle pollution down 35% since 2000."
    )
    assert "precipitation" not in sentence


def test_map_metrics_include_only_supported_changes() -> None:
    metrics = build_map_metrics(
        {
            "available": True,
            "trend_supported": True,
            "baseline_mean": 50.0,
            "recent_mean": 53.25,
            "baseline_period": "1980–1989",
        },
        {
            "available": True,
            "significant_change": False,
            "baseline_mean": 20.0,
            "recent_mean": 22.0,
            "baseline_period": "1980–1989",
        },
        {
            "pm25": {
                "significant_change": True,
                "baseline_mean": 10.0,
                "recent_mean": 7.0,
                "baseline_period": "2000–2009",
            },
            "ozone": {"significant_change": False},
        },
    )

    assert metrics == {
        "temperature": {"change": 3.2},
        "pm25": {"change": -30.0},
    }


def test_explorable_patterns_require_supported_changes() -> None:
    summaries = {
        "example": {
            "temperature": {
                "available": True,
                "baseline_mean": 50.0,
                "recent_mean": 55.0,
                "baseline_period": "1980–1989",
                "trend_supported": False,
            },
            "precipitation": {
                "available": True,
                "baseline_mean": 20.0,
                "recent_mean": 25.0,
                "baseline_period": "1980–1989",
                "significant_change": False,
            },
            "air_quality": {
                "pm25": {
                    "baseline_mean": 10.0,
                    "recent_mean": 6.0,
                    "baseline_period": "2000–2009",
                    "significant_change": True,
                }
            },
        }
    }
    stations = {"example": {"name": "Example, ST"}}

    patterns = build_explorable_patterns(summaries, stations)

    assert [pattern["category"] for pattern in patterns] == [
        "fine_particles"
    ]
    assert patterns[0]["tab"] == "Air Quality"
    assert patterns[0]["pollutant"] == "pm25"
    assert patterns[0]["category_rank"] == 1
    assert patterns[0]["featured"] is True
    assert "down 40% since 2000" in patterns[0]["summary"]


def test_explorable_patterns_retain_candidates_beyond_featured_pool() -> None:
    summaries = {}
    stations = {}
    for index in range(16):
        key = f"station_{index}"
        stations[key] = {"name": f"Station {index}"}
        summaries[key] = {
            "temperature": {
                "available": True,
                "baseline_mean": 50.0,
                "recent_mean": 51.0 + index,
                "baseline_period": "1980–1989",
                "trend_supported": True,
            },
            "precipitation": {"available": False},
            "air_quality": {},
        }

    patterns = build_explorable_patterns(summaries, stations)

    assert len(patterns) == 16
    assert sum(pattern["featured"] for pattern in patterns) == 15
    assert sorted(pattern["category_rank"] for pattern in patterns) == list(
        range(1, 17)
    )
