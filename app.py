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

data = pd.read_csv("data/processed/USW00023234_daily_temperature.csv")

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