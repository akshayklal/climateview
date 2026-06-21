import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests


NOAA_API_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
RAW_DATA_DIR = Path("data/raw")

DATATYPES = ["TMAX", "TMIN"]


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
    return RAW_DATA_DIR / "noaa-temperature-{}-{}-{}.json".format(
        datatype,
        file_station_id,
        year,
    )


def fetch_temperature_data(
    token: str,
    station_id: str,
    start_date: str,
    end_date: str,
    datatype: str,
    units: str,
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
        "units": units,
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
    units: str,
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
        units=units,
    )

    second_half = fetch_temperature_data(
        token=token,
        station_id=station_id,
        start_date="{}-07-01".format(year),
        end_date="{}-12-31".format(year),
        datatype=datatype,
        units=units,
    )

    records = first_half + second_half

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w") as f:
        json.dump(records, f, indent=2)

    print("Wrote {} records to {}".format(len(records), output_file))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw NOAA GHCN daily TMAX/TMIN data by station and year."
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

    parser.add_argument(
        "--units",
        choices=["metric", "standard"],
        default="standard",
        help="NOAA units. Use standard for Fahrenheit, metric for Celsius.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even if they already exist.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.end_year < args.start_year:
        raise ValueError("end-year must be greater than or equal to start-year")

    token = os.environ.get("NOAA_TOKEN")

    if not token:
        raise RuntimeError(
            "NOAA_TOKEN environment variable is not set. "
            "Run: export NOAA_TOKEN='your_actual_token_here'"
        )

    api_station_id, file_station_id = normalize_station_id(args.station)

    for year in range(args.start_year, args.end_year + 1):
        for datatype in DATATYPES:
            download_year(
                token=token,
                station_id=api_station_id,
                file_station_id=file_station_id,
                year=year,
                datatype=datatype,
                units=args.units,
                overwrite=args.overwrite,
            )

            time.sleep(0.2)


if __name__ == "__main__":
    main()