from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from climateview.aqs_config import AQS_POLLUTANTS as POLLUTANTS
from climateview.ai_insights import render_ai_insights
from climateview.charts import (
    HIGHLIGHT_COLOR,
    apply_standard_layout,
    calculate_linear_trend,
    insert_gap_breaks,
    select_referenced_periods,
)
from climateview.presentation import (
    AIR_QUALITY,
    format_decadal_trend,
    render_location_summary,
)
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)

def _empty_dataset(dataset: dict) -> bool:
    if not dataset:
        return True

    data = dataset.get("data")
    return data is None or data.empty


@st.cache_data(show_spinner=False)
def _prepare_daily_data(
    df: pd.DataFrame,
    pollutant: str,
) -> pd.DataFrame:
    config = POLLUTANTS[pollutant]
    value_column = config["value_column"]

    valid = df.copy()
    valid["date"] = pd.to_datetime(
        valid["date"],
        errors="coerce",
    )
    valid[value_column] = pd.to_numeric(
        valid[value_column],
        errors="coerce",
    )
    valid = valid.dropna(
        subset=["date", value_column],
    )

    if valid.empty:
        return pd.DataFrame()

    valid["display_value"] = (
        valid[value_column] * config["display_scale"]
    )

    # Keep one value per date in case the processed file contains duplicates.
    daily = (
        valid.groupby("date", as_index=False)
        .agg(display_value=("display_value", "mean"))
        .sort_values("date")
    )

    daily["year"] = daily["date"].dt.year
    return daily


def _aggregate_air_quality(
    daily: pd.DataFrame,
    aggregation: str,
) -> tuple[pd.DataFrame, str, str]:
    if daily.empty:
        return pd.DataFrame(), "date", "Date"

    if aggregation == "Day":
        aggregated = daily[["date", "display_value"]].copy()
        x_column = "date"
        x_title = "Date"

    elif aggregation == "Month":
        aggregated = (
            daily.set_index("date")
            .resample("MS")
            .agg(display_value=("display_value", "mean"))
            .reset_index()
        )
        aggregated = aggregated.dropna(subset=["display_value"])
        x_column = "date"
        x_title = "Month"

    else:
        aggregated = (
            daily.groupby("year", as_index=False)
            .agg(display_value=("display_value", "mean"))
        )
        x_column = "year"
        x_title = "Year"

    return aggregated, x_column, x_title


def _unhealthy_days(
    df: pd.DataFrame,
    aggregation: str,
) -> pd.DataFrame:
    if "aqi" not in df.columns:
        key_column = "date" if aggregation == "Month" else "year"
        return pd.DataFrame(columns=[key_column, "unhealthy_days"])

    valid = df.copy()
    valid["date"] = pd.to_datetime(
        valid["date"],
        errors="coerce",
    )
    valid["aqi"] = pd.to_numeric(
        valid["aqi"],
        errors="coerce",
    )
    valid = valid.dropna(
        subset=["date", "aqi"],
    )

    key_column = "date" if aggregation == "Month" else "year"
    if valid.empty:
        return pd.DataFrame(columns=[key_column, "unhealthy_days"])

    # Keep one AQI value per date so duplicate source records do not
    # inflate the unhealthy-day count.
    daily_aqi = (
        valid.groupby("date", as_index=False)
        .agg(aqi=("aqi", "max"))
        .sort_values("date")
    )
    daily_aqi["unhealthy_day"] = daily_aqi["aqi"] > 100

    if aggregation == "Month":
        return (
            daily_aqi.set_index("date")
            .resample("MS")
            .agg(unhealthy_days=("unhealthy_day", "sum"))
            .reset_index()
        )

    daily_aqi["year"] = daily_aqi["date"].dt.year
    return (
        daily_aqi.groupby("year", as_index=False)
        .agg(unhealthy_days=("unhealthy_day", "sum"))
    )


