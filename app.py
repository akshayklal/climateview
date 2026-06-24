import streamlit as st
import pydeck as pdk
import pandas as pd
from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab

# 1. Page Configuration
st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)

# 2. Define Weather Station Mapping
# Keeping only SFO active to fulfill Step 1. Uncomment others for Step 2.
STATIONS = {
    "USW00023234": {"name": "San Francisco / SFO, CA", "lat": 37.619, "lon": -122.375, "active": True},
    "USW00094728": {"name": "New York Central Park, NY", "lat": 40.782, "lon": -73.965, "active": True},
    "USW00094846": {"name": "Chicago O'Hare, IL", "lat": 41.974, "lon": -87.903, "active": True},
    "USW00024233": {"name": "Seattle-Tacoma, WA", "lat": 47.444, "lon": -122.314, "active": True},
    "USW00023174": {"name": "Los Angeles Downtown / USC, CA", "lat": 34.023, "lon": -118.285, "active": True},
    "USW00023183": {"name": "Phoenix Sky Harbor, AZ", "lat": 33.428, "lon": -111.998, "active": True},
    "USW00023062": {"name": "Denver, CO", "lat": 39.833, "lon": -104.658, "active": True},
    "USW00012960": {"name": "Houston Intercontinental, TX", "lat": 29.980, "lon": -95.340, "active": True}
}

# Convert station dictionary into a Pandas DataFrame
df_stations = pd.DataFrame([
    {"station_id": k, "name": v["name"], "lat": v["lat"], "lon": v["lon"]}
    for k, v in STATIONS.items() if v["active"]
])

# 3. Track Selected Station across reruns
if "selected_station" not in st.session_state:
    st.session_state.selected_station = None

# --- ROUTING LOGIC ---

# SCREEN 2: Station Selected -> Show Detailed Climate Data Tabs
if st.session_state.selected_station:
    station_id = st.session_state.selected_station
    station_name = STATIONS[station_id]["name"]

    # Navigation header
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅ Back to Map"):
            st.session_state.selected_station = None
            st.rerun()
    with col2:
        st.title("ClimateView")
        st.subheader(f"Historical Trends for {station_name}")

    # Pass the selected station ID down cleanly
    temperature_data = load_temperature_data(station_id=station_id)
    precipitation_data = load_precipitation_data(station_id=station_id)

    # Render original tabs layout
    temperature_tab, precipitation_tab = st.tabs(["Temperature", "Precipitation"])

    with temperature_tab:
        render_temperature_tab(temperature_data)

    with precipitation_tab:
        render_precipitation_tab(precipitation_data)


# SCREEN 1: Map View -> Landing Selection Interface
else:
    st.title("ClimateView")
    st.subheader("Local climate trends using NOAA data")
    st.write(
        "This app visualizes historical temperature and precipitation trends "
        "using NOAA weather-station data. **Click the highlighted station marker on the map below** to begin."
    )

    # Configure Pydeck Visual Scatter Marker Layer
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_stations,
        get_position="[lon, lat]",
        get_color="[230, 65, 0, 200]",  # Bright Orange-Red with transparency
        get_radius=90000,  # Radius bounds in meters (makes it easily clickable)
        pickable=True,  # Allows click interaction
        auto_highlight=True,  # Changes color on hover
        id="weather-stations"  # Unique identifier matching selection routing
    )

    # Center perspective view focused broadly over North America
    view_state = pdk.ViewState(
        latitude=39.8283,
        longitude=-98.5795,
        zoom=3.8,
        pitch=0
    )

    # Render interactive map component capturing selection triggers
    map_deck = st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "{name}\n👉 Click to view historical charts"},
        ),
        on_select="rerun",
        selection_mode="single-object"
    )

    # Evaluate Selection State Shifts
    if map_deck and "selection" in map_deck and map_deck["selection"]:
        # Extract indices returned natively by Streamlit selection events
        indices = map_deck["selection"].get("indices", {}).get("weather-stations", [])

        if indices:
            # Map the clicked index position back to the row in df_stations
            clicked_index = indices[0]
            clicked_row = df_stations.iloc[clicked_index]
            st.session_state.selected_station = clicked_row["station_id"]
            st.rerun()

# import streamlit as st
#
# from climateview.data_loader import load_precipitation_data
# from climateview.data_loader import load_temperature_data
# from climateview.precipitation import render_precipitation_tab
# from climateview.temperature import render_temperature_tab
#
#
# st.set_page_config(
#     page_title="ClimateView",
#     page_icon="🌎",
#     layout="wide",
# )
#
# st.title("ClimateView")
# st.subheader("Local climate trends using NOAA data")
#
# st.write(
#     "This app visualizes historical temperature and precipitation trends "
#     "using NOAA weather-station data."
# )
#
# temperature_data = load_temperature_data()
# precipitation_data = load_precipitation_data()
#
# temperature_tab, precipitation_tab = st.tabs(
#     ["Temperature", "Precipitation"]
# )
#
# with temperature_tab:
#     render_temperature_tab(temperature_data)
#
# with precipitation_tab:
#     render_precipitation_tab(precipitation_data)