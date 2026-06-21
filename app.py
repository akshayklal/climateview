import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)

st.title("ClimateView")
st.subheader("Local climate trends using NOAA data")

st.write(
    "This is the first local version of the ClimateView app. "
    "For now, it uses sample SFO annual temperature data so we can verify that Streamlit runs correctly."
)

# Temporary sample data. Later this will come from data/processed/sfo_annual_temperature.csv
data = {
    "year": [2019, 2020, 2021, 2022, 2023, 2024],
    "avg_tmax_f": [65.1, 66.0, 65.8, 66.2, 65.7, 66.4],
    "avg_tmin_f": [51.2, 51.5, 51.7, 52.0, 51.8, 52.2],
}

annual = pd.DataFrame(data)

year_range = st.slider(
    "Select year range",
    min_value=int(annual["year"].min()),
    max_value=int(annual["year"].max()),
    value=(int(annual["year"].min()), int(annual["year"].max())),
)

filtered = annual[
    (annual["year"] >= year_range[0]) &
    (annual["year"] <= year_range[1])
]

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=filtered["year"],
        y=filtered["avg_tmax_f"],
        mode="lines+markers",
        name="Average annual max temperature",
    )
)

fig.add_trace(
    go.Scatter(
        x=filtered["year"],
        y=filtered["avg_tmin_f"],
        mode="lines+markers",
        name="Average annual min temperature",
    )
)

fig.update_layout(
    title="Average Annual Max and Min Temperatures at SFO",
    xaxis_title="Year",
    yaxis_title="Temperature (°F)",
    hovermode="x unified",
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("### Data")
st.dataframe(filtered, use_container_width=True)