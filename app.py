import pandas as pd
import pydeck as pdk
import streamlit as st

from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab
from climateview.air_quality import render_air_quality_tab
from climateview.data_loader import load_air_quality_data
from climateview.stations import STATIONS


# Page configuration
st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)

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

# Build station dataframe for the map
df_stations = pd.DataFrame(
    [
        {
            "station_key": station_key,
            "name": station["name"],
            "lat": station["latitude"],
            "lon": station["longitude"],
        }
        for station_key, station in STATIONS.items()
        if station["active"]
    ]
)

# Track selected station across Streamlit reruns
if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# Clear invalid station IDs (e.g., after station list changes)
if (
    st.session_state.selected_station is not None
    and st.session_state.selected_station not in STATIONS
):
    st.session_state.selected_station = None

# SCREEN 2: Selected station detail page
if st.session_state.selected_station in STATIONS:
    station_key = st.session_state.selected_station
    station = STATIONS[station_key]

    station_name = station["name"]
    noaa_station_id = station["noaa_station_id"]

    # Compact navigation and station header
    back_col, title_col = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with back_col:
        if st.button("← All stations"):
            st.session_state.selected_station = None
            st.rerun()

    with title_col:
        st.markdown(f"## {station_name}")
        st.caption(
            f"NOAA station {noaa_station_id} · "
            f"{station['latitude']:.3f}, {station['longitude']:.3f}"
        )

    temperature_data = load_temperature_data(
        station_id=noaa_station_id
    )

    precipitation_data = load_precipitation_data(
        station_id=noaa_station_id
    )

    aqs_site_id = station.get("aqs_site_id")

    if aqs_site_id:
        pm25_data = load_air_quality_data(
            aqs_site_id=aqs_site_id,
            pollutant="pm25",
        )

        ozone_data = load_air_quality_data(
            aqs_site_id=aqs_site_id,
            pollutant="ozone",
        )
    else:
        pm25_data = {
            "metadata": {},
            "data": pd.DataFrame(),
        }

        ozone_data = {
            "metadata": {},
            "data": pd.DataFrame(),
        }

    # Detail tabs
    temperature_tab, precipitation_tab, air_quality_tab = st.tabs(
        ["Temperature", "Precipitation", "Air Quality"]
    )

    with temperature_tab:
        render_temperature_tab(
            temperature_data,
            station_name=station_name,
        )

    with precipitation_tab:
        render_precipitation_tab(
            precipitation_data,
            station_name=station_name,
        )

    with air_quality_tab:
        render_air_quality_tab(
            pm25_data=pm25_data,
            ozone_data=ozone_data,
            station_name=station_name,
        )


# SCREEN 1: Landing page and station map
else:
    # Hero section
    title_col, metric_col = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )

    with title_col:
        st.title("ClimateView")
        st.subheader(
            "Explore long-term climate trends across the United States"
        )
        st.caption(
            "Historical temperature, precipitation, and air quality records "
            "from NOAA and EPA monitoring stations."
        )

    with metric_col:
        st.metric(
            "Stations",
            len(df_stations),
        )

    st.divider()

    # Map heading
    heading_col, instruction_col = st.columns(
        [2, 3],
        vertical_alignment="center",
    )

    with heading_col:
        st.subheader("Select a weather station")

    with instruction_col:
        st.caption(
            "Click an orange marker to explore historical climate trends."
        )

    # Station marker layer
    station_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_stations,
        get_position="[lon, lat]",
        get_fill_color="[240, 90, 45, 210]",
        get_line_color="[255, 255, 255, 230]",
        get_radius=55000,
        radius_min_pixels=8,
        radius_max_pixels=24,
        line_width_min_pixels=2,
        stroked=True,
        filled=True,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 190, 90, 255],
        id="weather-stations",
    )

    # Initial map position
    view_state = pdk.ViewState(
        latitude=39.8283,
        longitude=-98.5795,
        zoom=3.65,
        pitch=0,
    )

    # Render interactive map
    map_deck = st.pydeck_chart(
        pdk.Deck(
            layers=[station_layer],
            initial_view_state=view_state,
            map_provider="carto",
            map_style="road",
            tooltip={
                "html": (
                    "<b>{name}</b><br/>"
                    "<span style='color:#666;'>"
                    "Temperature, precipitation, and air quality trends"
                    "</span><br/>"
                    "<span style='color:#999;'>Click to open</span>"
                ),
                "style": {
                    "backgroundColor": "white",
                    "color": "#222",
                    "fontSize": "14px",
                    "padding": "10px",
                },
            },
        ),
        on_select="rerun",
        selection_mode="single-object",
        width="stretch",
    )

    # Handle map selection
    if (
        map_deck
        and "selection" in map_deck
        and map_deck["selection"]
    ):
        selected_indices = (
            map_deck["selection"]
            .get("indices", {})
            .get("weather-stations", [])
        )

        if selected_indices:
            clicked_index = selected_indices[0]
            clicked_row = df_stations.iloc[clicked_index]

            st.session_state.selected_station = (
                clicked_row["station_key"]
            )

            st.rerun()

    # Data source note
    st.caption(
        "Data sources: NOAA Global Historical Climatology Network "
        "and U.S. EPA Air Quality System. "
        "Station records may cover different date ranges."
    )