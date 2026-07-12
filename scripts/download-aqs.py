import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import requests


AQS_API_URL = "https://aqs.epa.gov/data/api/dailyData/bySite"
RAW_DATA_DIR = Path("data/raw/aqs")
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3

POLLUTANTS = {
    "pm25": {
        "label": "PM2.5",
        "parameter_field": "aqs_pm25_parameter_code",
        "poc_field": "aqs_pm25_poc",
    },
    "ozone": {
        "label": "Ozone",
        "parameter_field": "aqs_ozone_parameter_code",
        "poc_field": "aqs_ozone_poc",
    },
}


def load_stations() -> Dict[str, Dict]:
    """Load STATIONS from climateview/stations.py or stations.py."""
    project_root = Path(__file__).resolve().parent.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from climateview.stations import STATIONS

        return STATIONS
    except ModuleNotFoundError:
        try:
            from stations import STATIONS

            return STATIONS
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Could not import STATIONS. Run this script from the ClimateView "
                "project or place stations.py in the project root/climateview package."
            ) from exc


def get_aqs_credentials() -> Tuple[str, str]:
    email = os.environ.get("AQS_EMAIL")
    key = os.environ.get("AQS_KEY")

    if not email or not key:
        raise RuntimeError(
            "AQS_EMAIL and AQS_KEY environment variables must be set.\n"
            "Run:\n"
            "  export AQS_EMAIL='your_email@example.com'\n"
            "  export AQS_KEY='your_aqs_key'"
        )

    return email, key


def split_aqs_site_id(aqs_site_id: str) -> Tuple[str, str, str]:
    """Split an AQS site ID such as 06-075-0005 into state/county/site."""
    parts = aqs_site_id.strip().split("-")

    if len(parts) != 3:
        raise ValueError(
            "Invalid AQS site ID '{}'; expected SS-CCC-NNNN.".format(aqs_site_id)
        )

    state, county, site = parts

    if len(state) != 2 or len(county) != 3 or len(site) != 4:
        raise ValueError(
            "Invalid AQS site ID '{}'; expected SS-CCC-NNNN.".format(aqs_site_id)
        )

    return state, county, site


def raw_output_path(pollutant: str, aqs_site_id: str, year: int) -> Path:
    return RAW_DATA_DIR / "aqs-{}-{}-{}.json".format(
        pollutant,
        aqs_site_id,
        year,
    )


def fetch_daily_data(
    email: str,
    key: str,
    parameter_code: str,
    state: str,
    county: str,
    site: str,
    year: int,
) -> List[Dict]:
    params = {
        "email": email,
        "key": key,
        "param": parameter_code,
        "bdate": "{}0101".format(year),
        "edate": "{}1231".format(year),
        "state": state,
        "county": county,
        "site": site,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                AQS_API_URL,
                params=params,
                timeout=120,
            )
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError("AQS API request failed: {}".format(exc)) from exc

            wait_seconds = 2 ** attempt
            print(
                "Request error; retrying in {} seconds ({}/{})".format(
                    wait_seconds,
                    attempt,
                    MAX_RETRIES,
                )
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code == 200:
            break

        if response.status_code == 429 or response.status_code >= 500:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "AQS API request failed: {} - {}".format(
                        response.status_code,
                        response.text,
                    )
                )

            wait_seconds = 2 ** attempt
            print(
                "AQS returned {}; retrying in {} seconds ({}/{})".format(
                    response.status_code,
                    wait_seconds,
                    attempt,
                    MAX_RETRIES,
                )
            )
            time.sleep(wait_seconds)
            continue

        raise RuntimeError(
            "AQS API request failed: {} - {}".format(
                response.status_code,
                response.text,
            )
        )
    else:
        raise RuntimeError("AQS API request failed after retries.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("AQS API returned invalid JSON.") from exc

    header = payload.get("Header", [])
    status = header[0].get("status") if header else None

    if status == "Failed":
        error = header[0].get("error", "Unknown AQS API error")
        raise RuntimeError("AQS API returned an error: {}".format(error))

    return payload.get("Data", [])


def download_year(
    email: str,
    key: str,
    station_key: str,
    station: Dict,
    pollutant: str,
    year: int,
    overwrite: bool,
) -> None:
    pollutant_config = POLLUTANTS[pollutant]
    parameter_code = station.get(pollutant_config["parameter_field"])
    configured_poc = station.get(pollutant_config["poc_field"])
    aqs_site_id = station.get("aqs_site_id")

    if not aqs_site_id:
        print("Skipping {}: no AQS site ID configured.".format(station_key))
        return

    if not parameter_code:
        print(
            "Skipping {} {}: no parameter code configured.".format(
                station_key,
                pollutant_config["label"],
            )
        )
        return

    output_file = raw_output_path(pollutant, aqs_site_id, year)

    if output_file.exists() and not overwrite:
        print("Skipping existing file: {}".format(output_file))
        return

    state, county, site = split_aqs_site_id(aqs_site_id)

    print(
        "Downloading {} for {} ({}, POC {}), year {}".format(
            pollutant_config["label"],
            station["name"],
            aqs_site_id,
            configured_poc,
            year,
        )
    )

    records = fetch_daily_data(
        email=email,
        key=key,
        parameter_code=parameter_code,
        state=state,
        county=county,
        site=site,
        year=year,
    )

    records = sorted(
        records,
        key=lambda row: (
            row.get("date_local", ""),
            str(row.get("poc", "")),
            row.get("sample_duration", ""),
            row.get("pollutant_standard", ""),
        ),
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)

    matching_poc_count = sum(
        1 for row in records if str(row.get("poc", "")) == str(configured_poc)
    )

    print(
        "Wrote {} records to {} ({} rows match configured POC {})".format(
            len(records),
            output_file,
            matching_poc_count,
            configured_poc,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download raw EPA AQS daily PM2.5 and ozone summaries for "
            "ClimateView stations."
        )
    )

    parser.add_argument(
        "--station",
        help=(
            "Optional ClimateView station key from stations.py. "
            "If omitted, all active stations are downloaded."
        ),
    )

    parser.add_argument(
        "--pollutant",
        choices=["pm25", "ozone", "all"],
        default="all",
        help="Pollutant to download. Default: all.",
    )

    parser.add_argument(
        "--start-year",
        type=int,
        required=True,
        help="First year to download, e.g. 1970.",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=date.today().year,
        help="Last year to download. Default: current year.",
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

    if args.end_year > date.today().year:
        raise ValueError("end-year cannot be later than the current year")

    stations = load_stations()
    email, key = get_aqs_credentials()

    if args.station:
        if args.station not in stations:
            valid_keys = ", ".join(sorted(stations.keys()))
            raise ValueError(
                "Unknown station '{}'. Valid station keys: {}".format(
                    args.station,
                    valid_keys,
                )
            )

        selected_stations = {args.station: stations[args.station]}
    else:
        selected_stations = {
            station_key: station
            for station_key, station in stations.items()
            if station.get("active", False)
        }

    pollutants = (
        list(POLLUTANTS.keys())
        if args.pollutant == "all"
        else [args.pollutant]
    )

    for station_key, station in selected_stations.items():
        if not station.get("active", False):
            print(
                "Station {} is inactive but was explicitly selected.".format(
                    station_key
                )
            )

        for year in range(args.start_year, args.end_year + 1):
            for pollutant in pollutants:
                download_year(
                    email=email,
                    key=key,
                    station_key=station_key,
                    station=station,
                    pollutant=pollutant,
                    year=year,
                    overwrite=args.overwrite,
                )

                time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    main()