import streamlit as st

from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab


st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)

st.title("ClimateView")
st.subheader("Local climate trends using NOAA data")

st.write(
    "This app visualizes historical temperature and precipitation trends "
    "using NOAA weather-station data."
)

temperature_data = load_temperature_data()
precipitation_data = load_precipitation_data()

temperature_tab, precipitation_tab = st.tabs(
    ["Temperature", "Precipitation"]
)

with temperature_tab:
    render_temperature_tab(temperature_data)

with precipitation_tab:
    render_precipitation_tab(precipitation_data)