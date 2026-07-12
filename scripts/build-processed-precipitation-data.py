import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


RAW_DATA_DIR = Path("data/raw/noaa-precipitation")
PROCESSED_DATA_DIR = Path("data/processed/noaa-precipitation")


def load_stations() -> Dict[str, Dict]:
    project_root = Path(__file__).resolve().parent.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from climateview.stations import STATIONS

    return STATIONS


def resolve_station(
    stations: Dict[str, Dict],
    station_value: str,
) -> Tuple[str, Dict]:
    if station_value in stations:
        return station_value, stations[station_value]

    normalized_value = station_value.replace("GHCND:", "")

    for station_key, station in stations.items():
        noaa_station_id = str(station.get("noaa_station_id", "")).replace(
            "GHCND:",
            "",
        )

        if noaa_station_id == normalized_value:
            return station_key, station

    valid_keys = ", ".join(sorted(stations.keys()))
    raise ValueError(
        "Unknown station '{}'. Valid station keys: {}".format(
            station_value,
            valid_keys,
        )
    )


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
        help=(
            "ClimateView station key or NOAA station ID. "
            "If omitted, all active stations are processed."
        ),
    )

    parser.add_argument(
        "--start-year",
        type=int,
        help=(
            "First year to process. If omitted, each station uses "
            "noaa_start_year + 1 from stations.py."
        ),
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=date.today().year - 1,
        help="Last year to process. Defaults to the last completed calendar year.",
    )

    return parser.parse_args()

def main() -> None:
    args = parse_args()

    stations = load_stations()

    if args.station:
        station_key, station = resolve_station(stations, args.station)
        selected_stations = [(station_key, station)]
    else:
        selected_stations = [
            (station_key, station)
            for station_key, station in stations.items()
            if station.get("active", False)
        ]

    if not selected_stations:
        raise ValueError("No active stations found in stations.py")

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for station_key, station in selected_stations:
        noaa_station_id = station.get("noaa_station_id")

        if not noaa_station_id:
            print(
                "Skipping station '{}': no noaa_station_id in stations.py".format(
                    station_key
                )
            )
            continue

        if args.start_year is not None:
            start_year = args.start_year
        else:
            noaa_start_year = station.get("noaa_start_year")

            if noaa_start_year is None:
                print(
                    "Skipping station '{}': no noaa_start_year in stations.py "
                    "and --start-year was not specified.".format(station_key)
                )
                continue

            start_year = int(noaa_start_year) + 1

        if args.end_year < start_year:
            print(
                "Skipping station '{}': end year {} is earlier than start year {}.".format(
                    station_key,
                    args.end_year,
                    start_year,
                )
            )
            continue

        print(
            "Processing {} ({}) from {} through {}".format(
                station.get("name", station_key),
                noaa_station_id,
                start_year,
                args.end_year,
            )
        )

        processed = build_processed_precipitation_data(
            station_code=noaa_station_id,
            start_year=start_year,
            end_year=args.end_year,
        )

        station_id = output_station_id(noaa_station_id)
        output_file = PROCESSED_DATA_DIR / "{}_daily_precipitation.csv".format(station_id)

        processed.to_csv(output_file, index=False)

        print("Wrote {} rows to {}".format(len(processed), output_file))


if __name__ == "__main__":
    main()