import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import date

import requests


NOAA_API_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
RAW_DATA_DIR = Path("data/raw/noaa-precipitation")
DATATYPES = ["PRCP"]


def load_stations() -> Dict[str, Dict]:
    """Load STATIONS from climateview/stations.py or stations.py."""
    project_root = Path(__file__).resolve().parent.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from climateview.stations import STATIONS
    except ModuleNotFoundError:
        from stations import STATIONS

    return STATIONS


def resolve_station(stations: Dict[str, Dict], station_arg: str) -> Tuple[str, Dict]:
    """Resolve a station key or NOAA station ID to its stations.py entry."""
    if station_arg in stations:
        return station_arg, stations[station_arg]

    normalized_id = station_arg.strip()
    if normalized_id.startswith("GHCND:"):
        normalized_id = normalized_id.split(":", 1)[1]

    for station_key, station in stations.items():
        if station.get("noaa_station_id") == normalized_id:
            return station_key, station

    valid_values = ", ".join(
        "{} ({})".format(key, station.get("noaa_station_id", "missing ID"))
        for key, station in stations.items()
    )
    raise ValueError(
        "Unknown station '{}'. Valid stations: {}".format(station_arg, valid_values)
    )


def normalize_station_id(station_code: str) -> Tuple[str, str]:
    station_code = station_code.strip()

    if station_code.startswith("GHCND:"):
        api_station_id = station_code
    else:
        api_station_id = "GHCND:" + station_code

    file_station_id = api_station_id.replace(":", "_").replace("/", "_")

    return api_station_id, file_station_id


def get_noaa_token() -> str:
    token = os.environ.get("NOAA_TOKEN")

    if not token:
        raise RuntimeError(
            "NOAA_TOKEN environment variable is not set. "
            "Run: export NOAA_TOKEN='your_actual_noaa_token'"
        )

    return token


def fetch_noaa_data(
    token: str,
    station_id: str,
    datatype: str,
    start_date: str,
    end_date: str,
    units: str,
) -> List[Dict]:
    params = {
        "datasetid": "GHCND",
        "stationid": station_id,
        "datatypeid": datatype,
        "startdate": start_date,
        "enddate": end_date,
        "limit": 1000,
        "offset": 1,
        "units": units,
    }

    headers = {
        "token": token,
    }

    all_results = []

    while True:
        response = requests.get(
            NOAA_API_URL,
            headers=headers,
            params=params,
            timeout=60,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "NOAA API request failed: {} - {}".format(
                    response.status_code,
                    response.text,
                )
            )

        payload = response.json()
        results = payload.get("results", [])

        all_results.extend(results)

        metadata = payload.get("metadata", {})
        resultset = metadata.get("resultset", {})
        count = resultset.get("count", 0)
        offset = resultset.get("offset", 1)
        limit = resultset.get("limit", 1000)

        if offset + limit > count:
            break

        params["offset"] = offset + limit

        time.sleep(0.2)

    return all_results


def raw_output_path(datatype: str, file_station_id: str, year: int) -> Path:
    return RAW_DATA_DIR / "noaa-precipitation-{}-{}-{}.json".format(
        datatype,
        file_station_id,
        year,
    )


def download_year(
    token: str,
    station_id: str,
    file_station_id: str,
    datatype: str,
    year: int,
    units: str,
    overwrite: bool,
) -> None:
    output_file = raw_output_path(datatype, file_station_id, year)

    if output_file.exists() and not overwrite:
        print("Skipping existing file: {}".format(output_file))
        return

    print("Downloading {} for {}, year {}".format(datatype, station_id, year))

    first_half = fetch_noaa_data(
        token=token,
        station_id=station_id,
        datatype=datatype,
        start_date="{}-01-01".format(year),
        end_date="{}-06-30".format(year),
        units=units,
    )

    second_half = fetch_noaa_data(
        token=token,
        station_id=station_id,
        datatype=datatype,
        start_date="{}-07-01".format(year),
        end_date="{}-12-31".format(year),
        units=units,
    )

    records = first_half + second_half

    records = sorted(records, key=lambda row: row.get("date", ""))
    if not records:
        print(
            f"No {datatype} data available for {station_id}, year {year}; skipping."
        )
        return

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with output_file.open("w") as f:
        json.dump(records, f, indent=2)

    print("Wrote {} records to {}".format(len(records), output_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw daily NOAA precipitation data."
    )

    parser.add_argument(
        "--station",
        help=(
            "Station key from stations.py or NOAA station code, e.g. san_francisco_sfo or USW00023234.  If omitted, all active stations are downloaded."
        ),
    )

    parser.add_argument(
        "--start-year",
        type=int,
        help=(
            "Optional first year to download. If omitted, uses "
            "noaa_start_year from stations.py plus one year."
        ),
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=date.today().year - 1,
        help="Last year to download. Defaults to the last completed calendar year.",
    )

    parser.add_argument(
        "--units",
        choices=["standard", "metric"],
        default="standard",
        help="NOAA units. Use standard for inches.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing raw files.",
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

    token = get_noaa_token()

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
            "Using {} ({}) with start year {} and end year {}".format(
                station.get("name", station_key),
                noaa_station_id,
                start_year,
                args.end_year,
            )
        )

        api_station_id, file_station_id = normalize_station_id(noaa_station_id)

        for year in range(start_year, args.end_year + 1):
            for datatype in DATATYPES:
                download_year(
                    token=token,
                    station_id=api_station_id,
                    file_station_id=file_station_id,
                    datatype=datatype,
                    year=year,
                    units=args.units,
                    overwrite=args.overwrite,
                )

                time.sleep(0.2)


if __name__ == "__main__":
    main()