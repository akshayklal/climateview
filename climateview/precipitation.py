import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from climateview.ai_insights import render_ai_insights
from climateview.charts import (
    HIGHLIGHT_COLOR,
    apply_standard_layout,
    calculate_linear_trend,
    select_referenced_periods,
)
from climateview.presentation import (
    RAINFALL,
    format_decadal_trend,
    render_location_summary,
)
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)

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

PRECIPITATION_TABLES = {
    "Month": {
        "period_column": "month",
        "period_label": "Month",
        "precipitation_label": "Total precipitation (in)",
        "rainy_days_label": "Rainy days",
        "coverage_column": "days_with_data",
        "coverage_label": "Days with observations",
    },
    "Calendar Year": {
        "period_column": "year",
        "period_label": "Year",
        "precipitation_label": "Total precipitation (in)",
        "rainy_days_label": "Rainy days",
        "coverage_column": "days_with_data",
        "coverage_label": "Days with observations",
    },
    "Rain Year": {
        "period_column": "rain_year",
        "period_label": "Rain year",
        "precipitation_label": "Total precipitation (in)",
        "rainy_days_label": "Rainy days",
        "coverage_column": "days_with_data",
        "coverage_label": "Days with observations",
    },
    "Decade": {
        "period_column": "decade",
        "period_label": "Decade",
        "precipitation_label": "Average annual precipitation (in)",
        "rainy_days_label": "Average rainy days",
        "coverage_column": "years_in_decade",
        "coverage_label": "Years included",
    },
}


def _aggregate_precipitation(data, period_column):
    """Aggregate daily precipitation records by one period column."""
    return (
        data.groupby(period_column)
        .agg(
            total_prcp_in=("prcp_in", "sum"),
            days_with_data=("prcp_in", "count"),
            rainy_days=("prcp_in", lambda values: (values > 0).sum()),
        )
        .reset_index()
    )


def _complete_annual_precipitation(data):
    annual = _aggregate_precipitation(data, "year")
    return annual[annual["days_with_data"] >= 300].copy()



def build_precipitation_aggregation(
    data,
    precipitation_view,
    rain_year_start_month,
):
    if precipitation_view == "Month":
        grouped = _aggregate_precipitation(data, "month")

        grouped["month"] = pd.to_datetime(grouped["month"])
        grouped["year"] = grouped["month"].dt.year
        grouped["trend_year"] = (
            grouped["month"].dt.year
            + (grouped["month"].dt.month - 1) / 12
        )

        x_col = "month"
        x_title = "Month"

    elif precipitation_view == "Calendar Year":
        grouped = _complete_annual_precipitation(data)

        grouped["trend_year"] = grouped["year"]

        x_col = "year"
        x_title = "Year"

    elif precipitation_view == "Rain Year":
        rain_data = data.copy()

        rain_data["rain_year"] = np.where(
            rain_data["month_number"] >= rain_year_start_month,
            rain_data["year"] + 1,
            rain_data["year"],
        )

        grouped = _aggregate_precipitation(rain_data, "rain_year")

        grouped = grouped[
            grouped["days_with_data"] >= 300
        ].copy()

        grouped["year"] = grouped["rain_year"]
        grouped["trend_year"] = grouped["rain_year"]

        x_col = "rain_year"
        x_title = "Rain Year"

    else:
        annual = _complete_annual_precipitation(data)

        annual["decade"] = (
            annual["year"] // 10
        ) * 10

        grouped = (
            annual.groupby("decade")
            .agg(
                total_prcp_in=("total_prcp_in", "mean"),
                rainy_days=("rainy_days", "mean"),
                years_in_decade=("year", "count"),
            )
            .reset_index()
        )

        grouped["year"] = grouped["decade"]
        grouped["trend_year"] = grouped["decade"]

        x_col = "decade"
        x_title = "Decade"

    return grouped, x_col, x_title


