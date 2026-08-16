import pandas as pd

from climateview.temperature import (
    build_temperature_aggregation,
    filter_temperature_season,
)


def _temperature_rows() -> pd.DataFrame:
    dates = pd.to_datetime(
        ["2019-12-15", "2020-01-15", "2020-06-15", "2020-09-15"]
    )
    data = pd.DataFrame({"date": dates})
    data["year"] = data["date"].dt.year
    data["decade"] = (data["year"] // 10) * 10
    return data


def test_temperature_season_filter_selects_expected_months() -> None:
    summer = filter_temperature_season(_temperature_rows(), "Summer")

    assert summer["date"].dt.month.tolist() == [6]


def test_winter_assigns_december_to_following_year() -> None:
    winter = filter_temperature_season(_temperature_rows(), "Winter")

    assert winter["date"].dt.month.tolist() == [12, 1]
    assert winter["year"].tolist() == [2020, 2020]
    assert winter["decade"].tolist() == [2020, 2020]


def test_yearly_seasonal_aggregation_accepts_60_days() -> None:
    dates = pd.date_range("2020-06-01", periods=60)
    data = pd.DataFrame(
        {
            "date": dates,
            "year": 2020,
            "decade": 2020,
            "tmax_f": 80.0,
            "tmin_f": 60.0,
        }
    )

    aggregated, _, _ = build_temperature_aggregation(
        data,
        "Year",
        minimum_days_per_year=60,
    )

    assert len(aggregated) == 1
    assert aggregated.iloc[0]["days_with_tmax"] == 60
