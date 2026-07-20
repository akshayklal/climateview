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
# - stations.py stores the selected physical AQS site.
# - POCs are not stored in stations.py because EPA may add, retire, or replace them.
# - This script discovers all POCs dynamically and saves their monitor metadata.
# - This script downloads all daily rows for all POCs without stitching them.
# - build-processed-aqs-data.py will later stitch POCs chronologically:
#   the oldest active POC is retained until it closes, with per-day fallback
#   to the next-oldest active POC when the preferred monitor has no data.

AQS_API_BASE_URL = "https://aqs.epa.gov/data/api"
DAILY_DATA_URL = f"{AQS_API_BASE_URL}/dailyData/bySite"
MONITORS_URL = f"{AQS_API_BASE_URL}/monitors/bySite"

RAW_DATA_DIR = Path("data/raw/aqs")
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 120

# Broad metadata range used only to discover monitor opening and closing dates.
MONITOR_SEARCH_START_DATE = "19500101"

PARAMETERS = {
    "42101": ("carbon_monoxide", "Carbon monoxide"),
    "14129": ("lead", "Lead"),
    "42602": ("nitrogen_dioxide", "Nitrogen dioxide"),
    "88101": ("pm25", "PM2.5"),
    "81102": ("pm10", "PM10"),
    "44201": ("ozone", "Ozone"),
    "42401": ("sulfur_dioxide", "Sulfur dioxide"),
}


def load_stations() -> Dict[str, Dict]:
    """Load the project station registry."""
    project_root = Path(__file__).resolve().parent.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from climateview.stations import STATIONS

    return STATIONS


def resolve_station(
    stations: Dict[str, Dict],
    station_value: str,
) -> Tuple[str, Dict]:
    """Resolve a NOAA station ID to its stations.py entry."""
    normalized_noaa = station_value.replace("GHCND:", "")

    for station_key, station in stations.items():
        noaa_station_id = str(station.get("noaa_station_id", "")).replace(
            "GHCND:",
            "",
        )
        if normalized_noaa == noaa_station_id:
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
        identity = (
            str(record.get("poc", "")),
            str(record.get("open_date") or ""),
            str(record.get("close_date") or ""),
        )
        unique[identity] = record

    return sorted(
        unique.values(),
        key=lambda row: (
            parse_aqs_date(row.get("open_date")) or date.max,
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
        open_date = parse_aqs_date(record.get("open_date"))
        if open_date:
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
    pollutant: str,
    pollutant_label: str,
    parameter_code: str,
    station_name: str,
    aqs_site_id: str,
    year: int,
    overwrite: bool,
) -> None:
    output_file = raw_output_path(pollutant, aqs_site_id, year)

    if output_file.exists() and not overwrite:
        print("Skipping existing file: {}".format(output_file))
        return

    state, county, site = split_aqs_site_id(aqs_site_id)

    print(
        "Downloading {} for {} ({}), year {}".format(
            pollutant_label,
            station_name,
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
                pollutant_label,
                station_name,
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

    print(
        "Wrote {} records to {} (POCs: {})".format(
            len(records),
            output_file,
            describe_pocs(records),
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download raw EPA AQS daily pollutant summaries for "
            "ClimateView stations. All POCs are downloaded."
        )
    )

    parser.add_argument(
        "--station",
        help=(
            "NOAA station ID, such as USC00111577. "
            "If omitted, all stations are downloaded."
        ),
    )

    parser.add_argument(
        "--pollutant",
        required=True,
        help=(
            "Five-digit AQS parameter code, such as 44201 for ozone "
            "or 88101 for PM2.5."
        ),
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

    stations = load_stations()
    parameter_code = args.pollutant.strip()
    pollutant, pollutant_label = PARAMETERS.get(
        parameter_code,
        (parameter_code, f"AQS parameter {parameter_code}"),
    )
    end_year = date.today().year - 1

    if args.station:
        station_key, station = resolve_station(stations, args.station)
        selected_stations = [(station_key, station)]
    else:
        selected_stations = list(stations.items())

    if not selected_stations:
        raise ValueError("No stations found in stations.py")

    for station_key, station in selected_stations:
        aqs_site_id = station.get("aqs_site_id")
        if not aqs_site_id:
            print("Skipping {}: no AQS site ID configured.".format(station_key))
            continue

        state, county, site = split_aqs_site_id(aqs_site_id)

        station_name = station.get("name", station_key)

        print(
            "Discovering {} monitors for {} ({})".format(
                pollutant_label,
                station_name,
                aqs_site_id,
            )
        )

        monitor_records = normalize_monitor_records(
            fetch_monitors(
                email=args.email,
                key=args.key,
                parameter_code=parameter_code,
                state=state,
                county=county,
                site=site,
            )
        )

        if not monitor_records:
            print(
                "No {} monitors found for {}; skipping.".format(
                    pollutant_label,
                    station_name,
                )
            )
            continue

        save_monitor_metadata(
            records=monitor_records,
            pollutant=pollutant,
            aqs_site_id=aqs_site_id,
            overwrite=args.overwrite,
        )

        start_year = earliest_monitor_year(monitor_records)
        if start_year is None:
            print(
                "Could not determine a start year for {} {}; skipping.".format(
                    station_key,
                    pollutant_label,
                )
            )
            continue

        if end_year < start_year:
            print(
                "Skipping {} {}: end year {} is earlier than start year {}.".format(
                    station_key,
                    pollutant_label,
                    end_year,
                    start_year,
                )
            )
            continue

        print(
            "Using {} for {} with POCs [{}], start year {}, end year {}".format(
                station_name,
                pollutant_label,
                describe_pocs(monitor_records),
                start_year,
                end_year,
            )
        )

        for year in range(start_year, end_year + 1):
            download_year(
                email=args.email,
                key=args.key,
                pollutant=pollutant,
                pollutant_label=pollutant_label,
                parameter_code=parameter_code,
                station_name=station_name,
                aqs_site_id=aqs_site_id,
                year=year,
                overwrite=args.overwrite,
            )

            time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    main()
