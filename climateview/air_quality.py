from typing import Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def _empty_dataset(dataset: Dict) -> bool:
    if not dataset:
        return True

    data = dataset.get("data")

    return data is None or data.empty


def _format_date_range(metadata: Dict) -> str:
    first_date = metadata.get("first_date")
    last_date = metadata.get("last_date")

    if not first_date or not last_date:
        return "Date range unavailable"

    return f"{first_date} to {last_date}"


def _annual_summary(
    df: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    valid = df.dropna(
        subset=["date", value_column]
    ).copy()

    if valid.empty:
        return pd.DataFrame()

    annual = (
        valid.groupby("year", as_index=False)
        .agg(
            annual_mean=(value_column, "mean"),
            annual_max=(value_column, "max"),
            observation_days=(value_column, "count"),
        )
    )

    return annual


def _render_annual_trend(
    df: pd.DataFrame,
    pollutant: str,
) -> None:
    if pollutant == "pm25":
        value_column = "value"
        chart_title = "Annual average PM2.5 concentration"
        y_title = "PM2.5 (µg/m³)"
    else:
        value_column = "daily_max"
        chart_title = "Annual average daily maximum ozone"
        y_title = "Ozone (ppb)"

    annual = _annual_summary(
        df,
        value_column,
    )

    if annual.empty:
        st.info("No annual trend data is available.")
        return

    if pollutant == "ozone":
        annual["annual_mean"] = (
            annual["annual_mean"] * 1000.0
        )
        annual["annual_max"] = (
            annual["annual_max"] * 1000.0
        )

    figure = px.line(
        annual,
        x="year",
        y="annual_mean",
        markers=True,
        labels={
            "year": "Year",
            "annual_mean": y_title,
        },
        title=chart_title,
    )

    figure.update_traces(
        hovertemplate=(
            "Year: %{x}<br>"
            f"{y_title}: %{{y:.2f}}"
            "<extra></extra>"
        )
    )

    figure.update_layout(
        height=430,
        margin=dict(l=20, r=20, t=60, b=20),
        hovermode="x unified",
    )

    st.plotly_chart(
        figure,
        width="stretch",
    )


def _render_aqi_days(df: pd.DataFrame) -> None:
    if "aqi" not in df.columns:
        return

    valid = df.dropna(subset=["aqi"]).copy()

    if valid.empty:
        return

    valid["unhealthy_day"] = valid["aqi"] > 100

    annual = (
        valid.groupby("year", as_index=False)
        .agg(
            unhealthy_days=("unhealthy_day", "sum"),
            aqi_days=("aqi", "count"),
        )
    )

    figure = px.bar(
        annual,
        x="year",
        y="unhealthy_days",
        labels={
            "year": "Year",
            "unhealthy_days": "Days with AQI above 100",
        },
        title="Days with unhealthy AQI",
    )

    figure.update_traces(
        hovertemplate=(
            "Year: %{x}<br>"
            "Days: %{y}<extra></extra>"
        )
    )

    figure.update_layout(
        height=380,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    st.plotly_chart(
        figure,
        width="stretch",
    )


def _render_monthly_detail(
    df: pd.DataFrame,
    pollutant: str,
) -> None:
    if pollutant == "pm25":
        value_column = "value"
        y_title = "PM2.5 (µg/m³)"
    else:
        value_column = "daily_max"
        y_title = "Ozone (ppb)"

    valid = df.dropna(
        subset=["date", value_column]
    ).copy()

    if valid.empty:
        return

    if pollutant == "ozone":
        valid["display_value"] = (
            valid[value_column] * 1000.0
        )
    else:
        valid["display_value"] = valid[value_column]

    monthly = (
        valid.set_index("date")["display_value"]
        .resample("MS")
        .mean()
        .reset_index()
    )

    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=monthly["date"],
            y=monthly["display_value"],
            mode="lines",
            name="Monthly mean",
            hovertemplate=(
                "%{x|%b %Y}<br>"
                f"{y_title}: %{{y:.2f}}"
                "<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        title="Monthly average",
        xaxis_title="Date",
        yaxis_title=y_title,
        height=420,
        margin=dict(l=20, r=20, t=60, b=20),
        hovermode="x unified",
    )

    st.plotly_chart(
        figure,
        width="stretch",
    )


def _render_pollutant_section(
    dataset: Dict,
    pollutant: str,
) -> None:
    if _empty_dataset(dataset):
        label = "PM2.5" if pollutant == "pm25" else "ozone"
        st.info(f"No processed {label} data is available.")
        return

    metadata = dataset["metadata"]
    df = dataset["data"]

    pollutant_label = metadata.get(
        "pollutant_label",
        "PM2.5" if pollutant == "pm25" else "Ozone",
    )

    st.markdown(f"### {pollutant_label}")
    st.caption(
        f"{_format_date_range(metadata)} · "
        f"{len(df):,} daily observations"
    )

    latest = df.dropna(
        subset=["date"]
    ).sort_values("date")

    metric_columns = st.columns(3)

    with metric_columns[0]:
        st.metric(
            "First year",
            int(df["year"].min()),
        )

    with metric_columns[1]:
        st.metric(
            "Latest year",
            int(df["year"].max()),
        )

    with metric_columns[2]:
        st.metric(
            "Observation days",
            f"{len(df):,}",
        )

    _render_annual_trend(
        df,
        pollutant,
    )

    _render_aqi_days(df)

    with st.expander(
        "Monthly detail",
        expanded=False,
    ):
        _render_monthly_detail(
            df,
            pollutant,
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
    st.subheader("Air quality")
    st.caption(
        f"Long-term PM2.5 and ozone trends near {station_name}. "
        "Source: U.S. EPA Air Quality System."
    )

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
