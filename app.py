import pandas as pd
import pydeck as pdk
import streamlit as st

from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab


# Page configuration
st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)


# Weather stations
STATIONS = {
    "USW00023234": {
        "name": "San Francisco / SFO, CA",
        "lat": 37.619,
        "lon": -122.375,
        "active": True,
    },
    "USW00094728": {
        "name": "New York Central Park, NY",
        "lat": 40.782,
        "lon": -73.965,
        "active": True,
    },
    "USW00094846": {
        "name": "Chicago O'Hare, IL",
        "lat": 41.974,
        "lon": -87.903,
        "active": True,
    },
    "USW00024233": {
        "name": "Seattle-Tacoma, WA",
        "lat": 47.444,
        "lon": -122.314,
        "active": True,
    },
    "USW00023174": {
        "name": "Los Angeles Downtown / USC, CA",
        "lat": 34.023,
        "lon": -118.285,
        "active": True,
    },
    "USW00023183": {
        "name": "Phoenix Sky Harbor, AZ",
        "lat": 33.428,
        "lon": -111.998,
        "active": True,
    },
    "USW00023062": {
        "name": "Denver, CO",
        "lat": 39.833,
        "lon": -104.658,
        "active": True,
    },
    "USW00012960": {
        "name": "Houston Intercontinental, TX",
        "lat": 29.980,
        "lon": -95.340,
        "active": True,
    },
}


# Build station dataframe for the map
df_stations = pd.DataFrame(
    [
        {
            "station_id": station_id,
            "name": station["name"],
            "lat": station["lat"],
            "lon": station["lon"],
        }
        for station_id, station in STATIONS.items()
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
    station_id = st.session_state.selected_station
    station = STATIONS[station_id]
    station_name = station["name"]

    # Navigation
    if st.button("← All stations"):
        st.session_state.selected_station = None
        st.rerun()

    # Station header
    st.title(station_name)
    st.caption(
        f"NOAA station {station_id} · "
        f"{station['lat']:.3f}, {station['lon']:.3f}"
    )

    # Load station-specific data
    temperature_data = load_temperature_data(
        station_id=station_id
    )

    precipitation_data = load_precipitation_data(
        station_id=station_id
    )

    # Detail tabs
    temperature_tab, precipitation_tab = st.tabs(
        ["Temperature", "Precipitation"]
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
            "Historical temperature and precipitation records "
            "from NOAA weather stations."
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
            map_style="mapbox://styles/mapbox/light-v11",
            tooltip={
                "html": (
                    "<b>{name}</b><br/>"
                    "<span style='color:#666;'>"
                    "Temperature and precipitation trends"
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
        use_container_width=True,
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
                clicked_row["station_id"]
            )

            st.rerun()

    # Data source note
    st.caption(
        "Data source: NOAA Global Historical Climatology Network. "
        "Station records may cover different date ranges."
    )