from pathlib import Path

import pandas as pd
import streamlit as st

from climateview.aqs_config import AQS_POLLUTANTS
from climateview.stations import STATIONS

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
    return _load_noaa_csv(file_path)


@st.cache_data
def load_precipitation_data(station_id: str):
    file_path = (
        PRECIPITATION_DIR
        / f"{station_id}_daily_precipitation.csv"
    )

    return _load_noaa_csv(file_path, include_month_number=True)


def _load_noaa_csv(
    file_path: Path,
    *,
    include_month_number: bool = False,
) -> pd.DataFrame:
    """Load a daily NOAA file and add its shared period columns."""
    if not file_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(file_path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    if include_month_number:
        df["month_number"] = df["date"].dt.month

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
    if pollutant not in AQS_POLLUTANTS:
        raise ValueError(
            "pollutant must be either 'pm25' or 'ozone'"
        )

    file_path = (
        AIR_QUALITY_DIR
        / f"aqs-{pollutant}-{aqs_site_id}.csv"
    )

    if not file_path.exists():
        return {
            "metadata": {},
            "data": pd.DataFrame(),
        }

    config = AQS_POLLUTANTS[pollutant]
    station = next(
        (
            value
            for value in STATIONS.values()
            if value.get("aqs_site_id") == aqs_site_id
        ),
        {},
    )
    metadata = {
        "aqs_site_id": aqs_site_id,
        "aqs_site_name": station.get("aqs_site_name"),
        "parameter_code": config["parameter_code"],
    }

    df = pd.read_csv(file_path, parse_dates=["date"])

    numeric_columns = (
        config["value_column"],
        "aqi",
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

    return {
        "metadata": metadata,
        "data": df,
    }
