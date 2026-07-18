import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from climateview.ai_insights import render_ai_insights
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)


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

        grouped["month"] = pd.to_datetime(grouped["month"])
        grouped["year"] = grouped["month"].dt.year
        grouped["trend_year"] = (
            grouped["month"].dt.year
            + (grouped["month"].dt.month - 1) / 12
        )

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

        # Exclude substantially incomplete years.
        grouped = grouped[
            (grouped["days_with_tmax"] >= 300)
            & (grouped["days_with_tmin"] >= 300)
        ].copy()

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


def calculate_linear_trend(data, value_column):
    """
    Return the linear trend in degrees Fahrenheit per year.

    The function returns None when there are fewer than two valid points.
    """
    trend_data = data[
        ["trend_year", value_column]
    ].dropna()

    if len(trend_data) < 2:
        return None, None

    slope, intercept = np.polyfit(
        trend_data["trend_year"],
        trend_data[value_column],
        1,
    )

    trend_values = (
        slope * data["trend_year"] + intercept
    )

    return float(slope), trend_values


def build_temperature_figure(
    aggregated_data,
    x_col,
    x_title,
    station_name,
):
    max_trend, max_trend_values = calculate_linear_trend(
        aggregated_data,
        "avg_tmax_f",
    )

    min_trend, min_trend_values = calculate_linear_trend(
        aggregated_data,
        "avg_tmin_f",
    )

    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=aggregated_data[x_col],
            y=aggregated_data["avg_tmax_f"],
            mode="lines+markers",
            name="Average maximum",
            hovertemplate=(
                "%{x}<br>"
                "Average maximum: %{y:.1f} °F"
                "<extra></extra>"
            ),
        )
    )

    figure.add_trace(
        go.Scatter(
            x=aggregated_data[x_col],
            y=aggregated_data["avg_tmin_f"],
            mode="lines+markers",
            name="Average minimum",
            hovertemplate=(
                "%{x}<br>"
                "Average minimum: %{y:.1f} °F"
                "<extra></extra>"
            ),
        )
    )

    if max_trend_values is not None:
        figure.add_trace(
            go.Scatter(
                x=aggregated_data[x_col],
                y=max_trend_values,
                mode="lines",
                name="Maximum trend",
                line={"dash": "dash"},
                hoverinfo="skip",
            )
        )

    if min_trend_values is not None:
        figure.add_trace(
            go.Scatter(
                x=aggregated_data[x_col],
                y=min_trend_values,
                mode="lines",
                name=f"Minimum trend",
                line={"dash": "dash"},
                hoverinfo="skip",
            )
        )

    figure.update_layout(
        xaxis_title=x_title,
        yaxis_title="Temperature (°F)",
        height=520,
        margin={
            "l": 40,
            "r": 30,
            "t": 70,
            "b": 100,
        },
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.20,
            "xanchor": "center",
            "x": 0.5,
        },
    )

    figure.update_xaxes(
        showgrid=False,
    )

    figure.update_yaxes(
        showgrid=True,
        zeroline=False,
    )

    return figure, max_trend, min_trend


def render_temperature_table(aggregated_data, aggregation):
    if aggregation == "Month":
        display_data = aggregated_data.rename(
            columns={
                "month": "Month",
                "avg_tmax_f": "Average maximum (°F)",
                "avg_tmin_f": "Average minimum (°F)",
                "days_with_tmax": "Maximum observations",
                "days_with_tmin": "Minimum observations",
            }
        )

        display_data["Month"] = display_data["Month"].dt.strftime(
            "%B %Y"
        )

        display_columns = [
            "Month",
            "Average maximum (°F)",
            "Average minimum (°F)",
            "Maximum observations",
            "Minimum observations",
        ]

    elif aggregation == "Year":
        display_data = aggregated_data.rename(
            columns={
                "year": "Year",
                "avg_tmax_f": "Average maximum (°F)",
                "avg_tmin_f": "Average minimum (°F)",
                "days_with_tmax": "Maximum observations",
                "days_with_tmin": "Minimum observations",
            }
        )

        display_columns = [
            "Year",
            "Average maximum (°F)",
            "Average minimum (°F)",
            "Maximum observations",
            "Minimum observations",
        ]

    else:
        display_data = aggregated_data.rename(
            columns={
                "decade": "Decade",
                "avg_tmax_f": "Average maximum (°F)",
                "avg_tmin_f": "Average minimum (°F)",
                "days_with_tmax": "Maximum observations",
                "days_with_tmin": "Minimum observations",
            }
        )

        display_columns = [
            "Decade",
            "Average maximum (°F)",
            "Average minimum (°F)",
            "Maximum observations",
            "Minimum observations",
        ]

    display_data = display_data[display_columns].copy()

    display_data["Average maximum (°F)"] = display_data[
        "Average maximum (°F)"
    ].round(1)

    display_data["Average minimum (°F)"] = display_data[
        "Average minimum (°F)"
    ].round(1)

    st.dataframe(
        display_data,
        width="stretch",
        hide_index=True,
    )


