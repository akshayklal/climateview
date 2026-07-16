from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def _empty_dataset(dataset: Dict) -> bool:
    if not dataset:
        return True

    data = dataset.get("data")
    return data is None or data.empty


def _value_column_and_unit(
    pollutant: str,
) -> Tuple[str, str]:
    if pollutant == "pm25":
        return "value", "µg/m³"

    return "daily_max", "ppb"


def _prepare_daily_data(
    df: pd.DataFrame,
    pollutant: str,
) -> pd.DataFrame:
    value_column, _ = _value_column_and_unit(pollutant)

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

    if pollutant == "ozone":
        valid["display_value"] = valid[value_column] * 1000.0
    else:
        valid["display_value"] = valid[value_column]

    # Keep one value per date in case the processed file contains duplicates.
    daily = (
        valid.groupby("date", as_index=False)
        .agg(
            display_value=("display_value", "mean"),
            observation_days=("display_value", "count"),
        )
        .sort_values("date")
    )

    daily["year"] = daily["date"].dt.year
    return daily


def _aggregate_air_quality(
    daily: pd.DataFrame,
    aggregation: str,
) -> Tuple[pd.DataFrame, str, str]:
    if daily.empty:
        return pd.DataFrame(), "date", "Date"

    if aggregation == "Day":
        aggregated = daily[
            ["date", "display_value", "observation_days"]
        ].copy()
        x_column = "date"
        x_title = "Date"

    elif aggregation == "Month":
        aggregated = (
            daily.set_index("date")
            .resample("MS")
            .agg(
                display_value=("display_value", "mean"),
                observation_days=("display_value", "count"),
            )
            .reset_index()
        )
        aggregated = aggregated[
            aggregated["observation_days"] > 0
        ].copy()
        x_column = "date"
        x_title = "Month"

    else:
        aggregated = (
            daily.groupby("year", as_index=False)
            .agg(
                display_value=("display_value", "mean"),
                observation_days=("display_value", "count"),
            )
        )
        x_column = "year"
        x_title = "Year"

    return aggregated, x_column, x_title


def _trend_values(
    aggregated: pd.DataFrame,
    x_column: str,
) -> Tuple[Optional[float], Optional[pd.Series]]:
    if len(aggregated) < 2:
        return None, None

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

    trend_data = pd.DataFrame(
        {
            "x": trend_x,
            "y": aggregated["display_value"],
        }
    ).dropna()

    if len(trend_data) < 2:
        return None, None

    slope, intercept = np.polyfit(
        trend_data["x"],
        trend_data["y"],
        1,
    )

    fitted = slope * trend_x + intercept
    return float(slope), fitted


def _y_axis_title(
    pollutant: str,
    aggregation: str,
) -> str:
    if pollutant == "pm25":
        if aggregation == "Day":
            return "Daily PM2.5 (µg/m³)"
        if aggregation == "Month":
            return "Monthly average PM2.5 (µg/m³)"
        return "Annual average PM2.5 (µg/m³)"

    if aggregation == "Day":
        return "Daily maximum ozone (ppb)"
    if aggregation == "Month":
        return "Monthly average daily max ozone (ppb)"
    return "Annual average daily max ozone (ppb)"


def _annual_unhealthy_days(df: pd.DataFrame) -> pd.DataFrame:
    if "aqi" not in df.columns:
        return pd.DataFrame(columns=["year", "unhealthy_days"])

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

    if valid.empty:
        return pd.DataFrame(columns=["year", "unhealthy_days"])

    valid["year"] = valid["date"].dt.year
    valid["unhealthy_day"] = valid["aqi"] > 100

    return (
        valid.groupby("year", as_index=False)
        .agg(unhealthy_days=("unhealthy_day", "sum"))
    )


