import pandas as pd
import pytest

from climateview.seasons import get_station_seasons, normalize_season
from climateview.stations import STATIONS
from climateview.temperature import filter_temperature_season


def test_existing_stations_keep_original_seasons():
    expected = {
        "Winter": (12, 1, 2), "Spring": (3, 4, 5),
        "Summer": (6, 7, 8), "Fall": (9, 10, 11),
    }
    for station in STATIONS.values():
        assert get_station_seasons(station) == expected


def test_southern_seasons_and_cross_year_grouping():
    seasons = get_station_seasons({"season_profile": "southern"})
    dates = pd.to_datetime(["2019-12-15", "2020-01-15", "2020-06-15"])
    data = pd.DataFrame({"date": dates, "year": dates.year, "decade": 2010})
    summer = filter_temperature_season(data, "Summer", season_months=seasons)
    assert summer["year"].tolist() == [2020, 2020]
    assert summer["decade"].tolist() == [2020, 2020]
    winter = filter_temperature_season(data, "Winter", season_months=seasons)
    assert winter["date"].dt.month.tolist() == [6]
    assert winter["year"].tolist() == [2020]


def test_custom_wet_season_rolls_all_previous_year_months():
    seasons = get_station_seasons({"season_months": {"Wet": [11, 12, 1, 2, 3]}})
    dates = pd.to_datetime(["2019-11-15", "2019-12-15", "2020-01-15", "2020-05-15"])
    data = pd.DataFrame({"date": dates, "year": dates.year})
    wet = filter_temperature_season(data, "Wet", season_months=seasons)
    assert wet["year"].tolist() == [2020, 2020, 2020]
    assert normalize_season("wet", seasons) == "Wet"
    assert normalize_season("Summer", seasons) == "All year"


def test_unconfigured_and_disabled_seasons_do_not_assume_hemisphere():
    assert get_station_seasons({"latitude": -33}) == {}
    assert get_station_seasons({"season_profile": "none"}) == {}
    assert normalize_season("Winter", {}) == "All year"


@pytest.mark.parametrize("station", [
    {"season_profile": "typo"},
    {"season_months": {"Wet": [13]}},
    {"season_months": {"Wet": [1, 1]}},
    {"season_months": {"Wet": [1, 3]}},
    {"season_months": {"Wet": [1, 2], "Dry": [2, 3]}},
    {"season_months": {"All year": [1, 2, 3]}},
])
def test_invalid_season_config_is_rejected(station):
    with pytest.raises(ValueError):
        get_station_seasons(station)


def test_season_selector_hides_and_resets_when_switching_profiles():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from unittest.mock import patch
from climateview.temperature import render_temperature_tab
from climateview.seasons import get_station_seasons

profile = st.selectbox("Profile", ["northern", "none", "southern"])
dates = pd.date_range("2000-01-01", "2002-12-31")
data = pd.DataFrame({
    "date": dates, "year": dates.year,
    "month": dates.to_period("M").astype(str), "decade": 2000,
    "tmax_f": 70., "tmin_f": 50.,
})
with patch("climateview.temperature.render_ai_insights"):
    render_temperature_tab(
        data, "Test", season_months=get_station_seasons({"season_profile": profile})
    )
''').run()
    assert not app.exception
    selectors = {control.key: control for control in app.get("button_group")}
    assert selectors["temperature_season"].options == [
        "All year", "Winter", "Spring", "Summer", "Fall"
    ]
    assert app.session_state["temperature_season"] == "All year"
    assert app.session_state["temperature_aggregation"] == "Year"

    app.session_state["temperature_season"] = "Summer"
    app.selectbox[0].select("none").run()
    assert not app.exception
    assert "temperature_season" not in {c.key for c in app.get("button_group")}
    assert app.session_state["temperature_season"] == "All year"

    app.selectbox[0].select("southern").run()
    assert not app.exception
    assert "temperature_season" in {c.key for c in app.get("button_group")}
    assert app.session_state["temperature_season"] == "All year"
