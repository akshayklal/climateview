import argparse
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests


# AQS architecture:
# - stations.py stores the selected physical AQS site and pollutant parameter codes.
# - POCs are not stored in stations.py because EPA may add, retire, or replace them.
# - download-aqs.py will discover and download all POCs dynamically.
# - build-processed-aqs-data.py will later stitch POCs chronologically.
# - On each date, the most recently opened POC that is still active is used.
# - When a temporary newer POC closes, processing falls back to the newest
#   remaining active POC.
#
# Allow imports from the project root when this script is run from scripts/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from climateview.stations import STATIONS


AQS_API_BASE_URL = "https://aqs.epa.gov/data/api"

PARAMETERS = {
    "pm25": {
        "code": "88101",
        "display_name": "PM2.5",
    },
    "ozone": {
        "code": "44201",
        "display_name": "Ozone",
    },
}

DEFAULT_RADIUS_KM = 40.0
DEFAULT_START_YEAR = 1980
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


def format_date(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else "unknown"


def get_first_present(record, *field_names, default=None):
    """Return the first non-empty field found in an API record."""
    for field_name in field_names:
        value = record.get(field_name)

        if value not in (None, ""):
            return value

    return default


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
    start_year,
):
    """Fetch PM2.5 and ozone monitors inside a bounding box."""
    box = build_bounding_box(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )

    response = session.get(
        f"{AQS_API_BASE_URL}/monitors/byBox",
        params={
            "email": email,
            "key": api_key,
            "param": ",".join(
                parameter["code"]
                for parameter in PARAMETERS.values()
            ),
            "bdate": f"{start_year}0101",
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

    return payload.get("Data", [])


def normalize_monitor(
    record,
    station_latitude,
    station_longitude,
):
    """Convert an AQS monitor record into a consistent internal structure."""
    latitude = get_first_present(
        record,
        "latitude",
        "Latitude",
    )
    longitude = get_first_present(
        record,
        "longitude",
        "Longitude",
    )

    if latitude is None or longitude is None:
        return None

    latitude = float(latitude)
    longitude = float(longitude)

    parameter_code = str(
        get_first_present(
            record,
            "parameter_code",
            "Parameter Code",
            default="",
        )
    )

    parameter_key = next(
        (
            key
            for key, parameter in PARAMETERS.items()
            if parameter["code"] == parameter_code
        ),
        parameter_code,
    )

    state_code = str(
        get_first_present(
            record,
            "state_code",
            "State Code",
            default="",
        )
    ).zfill(2)

    county_code = str(
        get_first_present(
            record,
            "county_code",
            "County Code",
            default="",
        )
    ).zfill(3)

    site_number = str(
        get_first_present(
            record,
            "site_number",
            "Site Num",
            "Site Number",
            default="",
        )
    ).zfill(4)

    poc = str(
        get_first_present(
            record,
            "poc",
            "POC",
            default="",
        )
    )

    open_date = get_first_present(
        record,
        "open_date",
        "Open Date",
    )

    close_date = get_first_present(
        record,
        "close_date",
        "Close Date",
    )

    return {
        "site_key": (
            state_code,
            county_code,
            site_number,
        ),
        "state_code": state_code,
        "county_code": county_code,
        "site_number": site_number,
        "aqs_site_id": (
            f"{state_code}-{county_code}-{site_number}"
        ),
        "parameter_key": parameter_key,
        "parameter_code": parameter_code,
        "parameter_name": get_first_present(
            record,
            "parameter_name",
            "Parameter Name",
            default=PARAMETERS.get(
                parameter_key,
                {},
            ).get("display_name", parameter_code),
        ),
        "poc": poc,
        "latitude": latitude,
        "longitude": longitude,
        "distance_km": haversine_distance_km(
            station_latitude,
            station_longitude,
            latitude,
            longitude,
        ),
        "site_name": get_first_present(
            record,
            "local_site_name",
            "Local Site Name",
            default="Unnamed AQS site",
        ),
        "address": get_first_present(
            record,
            "address",
            "Address",
            default="",
        ),
        "city_name": get_first_present(
            record,
            "city_name",
            "City Name",
            default="",
        ),
        "county_name": get_first_present(
            record,
            "county_name",
            "County Name",
            default="",
        ),
        "state_name": get_first_present(
            record,
            "state_name",
            "State Name",
            default="",
        ),
        "monitoring_agency": get_first_present(
            record,
            "monitoring_agency",
            "Monitoring Agency",
            default="Unknown",
        ),
        "open_date": open_date,
        "close_date": close_date,
        "open_date_parsed": parse_date(open_date),
        "close_date_parsed": parse_date(close_date),
        "last_method": get_first_present(
            record,
            "last_method_description",
            "Last Method Description",
            default="",
        ),
    }


def merge_site_monitors(monitors):
    """Group pollutant monitors that belong to the same physical AQS site."""
    sites = {}

    for monitor in monitors:
        site_key = monitor["site_key"]

        if site_key not in sites:
            sites[site_key] = {
                "site_key": site_key,
                "aqs_site_id": monitor["aqs_site_id"],
                "state_code": monitor["state_code"],
                "county_code": monitor["county_code"],
                "site_number": monitor["site_number"],
                "site_name": monitor["site_name"],
                "address": monitor["address"],
                "city_name": monitor["city_name"],
                "county_name": monitor["county_name"],
                "state_name": monitor["state_name"],
                "monitoring_agency": monitor["monitoring_agency"],
                "latitude": monitor["latitude"],
                "longitude": monitor["longitude"],
                "distance_km": monitor["distance_km"],
                "pollutants": defaultdict(list),
            }

        sites[site_key]["pollutants"][
            monitor["parameter_key"]
        ].append(monitor)

    return list(sites.values())


def monitor_coverage_years(monitor):
    start_date = monitor["open_date_parsed"]
    end_date = monitor["close_date_parsed"] or date.today()

    if start_date is None:
        return 0.0

    return max(
        0.0,
        (end_date - start_date).days / 365.25,
    )


def best_monitor_for_pollutant(monitors):
    """
    Select the strongest POC for a pollutant at one physical site.

    Prefer currently active monitors, followed by longest operational record.
    """
    return max(
        monitors,
        key=lambda monitor: (
            monitor["close_date_parsed"] is None,
            monitor_coverage_years(monitor),
            monitor["open_date_parsed"]
            is not None,
        ),
    )


def calculate_site_score(site):
    """
    Rank sites for ClimateView.

    Main priorities:
      1. Both PM2.5 and ozone are available.
      2. Currently operating monitors are preferred.
      3. Longer historical coverage is preferred.
      4. Nearby sites are preferred.
    """
    score = 0.0

    has_pm25 = "pm25" in site["pollutants"]
    has_ozone = "ozone" in site["pollutants"]

    if has_pm25:
        score += 35

    if has_ozone:
        score += 35

    if has_pm25 and has_ozone:
        score += 40

    for parameter_key in ("pm25", "ozone"):
        monitors = site["pollutants"].get(
            parameter_key,
            [],
        )

        if not monitors:
            continue

        best_monitor = best_monitor_for_pollutant(
            monitors
        )

        if best_monitor["close_date_parsed"] is None:
            score += 15

        score += min(
            monitor_coverage_years(best_monitor),
            30,
        )

    score -= site["distance_km"] * 1.5

    return score


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
            monitor["open_date_parsed"] or date.max,
            poc_sort_value(monitor["poc"]),
        ),
    )


