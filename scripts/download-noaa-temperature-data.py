import argparse
import json
import os
import time
from datetime import date
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import requests


NOAA_API_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
RAW_DATA_DIR = Path("data/raw/noaa-temperature")

DATATYPES = ["TMAX", "TMIN"]


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
    normalized_value = station_value.replace("GHCND:", "")

    for station_key, station in stations.items():
        noaa_station_id = str(station.get("noaa_station_id", "")).replace(
            "GHCND:",
            "",
        )

        if noaa_station_id == normalized_value:
            return station_key, station

    valid_ids = ", ".join(
        station["noaa_station_id"] for station in stations.values()
    )
    raise ValueError(
        "Unknown NOAA station ID '{}'. Valid IDs: {}".format(
            station_value,
            valid_ids,
        )
    )


def get_noaa_token() -> str:
    token = os.environ.get("NOAA_TOKEN")

    if not token:
        raise RuntimeError(
            "NOAA_TOKEN environment variable is not set. "
            "Run: export NOAA_TOKEN='your_actual_token_here'"
        )

    return token



def normalize_station_id(station_code: str) -> Tuple[str, str]:
    """
    Accepts either:
      USW00023234
      GHCND:USW00023234

    Returns:
      api_station_id: GHCND:USW00023234
      file_station_id: GHCND_USW00023234
    """
    station_code = station_code.strip()

    if station_code.startswith("GHCND:"):
        api_station_id = station_code
    else:
        api_station_id = "GHCND:" + station_code

    file_station_id = api_station_id.replace(":", "_").replace("/", "_")
    return api_station_id, file_station_id


def raw_filename(datatype: str, file_station_id: str, year: int) -> Path:
    station_directory = file_station_id.replace("GHCND_", "", 1)

    return (
        RAW_DATA_DIR
        / station_directory
        / "noaa-temperature-{}-{}-{}.json".format(
            datatype,
            file_station_id,
            year,
        )
    )


def fetch_temperature_data(
    token: str,
    station_id: str,
    start_date: str,
    end_date: str,
    datatype: str,
    limit: int = 1000,
) -> List[Dict]:
    headers = {
        "token": token,
    }

    params = {
        "datasetid": "GHCND",
        "stationid": station_id,
        "startdate": start_date,
        "enddate": end_date,
        "datatypeid": datatype,
        "limit": limit,
        "units": "standard",
        "sortfield": "date",
        "sortorder": "asc",
    }

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
    return payload.get("results", [])


def download_year(
    token: str,
    station_id: str,
    file_station_id: str,
    year: int,
    datatype: str,
    overwrite: bool,
) -> None:
    output_file = raw_filename(datatype, file_station_id, year)

    if output_file.exists() and not overwrite:
        print("Already exists, skipping: {}".format(output_file))
        return

    print("Downloading {} for {}, year {}".format(datatype, station_id, year))

    first_half = fetch_temperature_data(
        token=token,
        station_id=station_id,
        start_date="{}-01-01".format(year),
        end_date="{}-06-30".format(year),
        datatype=datatype,
    )

    second_half = fetch_temperature_data(
        token=token,
        station_id=station_id,
        start_date="{}-07-01".format(year),
        end_date="{}-12-31".format(year),
        datatype=datatype,
    )

    records = first_half + second_half
    if not records:
        print(
            f"No {datatype} data available for {station_id}, year {year}; skipping."
        )
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w") as f:
        json.dump(records, f, indent=2)

    print("Wrote {} records to {}".format(len(records), output_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw NOAA GHCN daily TMAX/TMIN data."
    )

    parser.add_argument(
        "--station",
        help=(
            "NOAA station ID, such as USC00111577. "
            "If omitted, all stations are downloaded."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even if they already exist.",
    )

    return parser.parse_args()

def main() -> None:
    args = parse_args()

    stations = load_stations()

    if args.station:
        station_key, station = resolve_station(stations, args.station)
        selected_stations = [(station_key, station)]
    else:
        selected_stations = list(stations.items())

    if not selected_stations:
        raise ValueError("No stations found in stations.py")

    token = get_noaa_token()
    end_year = date.today().year - 1

    for station_key, station in selected_stations:
        noaa_station_id = station.get("noaa_station_id")

        if not noaa_station_id:
            print(
                "Skipping station '{}': no noaa_station_id in stations.py".format(
                    station_key
                )
            )
            continue

        noaa_start_year = station.get("noaa_start_year")

        if noaa_start_year is None:
            print(
                "Skipping station '{}': no noaa_start_year in stations.py.".format(
                    station_key
                )
            )
            continue

        start_year = int(noaa_start_year)

        if end_year < start_year:
            print(
                "Skipping station '{}': end year {} is earlier than start year {}.".format(
                    station_key,
                    end_year,
                    start_year,
                )
            )
            continue

        print(
            "Using {} ({}) with start year {} and end year {}".format(
                station.get("name", station_key),
                noaa_station_id,
                start_year,
                end_year,
            )
        )

        api_station_id, file_station_id = normalize_station_id(noaa_station_id)

        for year in range(start_year, end_year + 1):
            for datatype in DATATYPES:
                download_year(
                    token=token,
                    station_id=api_station_id,
                    file_station_id=file_station_id,
                    year=year,
                    datatype=datatype,
                    overwrite=args.overwrite,
                )

                time.sleep(0.2)


if __name__ == "__main__":
    main()
