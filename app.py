import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

def add_trendline(fig, df, x_col, y_col, name):
    trend_data = df[[x_col, "trend_year", y_col]].dropna()

    if len(trend_data) < 2:
        return None

    x = trend_data["trend_year"].values
    y = trend_data[y_col].values

    slope_per_year, intercept = np.polyfit(x, y, 1)
    trend_y = slope_per_year * x + intercept

    fig.add_trace(
        go.Scatter(
            x=trend_data[x_col],
            y=trend_y,
            mode="lines",
            name=f"{name} ({slope_per_year:+.3f}°F/year)",
            line=dict(dash="dash"),
        )
    )

    return slope_per_year

st.set_page_config(
    page_title="ClimateView",
    page_icon="🌎",
    layout="wide",
)

st.title("ClimateView")
st.subheader("Local climate trends using NOAA data")

st.write(
    "This app visualizes historical average annual maximum and minimum "
    "temperatures at San Francisco International Airport using NOAA data."
)

data = pd.read_csv("data/processed/USW00023234_daily_temperature.csv")

data["date"] = pd.to_datetime(data["date"])
data["year"] = data["date"].dt.year
data["month"] = data["date"].dt.to_period("M").astype(str)
data["decade"] = (data["year"] // 10) * 10

aggregation = st.radio(
    "Aggregation level",
    ["Month", "Year", "Decade"],
    index=1,
    horizontal=True,
)

if aggregation == "Month":
    grouped = (
        data.groupby("month")
        .agg(
            avg_tmax_f=("tmax_f", "mean"),
            avg_tmin_f=("tmin_f", "mean"),
            days_with_tmax=("tmax_f", "count"),
            days_with_tmin=("tmin_f", "count"),
        )
        .reset_index()
    )

    grouped["year"] = pd.to_datetime(grouped["month"]).dt.year
    grouped["trend_year"] = pd.to_datetime(grouped["month"]).dt.year + (
            pd.to_datetime(grouped["month"]).dt.month - 1
    ) / 12
    x_col = "month"
    x_title = "Month"

elif aggregation == "Year":
    grouped = (
        data.groupby("year")
        .agg(
            avg_tmax_f=("tmax_f", "mean"),
            avg_tmin_f=("tmin_f", "mean"),
            days_with_tmax=("tmax_f", "count"),
            days_with_tmin=("tmin_f", "count"),
        )
        .reset_index()
    )

    grouped = grouped[
        (grouped["days_with_tmax"] >= 300) &
        (grouped["days_with_tmin"] >= 300)
    ]

    grouped["trend_year"] = grouped["year"]

    x_col = "year"
    x_title = "Year"

else:
    grouped = (
        data.groupby("decade")
        .agg(
            avg_tmax_f=("tmax_f", "mean"),
            avg_tmin_f=("tmin_f", "mean"),
            days_with_tmax=("tmax_f", "count"),
            days_with_tmin=("tmin_f", "count"),
        )
        .reset_index()
    )

    grouped["year"] = grouped["decade"]
    grouped["trend_year"] = grouped["decade"]
    x_col = "decade"
    x_title = "Decade"

year_range = st.slider(
    "Select year range",
    min_value=int(grouped["year"].min()),
    max_value=int(grouped["year"].max()),
    value=(int(grouped["year"].min()), int(grouped["year"].max())),
)

filtered = grouped[
    (grouped["year"] >= year_range[0]) &
    (grouped["year"] <= year_range[1])
]

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=filtered[x_col],
        y=filtered["avg_tmax_f"],
        mode="lines+markers",
        name="Average annual max temperature",
    )
)

fig.add_trace(
    go.Scatter(
        x=filtered[x_col],
        y=filtered["avg_tmin_f"],
        mode="lines+markers",
        name="Average annual min temperature",
    )
)

max_slope_per_year = add_trendline(
    fig,
    filtered,
    x_col,
    "avg_tmax_f",
    "Max temperature trend",
)

min_slope_per_year = add_trendline(
    fig,
    filtered,
    x_col,
    "avg_tmin_f",
    "Min temperature trend",
)

fig.update_layout(
    title="Average Annual Max and Min Temperatures at SFO",
    xaxis_title=x_title,
    yaxis_title="Temperature (°F)",
    hovermode="x unified",
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("### Trend Summary")

if max_slope_per_year is not None and min_slope_per_year is not None:
    st.write(
        f"Maximum temperature linear trend: {max_slope_per_year:+.3f}°F per year"
    )
    st.write(
        f"Minimum temperature linear trend: {min_slope_per_year:+.3f}°F per year"
    )
else:
    st.write("Not enough data points to calculate a linear trend.")

st.markdown("### Data")
st.dataframe(filtered, use_container_width=True)