def select_active_monitor(monitors, interval_start):
    """
    Select the POC to use at one point in time.

    Priority:
    1. Most recent open date.
    2. Latest close date, with an open-ended monitor preferred.
    3. Lowest POC as a deterministic final tie-breaker.

    The second rule avoids choosing a short-lived parallel or corrected POC
    over a monitor with the same opening date that remains active longer.
    """
    active = []

    for monitor in monitors:
        open_date = monitor["open_date_parsed"]
        close_date = monitor["close_date_parsed"]

        if open_date is None or open_date > interval_start:
            continue

        if close_date is not None and close_date < interval_start:
            continue

        active.append(monitor)

    if not active:
        return None

    def priority(monitor):
        open_date = monitor["open_date_parsed"]
        close_date = monitor["close_date_parsed"] or date.max
        poc_type, poc_value = poc_sort_value(monitor["poc"])

        numeric_poc = poc_value if poc_type == 0 else 10**9
        text_poc = "" if poc_type == 0 else str(poc_value)

        return (
            -open_date.toordinal(),
            -close_date.toordinal(),
            numeric_poc,
            text_poc,
        )

    return min(active, key=priority)


def build_stitching_intervals(monitors):
    """
    Build non-overlapping POC intervals using all monitor opening and closing
    boundaries.

    A newer POC wins while it is active. If it closes before an older monitor,
    the older monitor resumes automatically. Consecutive intervals using the
    same POC are merged.
    """
    valid_monitors = [
        monitor
        for monitor in monitors
        if monitor["open_date_parsed"] is not None
    ]

    if not valid_monitors:
        return []

    boundaries = set()

    for monitor in valid_monitors:
        boundaries.add(monitor["open_date_parsed"])

        close_date = monitor["close_date_parsed"]
        if close_date is not None and close_date < date.max:
            boundaries.add(close_date + timedelta(days=1))

    ordered_boundaries = sorted(boundaries)
    intervals = []

    for index, interval_start in enumerate(ordered_boundaries):
        selected = select_active_monitor(
            valid_monitors,
            interval_start,
        )

        if selected is None:
            continue

        if index + 1 < len(ordered_boundaries):
            interval_end = ordered_boundaries[index + 1] - timedelta(days=1)
        else:
            selected_close = selected["close_date_parsed"]
            interval_end = selected_close

        selected_close = selected["close_date_parsed"]
        if selected_close is not None:
            if interval_end is None or selected_close < interval_end:
                interval_end = selected_close

        if interval_end is not None and interval_end < interval_start:
            continue

        if (
            intervals
            and intervals[-1]["poc"] == selected["poc"]
            and intervals[-1]["end_date"] is not None
            and intervals[-1]["end_date"] + timedelta(days=1) == interval_start
        ):
            intervals[-1]["end_date"] = interval_end
        else:
            intervals.append(
                {
                    "poc": selected["poc"],
                    "start_date": interval_start,
                    "end_date": interval_end,
                }
            )

    return intervals


