import numpy as np
import plotly.graph_objects as go
import streamlit as st

from climateview.charts import add_trendline


MONTH_NAME_TO_NUMBER = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


def build_precipitation_aggregation(data, precip_view, rain_year_start_month):
    if precip_view == "Month":
        grouped = (
            data.groupby("month")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_prcp=("prcp_in", "count"),
            )
            .reset_index()
        )

        month_dates = grouped["month"].astype("datetime64[ns]")

        grouped["year"] = month_dates.dt.year
        grouped["trend_year"] = month_dates.dt.year + (month_dates.dt.month - 1) / 12

        x_col = "month"
        x_title = "Month"
        chart_title = "Monthly Total Precipitation at SFO"

    elif precip_view == "Calendar Year":
        grouped = (
            data.groupby("year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_prcp=("prcp_in", "count"),
            )
            .reset_index()
        )

        grouped = grouped[grouped["days_with_prcp"] >= 300]
        grouped["trend_year"] = grouped["year"]

        x_col = "year"
        x_title = "Year"
        chart_title = "Calendar-Year Total Precipitation at SFO"

    elif precip_view == "Rain Year":
        data = data.copy()

        data["rain_year"] = np.where(
            data["month_number"] >= rain_year_start_month,
            data["year"] + 1,
            data["year"],
        )

        grouped = (
            data.groupby("rain_year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_prcp=("prcp_in", "count"),
            )
            .reset_index()
        )

        grouped = grouped[grouped["days_with_prcp"] >= 300]

        grouped["year"] = grouped["rain_year"]
        grouped["trend_year"] = grouped["rain_year"]

        x_col = "rain_year"
        x_title = "Rain Year"
        chart_title = "Rain-Year Total Precipitation at SFO"

    else:
        annual = (
            data.groupby("year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_prcp=("prcp_in", "count"),
            )
            .reset_index()
        )

        annual = annual[annual["days_with_prcp"] >= 300]
        annual["decade"] = (annual["year"] // 10) * 10

        grouped = (
            annual.groupby("decade")
            .agg(
                total_prcp_in=("total_prcp_in", "mean"),
                years_in_decade=("year", "count"),
            )
            .reset_index()
        )

        grouped["year"] = grouped["decade"]
        grouped["trend_year"] = grouped["decade"]

        x_col = "decade"
        x_title = "Decade"
        chart_title = "Average Annual Precipitation by Decade at SFO"

    return grouped, x_col, x_title, chart_title


def render_precipitation_tab(precipitation_data):
    st.markdown("### Precipitation Trends")

    precip_view = st.radio(
        "Precipitation view",
        ["Rain Year", "Calendar Year", "Month", "Decade"],
        index=0,
        horizontal=True,
    )

    rain_year_start_month_name = st.selectbox(
        "Rain year starts in",
        list(MONTH_NAME_TO_NUMBER.keys()),
        index=9,
    )

    rain_year_start_month = MONTH_NAME_TO_NUMBER[rain_year_start_month_name]

    grouped, x_col, x_title, chart_title = build_precipitation_aggregation(
        precipitation_data,
        precip_view,
        rain_year_start_month,
    )

    year_range = st.slider(
        "Select precipitation year range",
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
        go.Bar(
            x=filtered[x_col],
            y=filtered["total_prcp_in"],
            name="Total precipitation",
        )
    )

    prcp_slope_per_year = add_trendline(
        fig,
        filtered,
        x_col,
        "trend_year",
        "total_prcp_in",
        "Precipitation trend",
        "inches",
    )

    fig.update_layout(
        title=chart_title,
        xaxis_title=x_title,
        yaxis_title="Precipitation (inches)",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Precipitation Trend Summary")

    if prcp_slope_per_year is not None:
        st.write(
            f"Precipitation linear trend: {prcp_slope_per_year:+.3f} inches per year"
        )
    else:
        st.write("Not enough data points to calculate a precipitation trend.")

    st.markdown("### Precipitation Data")
    st.dataframe(filtered, use_container_width=True)