def build_precipitation_figure(aggregated_data, x_col, x_title):
    precipitation_trend, trend_values = calculate_linear_trend(
        aggregated_data["trend_year"],
        aggregated_data["total_prcp_in"],
    )

    figure = go.Figure()

    figure.add_trace(
        go.Bar(
            x=aggregated_data[x_col],
            y=aggregated_data["total_prcp_in"],
            name="Precipitation",
            marker_color=RAINFALL["light"],
            hovertemplate=(
                "%{x}<br>"
                "Precipitation: %{y:.2f} in"
                "<extra></extra>"
            ),
        )
    )

    if trend_values is not None:
        figure.add_trace(
            go.Scatter(
                x=aggregated_data[x_col],
                y=trend_values,
                mode="lines",
                name=(
                    "Trend"
                ),
                line={"color": RAINFALL["dark"], "dash": "dash"},
                hoverinfo="skip",
            )
        )

    apply_standard_layout(
        figure,
        x_title=x_title,
        height=520,
        margins={
            "l": 40,
            "r": 30,
            "t": 12,
            "b": 100,
        },
        yaxis_title="Precipitation (inches)",
        bargap=0.15,
    )

    figure.update_yaxes(
        showgrid=True,
        zeroline=False,
    )

    return figure, precipitation_trend


def calculate_annual_statistics(filtered_data):
    annual_data = _complete_annual_precipitation(filtered_data)

    if annual_data.empty:
        return None, None, None

    average_annual_precipitation = float(
        annual_data["total_prcp_in"].mean()
    )

    wettest_row = annual_data.loc[
        annual_data["total_prcp_in"].idxmax()
    ]

    driest_row = annual_data.loc[
        annual_data["total_prcp_in"].idxmin()
    ]

    wettest_year = {
        "year": int(wettest_row["year"]),
        "precipitation": float(
            wettest_row["total_prcp_in"]
        ),
    }

    driest_year = {
        "year": int(driest_row["year"]),
        "precipitation": float(
            driest_row["total_prcp_in"]
        ),
    }

    return (
        average_annual_precipitation,
        wettest_year,
        driest_year,
    )


def render_precipitation_table(
    aggregated_data,
    precipitation_view,
):
    config = PRECIPITATION_TABLES[precipitation_view]
    display_columns = [
        config["period_label"],
        config["precipitation_label"],
        config["rainy_days_label"],
        config["coverage_label"],
    ]
    display_data = aggregated_data.rename(
        columns={
            config["period_column"]: config["period_label"],
            "total_prcp_in": config["precipitation_label"],
            "rainy_days": config["rainy_days_label"],
            config["coverage_column"]: config["coverage_label"],
        }
    )[display_columns].copy()

    if precipitation_view == "Month":
        display_data[config["period_label"]] = display_data[
            config["period_label"]
        ].dt.strftime("%B %Y")

    display_data[config["precipitation_label"]] = display_data[
        config["precipitation_label"]
    ].round(2)

    if precipitation_view == "Decade":
        display_data[config["rainy_days_label"]] = display_data[
            config["rainy_days_label"]
        ].round(1)

    st.dataframe(display_data, width="stretch", hide_index=True)