def print_monitor_table(parameter_key, monitors):
    """
    Print every POC for one pollutant at a physical AQS site.

    POCs are displayed chronologically. This script only reports metadata;
    it does not decide which POC data to retain in the processed time series.
    """
    display_name = PARAMETERS[parameter_key]["display_name"]
    ordered = sorted_monitors(monitors)

    print(f"       {display_name}: parameter={PARAMETERS[parameter_key]['code']}")
    print("         POC  Open date    Close date   Method")
    print("         ---  ----------   ----------   ------")

    for monitor in ordered:
        open_date = format_date(monitor["open_date"])
        close_date = (
            format_date(monitor["close_date"])
            if monitor["close_date"]
            else "present"
        )
        method = monitor["last_method"] or "-"
        print(
            f"         {monitor['poc'] or '-':<4} "
            f"{open_date:<12} "
            f"{close_date:<12} "
            f"{method}"
        )

    print("         Suggested chronological stitching:")

    intervals = build_stitching_intervals(ordered)

    if not intervals:
        print("           No usable monitor intervals found.")
        return

    for interval in intervals:
        end_label = (
            interval["end_date"].isoformat()
            if interval["end_date"] is not None
            else "present"
        )
        print(
            f"           {interval['start_date'].isoformat()} "
            f"to {end_label}: POC {interval['poc'] or '-'}"
        )


def print_site(site, rank):
    pollutants = [
        PARAMETERS[parameter_key]["display_name"]
        for parameter_key in ("pm25", "ozone")
        if parameter_key in site["pollutants"]
    ]

    print(f"  {rank}. {site['site_name']}")
    print(f"     AQS site ID: {site['aqs_site_id']}")
    print(f"     Distance: {site['distance_km']:.1f} km")
    print(
        f"     Coordinates: "
        f"{site['latitude']:.5f}, "
        f"{site['longitude']:.5f}"
    )

    location_parts = [
        part
        for part in (
            site["city_name"],
            site["county_name"],
            site["state_name"],
        )
        if part
    ]

    if location_parts:
        print("     Location: " + ", ".join(location_parts))

    if site["address"]:
        print(f"     Address: {site['address']}")

    print(f"     Monitoring agency: {site['monitoring_agency']}")
    print(
        "     Available pollutants: "
        + (", ".join(pollutants) or "none")
    )

    for parameter_key in ("pm25", "ozone"):
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
    start_year,
    max_results,
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
        f"monitor history searched from {start_year}"
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
            start_year=start_year,
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

    sites = merge_site_monitors(monitors)

    for site in sites:
        site["score"] = calculate_site_score(site)

    sites.sort(
        key=lambda site: (
            -site["score"],
            site["distance_km"],
        )
    )

    if not sites:
        print(
            "No PM2.5 or ozone AQS monitors were found "
            f"within {radius_km:.1f} km."
        )
        print()
        return None

    print(
        f"Found {len(sites)} physical AQS site(s). "
        f"Showing the best {min(max_results, len(sites))}:"
    )
    print()

    for rank, site in enumerate(
        sites[:max_results],
        start=1,
    ):
        print_site(site, rank)

    return sites[0]


