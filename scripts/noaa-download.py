import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

import requests

from station_utils import noaa_station_ids, select_stations


NOAA_API_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"


def _noaa_token() -> str:
    token = os.environ.get("NOAA_TOKEN")
    if not token:
        raise RuntimeError(
            "NOAA_TOKEN environment variable is not set. "
            "Run: export NOAA_TOKEN='your_actual_token_here'"
        )
    return token


def _fetch(
    token: str,
    station_id: str,
    datatype: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    response = requests.get(
        NOAA_API_URL,
        headers={"token": token},
        params={
            "datasetid": "GHCND",
            "stationid": station_id,
            "datatypeid": datatype,
            "startdate": start_date,
            "enddate": end_date,
            "limit": 1000,
            "units": "standard",
            "sortfield": "date",
            "sortorder": "asc",
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"NOAA API request failed: {response.status_code} - "
            f"{response.text}"
        )
    return response.json().get("results", [])


def _download_year(
    *,
    token: str,
    station_id: str,
    file_station_id: str,
    datatype: str,
    year: int,
    metric: str,
    raw_data_dir: Path,
    overwrite: bool,
) -> None:
    station_directory = file_station_id.removeprefix("GHCND_")
    output_file = (
        raw_data_dir
        / station_directory
        / f"noaa-{metric}-{datatype}-{file_station_id}-{year}.json"
    )
    if output_file.exists() and not overwrite:
        print(f"Skipping existing file: {output_file}")
        return

    print(f"Downloading {datatype} for {station_id}, year {year}")
    records = _fetch(
        token, station_id, datatype, f"{year}-01-01", f"{year}-06-30"
    ) + _fetch(
        token, station_id, datatype, f"{year}-07-01", f"{year}-12-31"
    )
    if not records:
        print(f"No {datatype} data available for {station_id}, year {year}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)
    print(f"Wrote {len(records)} records to {output_file}")


def run(metric: str, datatypes: tuple[str, ...]) -> None:
    parser = argparse.ArgumentParser(
        description=f"Download raw daily NOAA {metric} data."
    )
    parser.add_argument(
        "--station",
        help="NOAA station ID. If omitted, all stations are downloaded.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even if they already exist.",
    )
    args = parser.parse_args()

    token = _noaa_token()
    end_year = date.today().year - 1
    raw_data_dir = Path(f"data/raw/noaa-{metric}")

    for station_key, station in select_stations(args.station):
        station_id = station.get("noaa_station_id")
        start_year = station.get("noaa_start_year")
        if not station_id or start_year is None:
            print(f"Skipping {station_key}: incomplete NOAA configuration.")
            continue

        start_year = int(start_year)
        if end_year < start_year:
            print(f"Skipping {station_key}: no complete years to download.")
            continue

        print(
            f"Using {station.get('name', station_key)} ({station_id}) "
            f"from {start_year} through {end_year}"
        )
        api_id, file_id, _ = noaa_station_ids(station_id)
        for year in range(start_year, end_year + 1):
            for datatype in datatypes:
                _download_year(
                    token=token,
                    station_id=api_id,
                    file_station_id=file_id,
                    datatype=datatype,
                    year=year,
                    metric=metric,
                    raw_data_dir=raw_data_dir,
                    overwrite=args.overwrite,
                )
                time.sleep(0.2)
