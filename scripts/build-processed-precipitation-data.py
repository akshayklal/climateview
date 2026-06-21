import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")


def station_file_id(station_code: str) -> str:
    station_code = station_code.strip()

    if station_code.startswith("GHCND:"):
        station_id = station_code
    else:
        station_id = "GHCND:" + station_code

    return station_id.replace(":", "_").replace("/", "_")


def output_station_id(station_code: str) -> str:
    station_code = station_code.strip()

    if station_code.startswith("GHCND:"):
        return station_code.split(":", 1)[1]

    return station_code


def raw_file_path(file_station_id: str, year: int) -> Path:
    return RAW_DATA_DIR / "noaa-precipitation-PRCP-{}-{}.json".format(
        file_station_id,
        year,
    )


def load_raw_records(path: Path) -> List[Dict]:
    if not path.exists():
        print("Missing raw file, skipping: {}".format(path))
        return []

    with path.open("r") as f:
        return json.load(f)


def records_to_dataframe(records: List[Dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["date", "prcp_in"])

    df = pd.DataFrame(records)

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["prcp_in"] = pd.to_numeric(df["value"], errors="coerce")

    df = df[["date", "prcp_in"]]
    df = df.drop_duplicates(subset=["date"])
    df = df.sort_values("date")

    return df


def build_processed_precipitation_data(
    station_code: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    file_station_id = station_file_id(station_code)
    clean_station_id = output_station_id(station_code)

    all_rows = []

    for year in range(start_year, end_year + 1):
        path = raw_file_path(file_station_id, year)
        records = load_raw_records(path)

        yearly_df = records_to_dataframe(records)
        yearly_df["station_id"] = clean_station_id

        all_rows.append(yearly_df)

    if not all_rows:
        return pd.DataFrame(columns=["station_id", "date", "prcp_in"])

    result = pd.concat(all_rows, ignore_index=True)

    result = result[["station_id", "date", "prcp_in"]]
    result = result.sort_values("date")
    result = result.drop_duplicates(subset=["station_id", "date"])

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build processed daily precipitation CSV from raw NOAA PRCP JSON files."
    )

    parser.add_argument(
        "--station",
        required=True,
        help="NOAA station code, e.g. USW00023234 or GHCND:USW00023234",
    )

    parser.add_argument(
        "--start-year",
        type=int,
        required=True,
        help="Start year, e.g. 1946",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        required=True,
        help="End year, e.g. 2024",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.end_year < args.start_year:
        raise ValueError("end-year must be greater than or equal to start-year")

    processed = build_processed_precipitation_data(
        station_code=args.station,
        start_year=args.start_year,
        end_year=args.end_year,
    )

    station_id = output_station_id(args.station)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_file = PROCESSED_DATA_DIR / "{}_daily_precipitation.csv".format(station_id)

    processed.to_csv(output_file, index=False)

    print("Wrote {} rows to {}".format(len(processed), output_file))


if __name__ == "__main__":
    main()