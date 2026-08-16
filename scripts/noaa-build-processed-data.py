import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from station_utils import noaa_station_ids, select_stations


METRICS = {
    "temperature": {
        "columns": {"TMAX": "tmax_f", "TMIN": "tmin_f"},
    },
    "precipitation": {
        "columns": {"PRCP": "prcp_in"},
    },
}


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        print(f"Missing raw file, skipping: {path}")
        return []
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _records_to_dataframe(
    records: list[dict],
    value_column: str,
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["date", value_column])

    dataframe = pd.DataFrame(records)
    dataframe["date"] = pd.to_datetime(dataframe["date"]).dt.date
    dataframe[value_column] = pd.to_numeric(
        dataframe["value"], errors="coerce"
    )
    return (
        dataframe[["date", value_column]]
        .drop_duplicates(subset=["date"])
        .sort_values("date")
    )


def build_processed_data(
    station_code: str,
    start_year: int,
    end_year: int,
    metric: str,
) -> pd.DataFrame:
    columns = METRICS[metric]["columns"]
    _, file_station_id, clean_station_id = noaa_station_ids(station_code)
    raw_data_dir = Path(f"data/raw/noaa-{metric}")
    all_rows = []

    for year in range(start_year, end_year + 1):
        daily = None
        for datatype, value_column in columns.items():
            path = (
                raw_data_dir
                / clean_station_id
                / f"noaa-{metric}-{datatype}-{file_station_id}-{year}.json"
            )
            values = _records_to_dataframe(
                _load_records(path), value_column
            )
            daily = (
                values
                if daily is None
                else daily.merge(values, on="date", how="outer")
            )

        daily["station_id"] = clean_station_id
        all_rows.append(daily)

    output_columns = ["station_id", "date", *columns.values()]
    if not all_rows:
        return pd.DataFrame(columns=output_columns)

    return (
        pd.concat(all_rows, ignore_index=True)[output_columns]
        .sort_values("date")
        .drop_duplicates(subset=["station_id", "date"])
    )


def run(metric: str) -> None:
    parser = argparse.ArgumentParser(
        description=f"Build processed daily NOAA {metric} data."
    )
    parser.add_argument(
        "--station",
        help="NOAA station ID. If omitted, all stations are processed.",
    )
    args = parser.parse_args()

    output_dir = Path(f"data/processed/noaa-{metric}")
    output_dir.mkdir(parents=True, exist_ok=True)
    end_year = date.today().year - 1

    for station_key, station in select_stations(args.station):
        station_id = station.get("noaa_station_id")
        configured_start = station.get("noaa_start_year")
        if not station_id or configured_start is None:
            print(f"Skipping {station_key}: incomplete NOAA configuration.")
            continue

        # Skip the potentially partial first calendar year of operation.
        start_year = int(configured_start) + 1
        if end_year < start_year:
            print(f"Skipping {station_key}: no complete years to process.")
            continue

        print(
            f"Processing {station.get('name', station_key)} ({station_id}) "
            f"from {start_year} through {end_year}"
        )
        processed = build_processed_data(
            station_id, start_year, end_year, metric
        )
        _, _, clean_station_id = noaa_station_ids(station_id)
        output_file = output_dir / f"{clean_station_id}_daily_{metric}.csv"
        processed.to_csv(output_file, index=False)
        print(f"Wrote {len(processed)} rows to {output_file}")
