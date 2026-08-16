import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from climateview.ai_insights import render_ai_insights
from climateview.charts import (
    HIGHLIGHT_COLOR,
    apply_standard_layout,
    calculate_linear_trend,
    insert_gap_breaks,
    select_referenced_periods,
)
from climateview.presentation import (
    TEMPERATURE,
    format_decadal_trend,
    render_location_summary,
)
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)


TEMPERATURE_TABLE_PERIODS = {
    "Month": ("month", "Month"),
    "Year": ("year", "Year"),
    "Decade": ("decade", "Decade"),
}

TEMPERATURE_SEASON_MONTHS = {
    "Winter": {12, 1, 2},
    "Spring": {3, 4, 5},
    "Summer": {6, 7, 8},
    "Fall": {9, 10, 11},
}


def filter_temperature_season(data: pd.DataFrame, season: str) -> pd.DataFrame:
    if season == "All year":
        return data.copy()

    months = TEMPERATURE_SEASON_MONTHS[season]
    filtered = data[data["date"].dt.month.isin(months)].copy()

    # Treat December as part of the winter ending the following year.
    if season == "Winter":
        filtered["year"] = filtered["date"].dt.year + (
            filtered["date"].dt.month == 12
        ).astype(int)
        filtered["decade"] = (filtered["year"] // 10) * 10

    return filtered


def build_temperature_aggregation(
    data,
    aggregation,
    *,
    minimum_days_per_year=300,
):
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
            (grouped["days_with_tmax"] >= minimum_days_per_year)
            & (grouped["days_with_tmin"] >= minimum_days_per_year)
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


def build_temperature_figure(aggregated_data, x_col, x_title):
    if x_col == "month":
        maximum_gap = pd.Timedelta(days=45)
    elif x_col == "year":
        maximum_gap = 1.5
    else:
        maximum_gap = 15

    plot_data = insert_gap_breaks(
        aggregated_data,
        x_col=x_col,
        y_cols=["avg_tmax_f", "avg_tmin_f"],
        max_gap=maximum_gap,
    )

    max_trend, max_trend_values = calculate_linear_trend(
        aggregated_data["trend_year"],
        aggregated_data["avg_tmax_f"],
    )

    min_trend, min_trend_values = calculate_linear_trend(
        aggregated_data["trend_year"],
        aggregated_data["avg_tmin_f"],
    )

    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=plot_data[x_col],
            y=plot_data["avg_tmax_f"],
            mode="lines+markers",
            name="Average maximum",
            line={"color": TEMPERATURE["dark"]},
            marker={"color": TEMPERATURE["dark"]},
            connectgaps=False,
            hovertemplate=(
                "%{x}<br>"
                "Average maximum: %{y:.1f} °F"
                "<extra></extra>"
            ),
        )
    )

    figure.add_trace(
        go.Scatter(
            x=plot_data[x_col],
            y=plot_data["avg_tmin_f"],
            mode="lines+markers",
            name="Average minimum",
            line={"color": TEMPERATURE["light"]},
            marker={"color": TEMPERATURE["light"]},
            connectgaps=False,
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
                line={"color": TEMPERATURE["dark"], "dash": "dash"},
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
                line={"color": TEMPERATURE["light"], "dash": "dash"},
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
            "t": 70,
            "b": 100,
        },
        yaxis_title="Temperature (°F)",
    )

    figure.update_yaxes(
        showgrid=True,
        zeroline=False,
    )

    return figure, max_trend, min_trend


def render_temperature_table(aggregated_data, aggregation):
    period_column, period_label = TEMPERATURE_TABLE_PERIODS[aggregation]
    display_columns = [
        period_label,
        "Average maximum (°F)",
        "Average minimum (°F)",
        "Maximum observations",
        "Minimum observations",
    ]
    display_data = aggregated_data.rename(
        columns={
            period_column: period_label,
            "avg_tmax_f": "Average maximum (°F)",
            "avg_tmin_f": "Average minimum (°F)",
            "days_with_tmax": "Maximum observations",
            "days_with_tmin": "Minimum observations",
        }
    )[display_columns].copy()

    if aggregation == "Month":
        display_data[period_label] = display_data[
            period_label
        ].dt.strftime("%B %Y")

    display_data["Average maximum (°F)"] = display_data[
        "Average maximum (°F)"
    ].round(1)

    display_data["Average minimum (°F)"] = display_data[
        "Average minimum (°F)"
    ].round(1)

    st.dataframe(display_data, width="stretch", hide_index=True)