def _build_air_quality_figure(
    aggregated: pd.DataFrame,
    pollutant: str,
    aggregation: str,
    x_column: str,
    x_title: str,
    unhealthy_days: Optional[pd.DataFrame] = None,
) -> Tuple[go.Figure, Optional[float]]:
    _, unit = _value_column_and_unit(pollutant)
    y_title = _y_axis_title(
        pollutant,
        aggregation,
    )

    trend, fitted = _trend_values(
        aggregated,
        x_column,
    )

    show_unhealthy_days = (
        aggregation == "Year"
        and unhealthy_days is not None
        and not unhealthy_days.empty
    )

    if show_unhealthy_days:
        figure = make_subplots(specs=[[{"secondary_y": True}]])
    else:
        figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=aggregated[x_column],
            y=aggregated["display_value"],
            mode=(
                "lines"
                if aggregation in ("Day", "Month")
                else "lines+markers"
            ),
            name=(
                "Daily value"
                if aggregation == "Day"
                else "Average"
            ),
            hovertemplate=(
                "%{x}<br>"
                f"Value: %{{y:.2f}} {unit}"
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
                name="Trend",
                line={"dash": "dash"},
                hoverinfo="skip",
            ),
            secondary_y=False if show_unhealthy_days else None,
        )

    if show_unhealthy_days:
        annual = aggregated[["year"]].merge(
            unhealthy_days,
            on="year",
            how="left",
        )
        annual["unhealthy_days"] = (
            annual["unhealthy_days"].fillna(0).astype(int)
        )

        figure.add_trace(
            go.Bar(
                x=annual["year"],
                y=annual["unhealthy_days"],
                name="Unhealthy AQI days",
                opacity=0.32,
                hovertemplate=(
                    "Year: %{x}<br>"
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

    figure.update_layout(
        xaxis_title=x_title,
        height=460,
        margin={
            "l": 40,
            "r": 55 if show_unhealthy_days else 30,
            "t": 20,
            "b": 90,
        },
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.20,
            "xanchor": "center",
            "x": 0.5,
        },
        barmode="overlay",
    )

    figure.update_xaxes(showgrid=False)

    return figure, trend


def _render_pollutant_section(
    dataset: Dict,
    pollutant: str,
) -> None:
    if _empty_dataset(dataset):
        label = "PM2.5" if pollutant == "pm25" else "ozone"
        st.info(f"No processed {label} data is available.")
        return

    metadata = dataset["metadata"]
    source_df = dataset["data"].copy()
    daily = _prepare_daily_data(
        source_df,
        pollutant,
    )

    if daily.empty:
        st.info("No valid air-quality records are available.")
        return

    min_year = int(daily["year"].min())
    max_year = int(daily["year"].max())
    pollutant_key = "pm25" if pollutant == "pm25" else "ozone"

    aggregation_col, period_col = st.columns(
        [2.4, 3.2],
        vertical_alignment="bottom",
    )

    with aggregation_col:
        aggregation = st.segmented_control(
            "Aggregation",
            options=["Day", "Month", "Year"],
            default="Year",
            key=f"{pollutant_key}_aggregation",
        )

    if aggregation is None:
        aggregation = "Year"

    with period_col:
        selected_years = st.slider(
            "Period",
            min_value=min_year,
            max_value=max_year,
            value=(min_year, max_year),
            key=f"{pollutant_key}_period",
        )

    filtered_daily = daily[
        daily["year"].between(
            selected_years[0],
            selected_years[1],
        )
    ].copy()

    aggregated, x_column, x_title = _aggregate_air_quality(
        filtered_daily,
        aggregation,
    )

    if aggregated.empty:
        st.info(
            "No air-quality data is available for the selected period."
        )
        return

    filtered_source_df = source_df[
        pd.to_datetime(
            source_df["date"],
            errors="coerce",
        ).dt.year.between(
            selected_years[0],
            selected_years[1],
        )
    ].copy()

    unhealthy_days = _annual_unhealthy_days(filtered_source_df)

    figure, trend = _build_air_quality_figure(
        aggregated=aggregated,
        pollutant=pollutant,
        aggregation=aggregation,
        x_column=x_column,
        x_title=x_title,
        unhealthy_days=unhealthy_days,
    )

    _, unit = _value_column_and_unit(pollutant)
    average_value = float(
        aggregated["display_value"].mean()
    )
    highest_value = float(
        aggregated["display_value"].max()
    )

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
        st.metric(
            "Average",
            f"{average_value:.1f} {unit}",
        )

    with metric_columns[2]:
        st.metric(
            "Highest value",
            f"{highest_value:.1f} {unit}",
        )

    with metric_columns[3]:
        st.metric(
            "Daily observations",
            f"{len(filtered_daily):,}",
        )

    st.plotly_chart(
        figure,
        width="stretch",
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
        st.write(
            "Fallback POC dates:",
            metadata.get("dates_using_fallback_poc", 0) or 0,
        )
        st.write(
            "Dates without an active monitor:",
            metadata.get("dates_without_active_monitor", 0) or 0,
        )


def render_air_quality_tab(
    pm25_data: Dict,
    ozone_data: Dict,
    station_name: str,
) -> None:
    """Render the Air Quality tab for one ClimateView station."""
    pm25_tab, ozone_tab = st.tabs(
        ["PM2.5", "Ozone"]
    )

    with pm25_tab:
        _render_pollutant_section(
            pm25_data,
            "pm25",
        )

    with ozone_tab:
        _render_pollutant_section(
            ozone_data,
            "ozone",
        )
