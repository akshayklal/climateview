from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent.parent

TEMPERATURE_FILE = (
    BASE_DIR / "data" / "processed" / "USW00023234_daily_temperature.csv"
)

PRECIPITATION_FILE = (
    BASE_DIR / "data" / "processed" / "USW00023234_daily_precipitation.csv"
)


@st.cache_data
def load_temperature_data():
    df = pd.read_csv(TEMPERATURE_FILE)

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    return df


@st.cache_data
def load_precipitation_data():
    df = pd.read_csv(PRECIPITATION_FILE)

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month_number"] = df["date"].dt.month
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["decade"] = (df["year"] // 10) * 10

    return df