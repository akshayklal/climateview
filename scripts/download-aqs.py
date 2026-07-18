#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests


# AQS architecture:
# - stations.py stores the selected physical AQS site and pollutant parameter codes.
# - POCs are not stored in stations.py because EPA may add, retire, or replace them.
# - This script discovers all POCs dynamically and saves their monitor metadata.
# - This script downloads all daily rows for all POCs without stitching them.
# - build-processed-aqs-data.py will later stitch POCs chronologically:
#   the most recently opened POC that is still active is used for each date,
#   with fallback to an older active POC when a temporary newer POC closes.

AQS_API_BASE_URL = "https://aqs.epa.gov/data/api"
DAILY_DATA_URL = f"{AQS_API_BASE_URL}/dailyData/bySite"
MONITORS_URL = f"{AQS_API_BASE_URL}/monitors/bySite"

RAW_DATA_DIR = Path("data/raw/aqs")
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 120

# Broad metadata range used only to discover monitor opening and closing dates.
MONITOR_SEARCH_START_DATE = "19500101"

POLLUTANTS = {
    "pm25": {
        "label": "PM2.5",
        "parameter_field": "aqs_pm25_parameter_code",
    },
    "ozone": {
        "label": "Ozone",
        "parameter_field": "aqs_ozone_parameter_code",
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


def resolve_station(
    stations: Dict[str, Dict],
    station_value: str,
) -> Tuple[str, Dict]:
    """Resolve a ClimateView key, NOAA station ID, or AQS site ID."""
    if station_value in stations:
        return station_value, stations[station_value]

    normalized_noaa = station_value.replace("GHCND:", "")

    for station_key, station in stations.items():
        noaa_station_id = str(station.get("noaa_station_id", "")).replace(
            "GHCND:",
            "",
        )
        aqs_site_id = str(station.get("aqs_site_id", ""))

        if normalized_noaa == noaa_station_id or station_value == aqs_site_id:
            return station_key, station

    valid_keys = ", ".join(sorted(stations.keys()))
    raise ValueError(
        "Unknown station '{}'. Valid station keys: {}".format(
            station_value,
            valid_keys,
        )
    )


def get_aqs_credentials(args) -> tuple[str, str]:
    if not args.email:
        raise ValueError("--email is required")

    if not args.key:
        raise ValueError("--key is required")

    return args.email, args.key

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


def parse_aqs_date(value: object) -> date | None:
    if not value:
        return None

    text = str(value)

    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    return None


def raw_output_path(pollutant: str, aqs_site_id: str, year: int) -> Path:
    return (
        RAW_DATA_DIR
        / aqs_site_id
        / "aqs-{}-{}-{}.json".format(
            pollutant,
            aqs_site_id,
            year,
        )
    )


def monitor_output_path(pollutant: str, aqs_site_id: str) -> Path:
    return (
        RAW_DATA_DIR
        / aqs_site_id
        / "aqs-monitors-{}-{}.json".format(
            pollutant,
            aqs_site_id,
        )
    )


def request_aqs(endpoint: str, params: Dict[str, str]) -> List[Dict]:
    """Call an AQS endpoint with retries and return its Data rows."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                endpoint,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
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
    status = str(header[0].get("status", "")).lower() if header else ""

    if "failed" in status or "error" in status:
        error = header[0].get("error", "Unknown AQS API error")
        raise RuntimeError("AQS API returned an error: {}".format(error))

    return payload.get("Data", [])


def fetch_monitors(
    email: str,
    key: str,
    parameter_code: str,
    state: str,
    county: str,
    site: str,
) -> List[Dict]:
    """Fetch all monitor/POC metadata for one site and pollutant."""
    return request_aqs(
        MONITORS_URL,
        {
            "email": email,
            "key": key,
            "param": parameter_code,
            "bdate": MONITOR_SEARCH_START_DATE,
            "edate": date.today().strftime("%Y%m%d"),
            "state": state,
            "county": county,
            "site": site,
        },
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
    """
    Fetch daily summaries for all POCs at one site.

    No POC filter is sent. The raw file therefore retains every POC so the
    processing script can apply the chronological stitching rule later.
    """
    return request_aqs(
        DAILY_DATA_URL,
        {
            "email": email,
            "key": key,
            "param": parameter_code,
            "bdate": "{}0101".format(year),
            "edate": "{}1231".format(year),
            "state": state,
            "county": county,
            "site": site,
        },
    )


def normalize_monitor_records(records: List[Dict]) -> List[Dict]:
    """Sort and de-duplicate monitor metadata returned by AQS."""
    unique = {}

    for record in records:
        poc = str(record.get("poc", ""))
        open_date = record.get("open_date") or record.get("monitor_begin_date")
        close_date = record.get("close_date") or record.get("monitor_end_date")

        key = (
            poc,
            str(open_date or ""),
            str(close_date or ""),
        )
        unique[key] = record

    return sorted(
        unique.values(),
        key=lambda row: (
            parse_aqs_date(
                row.get("open_date") or row.get("monitor_begin_date")
            )
            or date.max,
            int(str(row.get("poc", "0")))
            if str(row.get("poc", "")).isdigit()
            else 10**9,
        ),
    )


def save_monitor_metadata(
    records: List[Dict],
    pollutant: str,
    aqs_site_id: str,
    overwrite: bool,
) -> Path:
    output_file = monitor_output_path(pollutant, aqs_site_id)

    if output_file.exists() and not overwrite:
        print("Using existing monitor metadata: {}".format(output_file))
        return output_file

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)

    print(
        "Wrote {} monitor records to {}".format(
            len(records),
            output_file,
        )
    )

    return output_file


def earliest_monitor_year(records: List[Dict]) -> int | None:
    years = []

    for record in records:
        open_date = parse_aqs_date(
            record.get("open_date") or record.get("monitor_begin_date")
        )

        if open_date is not None:
            years.append(open_date.year)

    return min(years) if years else None


def describe_pocs(records: List[Dict]) -> str:
    pocs = sorted(
        {
            str(record.get("poc"))
            for record in records
            if record.get("poc") not in (None, "")
        },
        key=lambda value: int(value) if value.isdigit() else 10**9,
    )
    return ", ".join(pocs) if pocs else "none"


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
        "Downloading {} for {} ({}), year {}".format(
            pollutant_config["label"],
            station["name"],
            aqs_site_id,
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

    if not records:
        print(
            "No {} data available for {} in {}; skipping.".format(
                pollutant_config["label"],
                station.get("name", station_key),
                year,
            )
        )
        return

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

    downloaded_pocs = sorted(
        {
            str(row.get("poc"))
            for row in records
            if row.get("poc") not in (None, "")
        },
        key=lambda value: int(value) if value.isdigit() else 10**9,
    )

    print(
        "Wrote {} records to {} (POCs: {})".format(
            len(records),
            output_file,
            ", ".join(downloaded_pocs) if downloaded_pocs else "none",
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download raw EPA AQS daily PM2.5 and ozone summaries for "
            "ClimateView stations. All POCs are downloaded."
        )
    )

    parser.add_argument(
        "--station",
        help=(
            "Optional ClimateView station key, NOAA station ID, or AQS site ID. "
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
        help=(
            "First year to download. If omitted, the earliest opening year "
            "among all discovered POCs is used."
        ),
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=date.today().year - 1,
        help="Last year to download. Defaults to the last completed calendar year.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload raw data and monitor metadata even if files already exist.",
    )

    parser.add_argument(
        "--email",
        required=True,
        help="EPA AQS account email address.",
    )

    parser.add_argument(
        "--key",
        required=True,
        help="EPA AQS API key.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.end_year > date.today().year:
        raise ValueError("end-year cannot be later than the current year")

    stations = load_stations()
    email, key = get_aqs_credentials(args)

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

    pollutants = (
        list(POLLUTANTS.keys())
        if args.pollutant == "all"
        else [args.pollutant]
    )

    for station_key, station in selected_stations:
        if not station.get("active", False):
            print(
                "Station {} is inactive but was explicitly selected.".format(
                    station_key
                )
            )

        aqs_site_id = station.get("aqs_site_id")
        if not aqs_site_id:
            print("Skipping {}: no AQS site ID configured.".format(station_key))
            continue

        state, county, site = split_aqs_site_id(aqs_site_id)

        for pollutant in pollutants:
            pollutant_config = POLLUTANTS[pollutant]
            parameter_code = station.get(
                pollutant_config["parameter_field"]
            )

            if not parameter_code:
                print(
                    "Skipping {} {}: no parameter code configured.".format(
                        station_key,
                        pollutant_config["label"],
                    )
                )
                continue

            print(
                "Discovering {} monitors for {} ({})".format(
                    pollutant_config["label"],
                    station.get("name", station_key),
                    aqs_site_id,
                )
            )

            monitor_records = normalize_monitor_records(
                fetch_monitors(
                    email=email,
                    key=key,
                    parameter_code=parameter_code,
                    state=state,
                    county=county,
                    site=site,
                )
            )

            if not monitor_records:
                print(
                    "No {} monitors found for {}; skipping.".format(
                        pollutant_config["label"],
                        station.get("name", station_key),
                    )
                )
                continue

            save_monitor_metadata(
                records=monitor_records,
                pollutant=pollutant,
                aqs_site_id=aqs_site_id,
                overwrite=args.overwrite,
            )

            if args.start_year is not None:
                start_year = args.start_year
            else:
                start_year = earliest_monitor_year(monitor_records)

                if start_year is None:
                    print(
                        "Could not determine a start year for {} {}; skipping.".format(
                            station_key,
                            pollutant_config["label"],
                        )
                    )
                    continue

            if args.end_year < start_year:
                print(
                    "Skipping {} {}: end year {} is earlier than start year {}.".format(
                        station_key,
                        pollutant_config["label"],
                        args.end_year,
                        start_year,
                    )
                )
                continue

            print(
                "Using {} for {} with POCs [{}], start year {}, end year {}".format(
                    station.get("name", station_key),
                    pollutant_config["label"],
                    describe_pocs(monitor_records),
                    start_year,
                    args.end_year,
                )
            )

            for year in range(start_year, args.end_year + 1):
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
