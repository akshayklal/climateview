import pandas as pd
import pydeck as pdk
import streamlit as st

from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab
from climateview.stations import STATIONS

ESRI_TOPO_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
)

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

    # Esri World Topographic basemap
    basemap_layer = pdk.Layer(
        "TileLayer",
        id="esri-world-topographic",
        data=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        min_zoom=0,
        max_zoom=19,
        tile_size=256,
        render_sub_layers={
            "@@type": "BitmapLayer",
            "data": None,
            "image": "@@=data",
            "bounds": "@@=tile.boundingBox",
        },
    )

    # Initial map position
    view_state = pdk.ViewState(
        latitude=39.2,
        longitude=-98.2,
        zoom=3.5,
        pitch=0,
    )

    map_deck = st.pydeck_chart(
        pdk.Deck(
            layers=[
                basemap_layer,
                station_layer,
            ],
            initial_view_state=view_state,
            map_style=None,
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
                clicked_row["station_key"]
            )

            st.rerun()

    # Data source note
    st.caption(
        "Data source: NOAA Global Historical Climatology Network. "
        "Station records may cover different date ranges."
    )