def render_temperature_tab(data, station_name, summary_placeholder=None):
    if data is None or data.empty:
        st.warning("No temperature data is available for this station.")
        return

    required_columns = {
        "date",
        "year",
        "month",
        "decade",
        "tmax_f",
        "tmin_f",
    }

    missing_columns = required_columns - set(data.columns)

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

    aggregation_col, season_col, range_col = st.columns(
        [1.4, 2.6, 4.0], vertical_alignment="bottom"
    )

    with aggregation_col:
        aggregation = st.segmented_control(
            "Aggregation",
            options=["Month", "Year", "Decade"],
            default=(
                None
                if "temperature_aggregation" in st.session_state
                else "Year"
            ),
            key="temperature_aggregation",
        )

    # Fallback for Streamlit versions where no value is initially returned.
    if aggregation is None:
        aggregation = "Year"

    with season_col:
        season = st.segmented_control(
            "Season",
            options=["All year", "Winter", "Spring", "Summer", "Fall"],
            default=(
                None
                if "temperature_season" in st.session_state
                else "All year"
            ),
            key="temperature_season",
        )

    if season is None:
        season = "All year"

    with range_col:
        selected_years = st.slider(
            "Date Range", min_year, max_year, (min_year, max_year),
            key="temperature_period",
        )

    seasonal_data = filter_temperature_season(data, season)
    filtered_data = seasonal_data[
        seasonal_data["year"].between(*selected_years)
    ].copy()

    aggregated_data, x_col, x_title = build_temperature_aggregation(
        filtered_data,
        aggregation,
        minimum_days_per_year=300 if season == "All year" else 60,
    )

    if aggregated_data.empty:
        st.info(
            "No sufficiently complete temperature records are available "
            "for the selected period."
        )
        return

    figure, max_trend, min_trend = build_temperature_figure(
        aggregated_data, x_col, x_title
    )

    if summary_placeholder is not None:
        if max_trend is None or min_trend is None:
            summary = "No clear long-term temperature trend is available."
        else:
            nighttime_leads = abs(min_trend) >= abs(max_trend)
            trend = min_trend if nighttime_leads else max_trend
            period = "Nighttime" if nighttime_leads else "Daytime"
            summary = format_decadal_trend(
                f"{period} temperatures",
                trend,
                selected_years[0],
                "°F",
                ("are warming", "are cooling"),
                unchanged_subject="Temperatures",
                qualifier=" fastest",
            )
        render_location_summary(summary_placeholder, summary)

    metric1, metric2 = st.columns(2)

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

    analysis_data = aggregated_data.copy()
    analysis_data["avg_temperature_f"] = (
        analysis_data["avg_tmax_f"]
        + analysis_data["avg_tmin_f"]
    ) / 2.0

    analysis = analyze_series(
        dataframe=analysis_data,
        context=AnalysisContext(
            location=station_name,
            metric=(
                "temperature"
                if season == "All year"
                else f"{season.lower()} temperature"
            ),
            unit="degrees Fahrenheit",
            aggregation=aggregation.lower(),
            start_period=selected_years[0],
            end_period=selected_years[1],
        ),
        schema=DataSchema(
            period_column=x_col,
            value_column="avg_temperature_f",
            ranked_value_columns={
                "average maximum temperature": "avg_tmax_f",
                "average minimum temperature": "avg_tmin_f",
            },
        ),
    )

    insight_signature = (
        station_name,
        aggregation,
        season,
        selected_years[0],
        selected_years[1],
    )

    def render_temperature_chart(referenced_periods, referenced_series):
        highlighted = select_referenced_periods(
            aggregated_data,
            x_col,
            referenced_periods,
        )
        if not highlighted.empty:
            temperature_series = (
                ("avg_tmax_f", "Referenced maximum"),
                ("avg_tmin_f", "Referenced minimum"),
            )
            normalized_series = {
                series.strip().lower() for series in referenced_series
            }
            line_specific_series = normalized_series & {
                "average maximum temperature",
                "average minimum temperature",
            }
            if line_specific_series:
                temperature_series = tuple(
                    item
                    for item in temperature_series
                    if (
                        item[0] == "avg_tmax_f"
                        and "average maximum temperature" in line_specific_series
                    )
                    or (
                        item[0] == "avg_tmin_f"
                        and "average minimum temperature" in line_specific_series
                    )
                )

            for value_col, label in temperature_series:
                figure.add_trace(
                    go.Scatter(
                        x=highlighted[x_col],
                        y=highlighted[value_col],
                        mode="markers",
                        name=label,
                        marker={
                            "color": HIGHLIGHT_COLOR,
                            "size": 12,
                            "line": {"color": "white", "width": 2},
                        },
                        hoverinfo="skip",
                    )
                )
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
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

    with st.expander("View underlying temperature data", expanded=False):
        render_temperature_table(aggregated_data, aggregation)