def build_updated_station(station, selected_site):
    """
    Return one stations.py entry updated with the suggested physical AQS site.

    POCs and POC start dates are intentionally omitted. They are dynamic AQS
    monitor metadata and will be rediscovered by download-aqs.py.
    """
    updated = dict(station)

    for field_name in (
        "aqs_pm25_poc",
        "aqs_pm25_start_year",
        "aqs_ozone_poc",
        "aqs_ozone_start_year",
        "aqs_pm25_pocs",
        "aqs_ozone_pocs",
    ):
        updated.pop(field_name, None)

    if selected_site is None:
        return updated

    updated["aqs_site_id"] = selected_site["aqs_site_id"]
    updated["aqs_site_name"] = selected_site["site_name"]
    updated["aqs_distance_km"] = round(selected_site["distance_km"], 1)

    if selected_site["pollutants"].get("pm25"):
        updated["aqs_pm25_parameter_code"] = PARAMETERS["pm25"]["code"]

    if selected_site["pollutants"].get("ozone"):
        updated["aqs_ozone_parameter_code"] = PARAMETERS["ozone"]["code"]

    return updated


def format_python_value(value):
    return repr(value)


def print_station_entry(station_key, station, indent="    "):
    """Print one readable, copy-pasteable stations.py entry."""
    print(f'{indent}{station_key!r}: {{')

    ordered_fields = (
        "name",
        "latitude",
        "longitude",
        "noaa_station_id",
        "noaa_start_year",
        "aqs_site_id",
        "aqs_site_name",
        "aqs_distance_km",
        "aqs_pm25_parameter_code",
        "aqs_ozone_parameter_code",
        "active",
    )

    for field_name in ordered_fields:
        if field_name in station:
            print(
                f'{indent}    {field_name!r}: '
                f'{format_python_value(station[field_name])},'
            )

    for field_name, value in station.items():
        if field_name not in ordered_fields:
            print(
                f'{indent}    {field_name!r}: '
                f'{format_python_value(value)},'
            )

    print(f"{indent}}},")


def print_updated_stations(stations):
    """
    Print a complete copy-pasteable stations.py definition.

    The generated definition intentionally contains no POC fields.
    """
    print("=" * 88)
    print("Suggested stations.py")
    print("=" * 88)
    print()
    print("STATIONS = {")

    for station_key, station in stations.items():
        print_station_entry(station_key, station)

    print("}")
    print()

def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Find and rank nearby EPA AQS PM2.5 and ozone "
            "monitoring sites for ClimateView locations."
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
            "If omitted, all active stations are searched."
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
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help=(
            "Earliest monitor operating year to include. "
            f"Default: {DEFAULT_START_YEAR}."
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

    parser.add_argument(
        "--no-stations-output",
        action="store_true",
        help=(
            "Do not print the suggested copy-pasteable STATIONS definition "
            "after the search results. The generated definition omits POCs."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    current_year = date.today().year

    if args.radius_km <= 0:
        raise ValueError(
            "--radius-km must be greater than zero."
        )

    if not 1957 <= args.start_year <= current_year:
        raise ValueError(
            f"--start-year must be between 1957 "
            f"and {current_year}."
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
        selected_stations = {
            station_key: station
            for station_key, station in STATIONS.items()
            if station.get("active", True)
        }

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": (
                "ClimateView high-school climate project"
            ),
        }
    )

    suggested_stations = {
        station_key: dict(station)
        for station_key, station in STATIONS.items()
    }

    for station_key, station in selected_stations.items():
        selected_site = process_station(
            session=session,
            email=args.email,
            api_key=args.key,
            station_key=station_key,
            station=station,
            radius_km=args.radius_km,
            start_year=args.start_year,
            max_results=args.max_results,
        )

        suggested_stations[station_key] = build_updated_station(
            station=station,
            selected_site=selected_site,
        )

    if not args.no_stations_output:
        print_updated_stations(suggested_stations)


if __name__ == "__main__":
    main()