def _build_air_quality_figure(
    aggregated: pd.DataFrame,
    pollutant: str,
    aggregation: str,
    x_column: str,
    x_title: str,
    unhealthy_days: Optional[pd.DataFrame] = None,
) -> tuple[go.Figure, Optional[float]]:
    config = POLLUTANTS[pollutant]
    pollutant_name = config["label"]
    unit = config["unit"]
    y_title = config["axis_titles"][aggregation]

    if x_column == "year":
        trend_x = aggregated["year"].astype(float)
    else:
        dates = pd.to_datetime(
            aggregated["date"],
            errors="coerce",
        )
        trend_x = (
            dates.dt.year
            + (dates.dt.dayofyear - 1) / 365.25
        )

    trend, fitted = calculate_linear_trend(
        trend_x,
        aggregated["display_value"],
    )

    if aggregation == "Day":
        maximum_gap = pd.Timedelta(days=30)
    elif aggregation == "Month":
        maximum_gap = pd.Timedelta(days=45)
    else:
        maximum_gap = 1.5

    plot_data = insert_gap_breaks(
        aggregated,
        x_col=x_column,
        y_cols=["display_value"],
        max_gap=maximum_gap,
    )

    show_unhealthy_days = (
        aggregation in ("Month", "Year")
        and unhealthy_days is not None
        and not unhealthy_days.empty
    )

    if show_unhealthy_days:
        figure = make_subplots(specs=[[{"secondary_y": True}]])
    else:
        figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=plot_data[x_column],
            y=plot_data["display_value"],
            mode=(
                "lines"
                if aggregation in ("Day", "Month")
                else "lines+markers"
            ),
            name=(
                f"Daily {pollutant_name}"
                if aggregation == "Day"
                else f"Average {pollutant_name}"
            ),
            connectgaps=False,
            line={"color": AIR_QUALITY["primary"]},
            marker={"color": AIR_QUALITY["primary"]},
            hovertemplate=(
                "%{x}<br>"
                f"{pollutant_name}: %{{y:.2f}} {unit}"
                "<extra></extra>"
            ),
        ),
        secondary_y=False if show_unhealthy_days else None,
    )

    if fitted is not None:
        figure.add_trace(
            go.Scatter(
                x=aggregated[x_column],
                y=fitted,
                mode="lines",
                name=f"{pollutant_name} trend",
                line={"color": AIR_QUALITY["dark"], "dash": "dash"},
                hoverinfo="skip",
            ),
            secondary_y=False if show_unhealthy_days else None,
        )

    if show_unhealthy_days:
        unhealthy_x_column = (
            "date" if aggregation == "Month" else "year"
        )
        unhealthy = aggregated[[unhealthy_x_column]].merge(
            unhealthy_days,
            on=unhealthy_x_column,
            how="left",
        )
        unhealthy["unhealthy_days"] = (
            unhealthy["unhealthy_days"].fillna(0).astype(int)
        )
        hover_period = "Month" if aggregation == "Month" else "Year"

        figure.add_trace(
            go.Bar(
                x=unhealthy[unhealthy_x_column],
                y=unhealthy["unhealthy_days"],
                name="Unhealthy AQI days",
                marker_color=AIR_QUALITY["light"],
                opacity=0.55,
                hovertemplate=(
                    f"{hover_period}: %{{x}}<br>"
                    "Unhealthy AQI days: %{y}"
                    "<extra></extra>"
                ),
            ),
            secondary_y=True,
        )

        figure.update_yaxes(
            title_text=y_title,
            showgrid=True,
            zeroline=False,
            secondary_y=False,
        )
        figure.update_yaxes(
            title_text="Unhealthy AQI days",
            showgrid=False,
            rangemode="tozero",
            secondary_y=True,
        )
    else:
        figure.update_yaxes(
            title_text=y_title,
            showgrid=True,
            zeroline=False,
        )

    apply_standard_layout(
        figure,
        x_title=x_title,
        height=460,
        margins={
            "l": 40,
            "r": 55 if show_unhealthy_days else 30,
            "t": 20,
            "b": 90,
        },
        barmode="overlay",
    )

    return figure, trend