def render_precipitation_tab(data, station_name, summary_placeholder=None):
    if data is None or data.empty:
        st.warning("No precipitation data is available for this station.")
        return

    required_columns = {
        "year",
        "month",
        "month_number",
        "prcp_in",
    }

    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        st.error(
            "Precipitation data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    complete_years = _complete_annual_precipitation(data)["year"]

    if complete_years.empty:
        min_year = int(data["year"].min())
        max_year = int(data["year"].max())
    else:
        min_year = int(complete_years.min())
        max_year = int(complete_years.max())

    view_col, rain_year_col, range_col = st.columns(
        [2.4, 1.4, 3.2], vertical_alignment="bottom"
    )

    with view_col:
        precipitation_view = st.segmented_control(
            "Aggregation",
            options=[
                "Month",
                "Calendar Year",
                "Rain Year",
                "Decade",
            ],
            default="Calendar Year",
            key="precipitation_aggregation",
        )

    if precipitation_view is None:
        precipitation_view = "Calendar Year"

    with rain_year_col:
        rain_year_start_name = st.selectbox(
            "Rain year starts",
            options=list(MONTH_NAME_TO_NUMBER.keys()),
            index=9,
            disabled=precipitation_view != "Rain Year",
            key="rain_year_start_month",
        )

    rain_year_start_month = MONTH_NAME_TO_NUMBER[
        rain_year_start_name
    ]

    with range_col:
        selected_years = st.slider(
            "Date Range", min_year, max_year, (min_year, max_year),
            key="precipitation_year_range",
        )

    filtered_data = data[data["year"].between(*selected_years)].copy()

    aggregated_data, x_col, x_title = build_precipitation_aggregation(
        filtered_data, precipitation_view, rain_year_start_month
    )

    if aggregated_data.empty:
        st.info(
            "No sufficiently complete precipitation records "
            "are available for the selected period."
        )
        return

    figure, precipitation_trend = build_precipitation_figure(
        aggregated_data, x_col, x_title
    )

    if summary_placeholder is not None:
        if precipitation_trend is None:
            summary = "No clear long-term rainfall trend is available."
        else:
            summary = format_decadal_trend(
                "Rainfall",
                precipitation_trend,
                selected_years[0],
                " inches",
                ("is increasing", "is decreasing"),
            )
        render_location_summary(summary_placeholder, summary)

    (
        average_annual_precipitation,
        wettest_year,
        driest_year,
    ) = calculate_annual_statistics(filtered_data)

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "Precipitation trend",
        (
            f"{precipitation_trend:+.3f} in/year"
            if precipitation_trend is not None
            else "Insufficient data"
        ),
    )

    metric2.metric(
        "Annual average",
        (
            f"{average_annual_precipitation:.1f} in"
            if average_annual_precipitation is not None
            else "Insufficient data"
        ),
    )

    metric3.metric(
        "Wettest year",
        (
            str(wettest_year["year"])
            if wettest_year is not None
            else "Insufficient data"
        ),
        (
            f"{wettest_year['precipitation']:.1f} in"
            if wettest_year is not None
            else None
        ),
    )

    metric4.metric(
        "Driest year",
        (
            str(driest_year["year"])
            if driest_year is not None
            else "Insufficient data"
        ),
        (
            f"{driest_year['precipitation']:.1f} in"
            if driest_year is not None
            else None
        ),
    )

    analysis = analyze_series(
        dataframe=aggregated_data,
        context=AnalysisContext(
            location=station_name,
            metric="precipitation",
            unit="inches",
            aggregation=precipitation_view.lower().replace(" ", "_"),
            start_period=selected_years[0],
            end_period=selected_years[1],
        ),
        schema=DataSchema(
            period_column=x_col,
            value_column="total_prcp_in",
        ),
    )

    insight_signature = (
        station_name,
        precipitation_view,
        selected_years[0],
        selected_years[1],
        rain_year_start_month,
    )

    def render_precipitation_chart(referenced_periods, _referenced_series):
        highlighted = select_referenced_periods(
            aggregated_data,
            x_col,
            referenced_periods,
        )
        if not highlighted.empty:
            highlighted_indices = set(highlighted.index)
            figure.data[0].marker.color = [
                HIGHLIGHT_COLOR
                if index in highlighted_indices
                else RAINFALL["light"]
                for index in aggregated_data.index
            ]
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )

    render_ai_insights(
        analysis=analysis,
        state_prefix="precipitation",
        signature=insight_signature,
        render_below=render_precipitation_chart,
        question_label=(
            "Ask a question about the selected precipitation data"
        ),
        question_placeholder=(
            "Ask about trends, anomalies, or specific years..."
        ),
        summary_spinner_text=(
            "Analyzing the selected precipitation data..."
        ),
    )

    with st.expander("View underlying precipitation data", expanded=False):
        render_precipitation_table(aggregated_data, precipitation_view)
