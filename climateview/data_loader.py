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