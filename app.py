import pandas as pd
import streamlit as st

from climateview.air_quality import render_air_quality_tab
from climateview.data_loader import (
    load_air_quality_data,
    load_explorable_patterns,
    load_location_summaries,
    load_precipitation_data,
    load_temperature_data,
)
from climateview.landing_page import render_landing_page
from climateview.precipitation import render_precipitation_tab
from climateview.stations import STATIONS
from climateview.temperature import render_temperature_tab


st.set_page_config(page_title="Climate Patterns", page_icon="🌎", layout="wide")

if "station_navigation_in_progress" not in st.session_state:
    st.session_state.station_navigation_in_progress = False

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1.5rem;
        }

        h1 {
            margin-top: 0;
            margin-bottom: 0.25rem;
        }

        [data-testid="stCaptionContainer"] {
            margin-bottom: 0.25rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

if st.session_state.station_navigation_in_progress:
    st.markdown(
        """
        <style>
            /* Hide the previous page only during map/station navigation. */
            [data-stale="true"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Keep location pages bookmarkable and resilient to browser refreshes.
url_location = st.query_params.get("location")
if url_location in STATIONS:
    st.session_state.selected_station = url_location
else:
    st.session_state.selected_station = None
    if url_location is not None:
        del st.query_params["location"]


def render_station_page(station_key: str) -> None:
    st.session_state.station_navigation_in_progress = False
    station = STATIONS[station_key]
    station_name = station["name"]

    back_column, title_column = st.columns([1, 8], vertical_alignment="center")
    with back_column:
        if st.button("← All locations"):
            st.session_state.selected_station = None
            st.session_state.station_navigation_in_progress = True
            if "location" in st.query_params:
                del st.query_params["location"]
            st.rerun()
    with title_column:
        st.markdown(f"## {station_name}")

    noaa_station_id = station["noaa_station_id"]
    temperature_data = load_temperature_data(noaa_station_id)
    precipitation_data = load_precipitation_data(noaa_station_id)
    aqs_site_id = station.get("aqs_site_id")
    if aqs_site_id:
        pm25_data = load_air_quality_data(aqs_site_id, "pm25")
        ozone_data = load_air_quality_data(aqs_site_id, "ozone")
    else:
        pm25_data = {"metadata": {}, "data": pd.DataFrame()}
        ozone_data = {"metadata": {}, "data": pd.DataFrame()}

    temperature_tab, precipitation_tab, air_quality_tab = st.tabs(
        ["Temperature", "Precipitation", "Air Quality"],
        key="climate_data_tabs",
        on_change="rerun",
    )
    if temperature_tab.open:
        with temperature_tab:
            render_temperature_tab(temperature_data, station_name)
    elif precipitation_tab.open:
        with precipitation_tab:
            render_precipitation_tab(precipitation_data, station_name)
    elif air_quality_tab.open:
        with air_quality_tab:
            render_air_quality_tab(pm25_data, ozone_data, station_name)


selected_station = st.session_state.selected_station
if selected_station in STATIONS:
    render_station_page(selected_station)
else:
    render_landing_page(load_location_summaries(), load_explorable_patterns())
