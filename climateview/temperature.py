import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from climateview.charts import add_trendline


def build_temperature_aggregation(data, aggregation):
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

        month_dates = pd.to_datetime(grouped["month"])

        grouped["year"] = month_dates.dt.year
        grouped["trend_year"] = month_dates.dt.year + (month_dates.dt.month - 1) / 12

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
            (grouped["days_with_tmax"] >= 300)
            & (grouped["days_with_tmin"] >= 300)
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

    return grouped, x_col, x_title


def render_temperature_tab(temperature_data):
    st.markdown("### Temperature Trends")

    aggregation = st.radio(
        "Temperature aggregation level",
        ["Month", "Year", "Decade"],
        index=1,
        horizontal=True,
    )

    grouped, x_col, x_title = build_temperature_aggregation(
        temperature_data,
        aggregation,
    )

    year_range = st.slider(
        "Select temperature year range",
        min_value=int(grouped["year"].min()),
        max_value=int(grouped["year"].max()),
        value=(int(grouped["year"].min()), int(grouped["year"].max())),
    )

    filtered = grouped[
        (grouped["year"] >= year_range[0])
        & (grouped["year"] <= year_range[1])
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=filtered[x_col],
            y=filtered["avg_tmax_f"],
            mode="lines+markers",
            name="Average max temperature",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=filtered[x_col],
            y=filtered["avg_tmin_f"],
            mode="lines+markers",
            name="Average min temperature",
        )
    )

    max_slope_per_year = add_trendline(
        fig,
        filtered,
        x_col,
        "trend_year",
        "avg_tmax_f",
        "Max temperature trend",
        "°F",
    )

    min_slope_per_year = add_trendline(
        fig,
        filtered,
        x_col,
        "trend_year",
        "avg_tmin_f",
        "Min temperature trend",
        "°F",
    )

    fig.update_layout(
        title=f"Average {aggregation} Max and Min Temperatures at SFO",
        xaxis_title=x_title,
        yaxis_title="Temperature (°F)",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Temperature Trend Summary")

    if max_slope_per_year is not None and min_slope_per_year is not None:
        st.write(
            f"Maximum temperature linear trend: {max_slope_per_year:+.3f}°F per year"
        )
        st.write(
            f"Minimum temperature linear trend: {min_slope_per_year:+.3f}°F per year"
        )
    else:
        st.write("Not enough data points to calculate a temperature trend.")

    st.markdown("### Temperature Data")
    st.dataframe(filtered, use_container_width=True)