def _render_pollutant_section(
    pm25_data: dict,
    ozone_data: dict,
    station_name: str,
    summary_placeholder=None,
) -> None:
    control_columns = st.columns(
        [2.5, 1.5, 5.0], vertical_alignment="bottom"
    )

    with control_columns[0]:
        pollutant_options = {
            config["label"]: pollutant
            for pollutant, config in POLLUTANTS.items()
        }
        pollutant_label = st.segmented_control(
            "Pollutant",
            options=list(pollutant_options),
            default=(
                None
                if "air_quality_pollutant" in st.session_state
                else POLLUTANTS["pm25"]["label"]
            ),
            key="air_quality_pollutant",
        )

    pollutant = pollutant_options.get(pollutant_label, "pm25")
    config = POLLUTANTS[pollutant]

    dataset = ozone_data if pollutant == "ozone" else pm25_data

    if _empty_dataset(dataset):
        st.info(f"No processed {config['label']} data is available.")
        return

    metadata = dataset["metadata"]
    source_df = dataset["data"]

    daily = _prepare_daily_data(source_df, pollutant)

    if daily.empty:
        st.info("No valid air-quality records are available.")
        return

    min_year = int(daily["year"].min())
    max_year = int(daily["year"].max())
    pollutant_key = pollutant

    with control_columns[1]:
        aggregation = st.segmented_control(
            "Aggregation",
            options=["Day", "Month", "Year"],
            default="Year",
            key=f"{pollutant_key}_aggregation",
        )

    if aggregation is None:
        aggregation = "Year"

    with control_columns[2]:
        selected_years = st.slider(
            "Date Range", min_year, max_year, (min_year, max_year),
            key=f"{pollutant_key}_period",
        )

    filtered_daily = daily[daily["year"].between(*selected_years)].copy()

    aggregated, x_column, x_title = _aggregate_air_quality(
        filtered_daily,
        aggregation,
    )

    if aggregated.empty:
        st.info(
            "No air-quality data is available for the selected period."
        )
        return

    unhealthy_days = None
    if aggregation != "Day":
        filtered_source_df = source_df[
            source_df["date"].dt.year.between(
                selected_years[0],
                selected_years[1],
            )
        ].copy()
        unhealthy_days = _unhealthy_days(filtered_source_df, aggregation)

    figure, trend = _build_air_quality_figure(
        aggregated=aggregated,
        pollutant=pollutant,
        aggregation=aggregation,
        x_column=x_column,
        x_title=x_title,
        unhealthy_days=unhealthy_days,
    )

    if summary_placeholder is not None:
        if trend is None:
            summary = (
                f"No clear long-term {config['label'].lower()} trend is "
                "available."
            )
        else:
            summary = format_decadal_trend(
                config["label"],
                trend,
                selected_years[0],
                f" {config['unit']}",
                ("is worsening", "is improving"),
            )
        render_location_summary(summary_placeholder, summary)
    uses_secondary_axis = "yaxis2" in figure.layout

    unit = config["unit"]
    average_value = float(aggregated["display_value"].mean())
    highest_value = float(aggregated["display_value"].max())

    metric_columns = st.columns(4)

    with metric_columns[0]:
        st.metric(
            "Trend",
            (
                f"{trend:+.3f} {unit}/year"
                if trend is not None
                else "Insufficient data"
            ),
        )

    with metric_columns[1]:
        st.metric("Average", f"{average_value:.1f} {unit}")

    with metric_columns[2]:
        st.metric("Highest value", f"{highest_value:.1f} {unit}")

    with metric_columns[3]:
        st.metric("Daily observations", f"{len(filtered_daily):,}")

    pollutant_name = config["label"]

    analysis_data = aggregated.copy()
    ranked_value_columns = {}
    if unhealthy_days is not None and not unhealthy_days.empty:
        unhealthy_x_column = (
            "date" if aggregation == "Month" else "year"
        )
        analysis_data = analysis_data.merge(
            unhealthy_days,
            on=unhealthy_x_column,
            how="left",
        )
        ranked_value_columns["unhealthy AQI days"] = "unhealthy_days"

    analysis = analyze_series(
        dataframe=analysis_data,
        context=AnalysisContext(
            location=station_name,
            metric=pollutant_name,
            unit=unit,
            aggregation=aggregation.lower(),
            start_period=selected_years[0],
            end_period=selected_years[1],
        ),
        schema=DataSchema(
            period_column=x_column,
            value_column="display_value",
            ranked_value_columns=ranked_value_columns,
        ),
    )

    insight_signature = (
        station_name,
        pollutant_key,
        pollutant_name,
        aggregation,
        selected_years[0],
        selected_years[1],
    )

    def render_air_quality_chart(referenced_periods, _referenced_series):
        highlighted = select_referenced_periods(
            aggregated,
            x_column,
            referenced_periods,
        )
        if not highlighted.empty:
            figure.add_trace(
                go.Scatter(
                    x=highlighted[x_column],
                    y=highlighted["display_value"],
                    mode="markers",
                    name="AI referenced period",
                    marker={
                        "color": HIGHLIGHT_COLOR,
                        "size": 12,
                        "line": {"color": "white", "width": 2},
                    },
                    hoverinfo="skip",
                ),
                secondary_y=False if uses_secondary_axis else None,
            )
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )

    render_ai_insights(
        analysis=analysis,
        state_prefix=f"air_quality_{pollutant_key}",
        signature=insight_signature,
        render_below=render_air_quality_chart,
        question_label=(
            f"Ask a question about the selected {pollutant_name} data"
        ),
        question_placeholder=(
            "Ask about trends, unhealthy periods, or specific years..."
        ),
        summary_spinner_text=(
            f"Analyzing the selected {pollutant_name} data..."
        ),
    )

    with st.expander(
        "Data notes",
        expanded=False,
    ):
        st.write(
            "AQS site:",
            metadata.get("aqs_site_name")
            or metadata.get("aqs_site_id")
            or "Unavailable",
        )
        st.write(
            "Parameter code:",
            metadata.get("parameter_code") or "Unavailable",
        )


def render_air_quality_tab(
    pm25_data: dict,
    ozone_data: dict,
    station_name: str,
    summary_placeholder=None,
) -> None:
    """Render the Air Quality tab for one ClimateView station."""
    _render_pollutant_section(
        pm25_data, ozone_data, station_name, summary_placeholder
    )
