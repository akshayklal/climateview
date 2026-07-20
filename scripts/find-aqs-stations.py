import argparse
import math
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests


# AQS architecture:
# - stations.py stores the selected physical AQS site.
# - POCs are not stored in stations.py because EPA may add, retire, or replace them.
# - download-aqs.py will discover and download all POCs dynamically.
# - build-processed-aqs-data.py will later stitch POCs chronologically.
# - On each date, the oldest POC that is still active is used.
# - Processing switches to the next-oldest POC when the older monitor closes.
#
# Allow imports from the project root when this script is run from scripts/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from climateview.stations import STATIONS


AQS_API_BASE_URL = "https://aqs.epa.gov/data/api"
PARAMETERS = {
    "carbon_monoxide": {
        "code": "42101",
        "display_name": "Carbon monoxide",
    },
    "lead": {
        "code": "14129",
        "display_name": "Lead",
    },
    "nitrogen_dioxide": {
        "code": "42602",
        "display_name": "Nitrogen dioxide",
    },
    "pm25": {
        "code": "88101",
        "display_name": "PM2.5",
    },
    "pm10": {
        "code": "81102",
        "display_name": "PM10",
    },
    "ozone": {
        "code": "44201",
        "display_name": "Ozone",
    },
    "sulfur_dioxide": {
        "code": "42401",
        "display_name": "Sulfur dioxide",
    },
}
PARAMETER_KEYS_BY_CODE = {
    parameter["code"]: key for key, parameter in PARAMETERS.items()
}

POC_PARAMETER_KEYS = ("ozone", "pm25")

DEFAULT_RADIUS_KM = 40.0
MONITOR_SEARCH_START_YEAR = 1957
DEFAULT_MAX_RESULTS = 8
REQUEST_TIMEOUT_SECONDS = 60


def haversine_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    """Calculate the great-circle distance between two coordinates."""
    earth_radius_km = 6371.0088

    lat1 = math.radians(latitude_1)
    lon1 = math.radians(longitude_1)
    lat2 = math.radians(latitude_2)
    lon2 = math.radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(math.sqrt(value))


def build_bounding_box(latitude, longitude, radius_km):
    """
    Build an approximate latitude/longitude box surrounding a point.

    The AQS API searches by rectangular bounding box. Results are later
    filtered using the Haversine distance to enforce the requested radius.
    """
    latitude_delta = radius_km / 111.0

    longitude_scale = 111.0 * math.cos(math.radians(latitude))
    if abs(longitude_scale) < 0.0001:
        longitude_delta = 180.0
    else:
        longitude_delta = radius_km / longitude_scale

    return {
        "minlat": latitude - latitude_delta,
        "maxlat": latitude + latitude_delta,
        "minlon": longitude - longitude_delta,
        "maxlon": longitude + longitude_delta,
    }


def parse_date(value):
    """Parse an AQS date value, returning None when unavailable."""
    if not value:
        return None

    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(str(value), date_format).date()
        except ValueError:
            continue

    return None


def check_aqs_response(payload):
    """
    Raise an error when AQS returns an API-level failure.

    AQS frequently returns HTTP 200 even when the response header contains
    an error or warning, so inspect the response header as well.
    """
    header = payload.get("Header", [])

    if not header:
        return

    status = str(header[0].get("status", "")).lower()
    message = header[0].get("error", "")

    if "failed" in status or "error" in status:
        raise RuntimeError(
            f"AQS request failed: {message or header[0]}"
        )