def render_temperature_tab(data, station_name):
    if data is None or data.empty:
        st.warning(
            "No temperature data is available for this station."
        )
        return

    required_columns = {
        "year",
        "month",
        "decade",
        "tmax_f",
        "tmin_f",
    }

    missing_columns = required_columns.difference(data.columns)

    if missing_columns:
        st.error(
            "Temperature data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    # Use complete annual records to determine the normal selectable period.
    annual_counts = (
        data.groupby("year")
        .agg(
            days_with_tmax=("tmax_f", "count"),
            days_with_tmin=("tmin_f", "count"),
        )
        .reset_index()
    )

    complete_years = annual_counts[
        (annual_counts["days_with_tmax"] >= 300)
        & (annual_counts["days_with_tmin"] >= 300)
    ]["year"]

    if complete_years.empty:
        min_year = int(data["year"].min())
        max_year = int(data["year"].max())
    else:
        min_year = int(complete_years.min())
        max_year = int(complete_years.max())

    aggregation_col, range_col = st.columns(
        [1, 3],
        vertical_alignment="bottom",
    )

    with aggregation_col:
        aggregation = st.segmented_control(
            "Aggregation",
            options=["Month", "Year", "Decade"],
            default="Year",
            key="temperature_aggregation",
        )

    # Fallback for Streamlit versions where no value is initially returned.
    if aggregation is None:
        aggregation = "Year"

    with range_col:
        selected_years = st.slider(
            "Period",
            min_value=min_year,
            max_value=max_year,
            value=(min_year, max_year),
            key="temperature_period",
        )

    filtered_data = data[
        data["year"].between(
            selected_years[0],
            selected_years[1],
        )
    ].copy()

    aggregated_data, x_col, x_title = (
        build_temperature_aggregation(
            filtered_data,
            aggregation,
        )
    )

    if aggregated_data.empty:
        st.info(
            "No sufficiently complete temperature records are "
            "available for the selected period."
        )
        return

    figure, max_trend, min_trend = build_temperature_figure(
        aggregated_data=aggregated_data,
        x_col=x_col,
        x_title=x_title,
        station_name=station_name,
    )

    years_included = filtered_data["year"].nunique()

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "Maximum-temperature trend",
        (
            f"{max_trend:+.3f} °F/year"
            if max_trend is not None
            else "Insufficient data"
        ),
    )

    metric2.metric(
        "Minimum-temperature trend",
        (
            f"{min_trend:+.3f} °F/year"
            if min_trend is not None
            else "Insufficient data"
        ),
    )

    metric3.metric(
        "Selected period",
        f"{selected_years[0]}–{selected_years[1]}",
    )

    metric4.metric(
        "Years included",
        f"{years_included}",
    )

    analysis_data = aggregated_data.copy()
    analysis_data["avg_temperature_f"] = (
        analysis_data["avg_tmax_f"]
        + analysis_data["avg_tmin_f"]
    ) / 2.0

    analysis = analyze_series(
        dataframe=analysis_data,
        context=AnalysisContext(
            location=station_name,
            metric="temperature",
            unit="degrees Fahrenheit",
            aggregation=aggregation.lower(),
            start_period=selected_years[0],
            end_period=selected_years[1],
        ),
        schema=DataSchema(
            period_column=x_col,
            value_column="avg_temperature_f",
        ),
    )

    insight_signature = (
        station_name,
        aggregation,
        selected_years[0],
        selected_years[1],
    )

    def render_temperature_chart():
        st.plotly_chart(
            figure,
            width="stretch",
            config={
                "displayModeBar": False,
                "responsive": True,
            },
        )

    render_ai_insights(
        analysis=analysis,
        state_prefix="temperature",
        signature=insight_signature,
        render_below=render_temperature_chart,
        question_label=(
            "Ask a question about the selected temperature data"
        ),
        question_placeholder=(
            "Ask about warming trends, anomalies, or specific years..."
        ),
        summary_spinner_text=(
            "Analyzing the selected temperature data..."
        ),
    )

    with st.expander(
        "View underlying temperature data",
        expanded=False,
    ):
        render_temperature_table(
            aggregated_data,
            aggregation,
        )