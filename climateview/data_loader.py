from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent.parent

TEMPERATURE_DIR = (
    BASE_DIR / "data" / "processed" / "noaa-temperature"
)

PRECIPITATION_DIR = (
    BASE_DIR / "data" / "processed" / "noaa-precipitation"
)


@st.cache_data
def load_temperature_data(station_id: str):
    file_path = (
        TEMPERATURE_DIR
        / f"{station_id}_daily_temperature.csv"
    )

    if not file_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(file_path)

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    return df


@st.cache_data
def load_precipitation_data(station_id: str):
    file_path = (
        PRECIPITATION_DIR
        / f"{station_id}_daily_precipitation.csv"
    )

    if not file_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(file_path)

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month_number"] = df["date"].dt.month
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    return df

AIR_QUALITY_DIR = (
    BASE_DIR / "data" / "processed" / "aqs"
)


@st.cache_data
def load_air_quality_data(
    aqs_site_id: str,
    pollutant: str,
):
    """
    Load one processed AQS pollutant file.

    Returns a dictionary with:
      - metadata: top-level station and pollutant information
      - data: pandas DataFrame containing the daily records

    Supported pollutants are "pm25" and "ozone".
    """
    if pollutant not in {"pm25", "ozone"}:
        raise ValueError(
            "pollutant must be either 'pm25' or 'ozone'"
        )

    file_path = (
        AIR_QUALITY_DIR
        / f"aqs-{pollutant}-{aqs_site_id}.json"
    )

    if not file_path.exists():
        return {
            "metadata": {},
            "data": pd.DataFrame(),
        }

    payload = pd.read_json(file_path, typ="series")

    records = payload.get("records", [])
    metadata = {
        key: payload.get(key)
        for key in (
            "station_key",
            "station_name",
            "aqs_site_id",
            "aqs_site_name",
            "pollutant",
            "pollutant_label",
            "parameter_code",
            "record_count",
            "first_date",
            "last_date",
            "source_file_count",
            "dates_without_active_monitor",
            "dates_without_any_active_poc_data",
            "dates_using_fallback_poc",
        )
    }

    if not records:
        return {
            "metadata": metadata,
            "data": pd.DataFrame(),
        }

    df = pd.DataFrame(records)

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    numeric_columns = (
        "value",
        "daily_max",
        "daily_max_hour",
        "aqi",
        "observation_count",
        "observation_percent",
        "poc",
    )

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    df = (
        df.dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    df["year"] = df["date"].dt.year
    df["month_number"] = df["date"].dt.month
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    return {
        "metadata": metadata,
        "data": df,
    }