def fetch_monitors(
    session,
    email,
    api_key,
    latitude,
    longitude,
    radius_km,
):
    """Fetch all supported air-quality monitors inside a bounding box."""
    box = build_bounding_box(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )

    parameter_codes = [item["code"] for item in PARAMETERS.values()]
    records = []

    # The AQS API accepts no more than five parameter codes per request.
    for index in range(0, len(parameter_codes), 5):
        response = session.get(
            f"{AQS_API_BASE_URL}/monitors/byBox",
            params={
                "email": email,
                "key": api_key,
                "param": ",".join(parameter_codes[index:index + 5]),
                "bdate": f"{MONITOR_SEARCH_START_YEAR}0101",
                "edate": date.today().strftime("%Y%m%d"),
                "minlat": f"{box['minlat']:.6f}",
                "maxlat": f"{box['maxlat']:.6f}",
                "minlon": f"{box['minlon']:.6f}",
                "maxlon": f"{box['maxlon']:.6f}",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        check_aqs_response(payload)
        records.extend(payload.get("Data", []))

    return records


def normalize_monitor(
    record,
    station_latitude,
    station_longitude,
):
    """Keep the documented AQS fields needed for candidate selection."""
    latitude = record.get("latitude")
    longitude = record.get("longitude")

    if latitude is None or longitude is None:
        return None

    latitude = float(latitude)
    longitude = float(longitude)

    parameter_code = str(record.get("parameter_code", ""))
    parameter_key = PARAMETER_KEYS_BY_CODE.get(parameter_code)

    if parameter_key is None:
        return None

    state_code = str(record.get("state_code", "")).zfill(2)
    county_code = str(record.get("county_code", "")).zfill(3)
    site_number = str(record.get("site_number", "")).zfill(4)

    return {
        "site_key": (state_code, county_code, site_number),
        "aqs_site_id": f"{state_code}-{county_code}-{site_number}",
        "parameter_key": parameter_key,
        "poc": str(record.get("poc", "")),
        "distance_km": haversine_distance_km(
            station_latitude,
            station_longitude,
            latitude,
            longitude,
        ),
        "site_name": record.get("local_site_name") or "Unnamed AQS site",
        "open_date": parse_date(record.get("open_date")),
        "close_date": parse_date(record.get("close_date")),
    }


def merge_site_monitors(monitors):
    """Group pollutant monitors that belong to the same physical AQS site."""
    sites = {}

    for monitor in monitors:
        site_key = monitor["site_key"]

        if site_key not in sites:
            sites[site_key] = {
                "aqs_site_id": monitor["aqs_site_id"],
                "site_name": monitor["site_name"],
                "distance_km": monitor["distance_km"],
                "pollutants": defaultdict(list),
            }

        sites[site_key]["pollutants"][
            monitor["parameter_key"]
        ].append(monitor)

    return list(sites.values())


def site_sort_key(site, parameter_keys):
    """Order candidates by oldest shared coverage, then distance."""
    pollutant_monitors = [site["pollutants"][key] for key in parameter_keys]
    coverage_starts = [
        min(
            (
                monitor["open_date"]
                for monitor in monitors
                if monitor["open_date"] is not None
            ),
            default=date.max,
        )
        for monitors in pollutant_monitors
    ]
    common_start = max(coverage_starts, default=date.max)
    return (common_start, site["distance_km"])


def poc_sort_value(poc):
    """Return a deterministic sortable value for a POC."""
    value = str(poc or "")

    if value.isdigit():
        return (0, int(value))

    return (1, value)


def sorted_monitors(monitors):
    """Return monitors ordered by opening date, then POC."""
    return sorted(
        monitors,
        key=lambda monitor: (
            monitor["open_date"] or date.max,
            poc_sort_value(monitor["poc"]),
        ),
    )


def print_monitor_table(parameter_key, monitors):
    """Print every POC and operating period for one pollutant."""
    display_name = PARAMETERS[parameter_key]["display_name"]
    ordered = sorted_monitors(monitors)

    print(f"     {display_name} POCs:")

    for monitor in ordered:
        open_date = (
            monitor["open_date"].isoformat()
            if monitor["open_date"]
            else "unknown"
        )
        close_date = (
            monitor["close_date"].isoformat()
            if monitor["close_date"]
            else "present"
        )
        print(
            f"       POC {monitor['poc'] or '-'}: "
            f"{open_date} to {close_date}"
        )


def print_site(site, rank, show_pocs_for):
    pollutants = [
        (
            f"{PARAMETERS[parameter_key]['display_name']} "
            f"({PARAMETERS[parameter_key]['code']})"
        )
        for parameter_key in PARAMETERS
        if parameter_key in site["pollutants"]
    ]

    print(
        f"  {rank}. {{'aqs_site_id': {site['aqs_site_id']!r}, "
        f"'aqs_site_name': {site['site_name']!r}, "
        f"'aqs_distance_km': {site['distance_km']:.1f}}} "
        f"| Parameters: {', '.join(pollutants)}"
    )

    for parameter_key in show_pocs_for:
        monitors = site["pollutants"].get(parameter_key, [])

        if monitors:
            print_monitor_table(parameter_key, monitors)

    print()


def process_station(
    session,
    email,
    api_key,
    station_key,
    station,
    radius_km,
    max_results,
    show_pocs_for,
):
    station_latitude = station["latitude"]
    station_longitude = station["longitude"]

    print("=" * 88)
    print(f"{station['name']} ({station_key})")
    print(
        f"ClimateView coordinates: "
        f"{station_latitude:.4f}, "
        f"{station_longitude:.4f}"
    )
    print(
        f"Search radius: {radius_km:.1f} km; "
        f"monitor history searched from {MONITOR_SEARCH_START_YEAR}"
    )
    print()

    try:
        raw_records = fetch_monitors(
            session=session,
            email=email,
            api_key=api_key,
            latitude=station_latitude,
            longitude=station_longitude,
            radius_km=radius_km,
        )
    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"AQS request failed: {exc}")
        print()
        return None

    monitors = []

    for record in raw_records:
        monitor = normalize_monitor(
            record=record,
            station_latitude=station_latitude,
            station_longitude=station_longitude,
        )

        if monitor is None:
            continue

        if monitor["distance_km"] > radius_km:
            continue

        monitors.append(monitor)

    sites = [
        site
        for site in merge_site_monitors(monitors)
        if all(site["pollutants"].get(key) for key in show_pocs_for)
    ]

    sites.sort(key=lambda site: site_sort_key(site, show_pocs_for))

    if not sites:
        print(
            "No AQS sites with all requested parameters were found "
            f"within {radius_km:.1f} km."
        )
        print()
        return

    print(
        f"Found {len(sites)} matching AQS site(s). "
        f"Showing {min(max_results, len(sites))}:"
    )
    print()

    for rank, site in enumerate(
        sites[:max_results],
        start=1,
    ):
        print_site(site, rank, show_pocs_for)


def parse_poc_parameter_keys(value):
    """Parse and validate a comma-separated pollutant list."""
    keys = tuple(dict.fromkeys(part.strip().lower() for part in value.split(",")))
    invalid = [key for key in keys if key not in POC_PARAMETER_KEYS]

    if not keys or invalid:
        valid = ", ".join(POC_PARAMETER_KEYS)
        raise argparse.ArgumentTypeError(
            f"POC parameters must be selected from: {valid}"
        )

    return keys


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Find nearby EPA AQS air-quality monitoring sites "
            "for ClimateView locations."
        )
    )

    parser.add_argument(
        "--email",
        required=True,
        help="Email address registered with the AQS API.",
    )

    parser.add_argument(
        "--key",
        required=True,
        help="AQS API key associated with --email.",
    )

    parser.add_argument(
        "--station",
        choices=sorted(STATIONS.keys()),
        help=(
            "Search one ClimateView station. "
            "If omitted, all stations are searched."
        ),
    )

    parser.add_argument(
        "--show-pocs-for",
        type=parse_poc_parameter_keys,
        default=POC_PARAMETER_KEYS,
        help=(
            "Comma-separated pollutants whose POCs should be listed. "
            "Choices: ozone, pm25. Default: ozone,pm25."
        ),
    )

    parser.add_argument(
        "--radius-km",
        type=float,
        default=DEFAULT_RADIUS_KM,
        help=(
            "Search radius in kilometers. "
            f"Default: {DEFAULT_RADIUS_KM:g}."
        ),
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=(
            "Maximum ranked sites printed for each location. "
            f"Default: {DEFAULT_MAX_RESULTS}."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.radius_km <= 0:
        raise ValueError(
            "--radius-km must be greater than zero."
        )

    if args.max_results <= 0:
        raise ValueError(
            "--max-results must be greater than zero."
        )

    if args.station:
        selected_stations = {
            args.station: STATIONS[args.station]
        }
    else:
        selected_stations = STATIONS

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": (
                "ClimateView high-school climate project"
            ),
        }
    )

    for station_key, station in selected_stations.items():
        process_station(
            session=session,
            email=args.email,
            api_key=args.key,
            station_key=station_key,
            station=station,
            radius_km=args.radius_km,
            max_results=args.max_results,
            show_pocs_for=args.show_pocs_for,
        )



if __name__ == "__main__":
    main()
