import argparse
import math
import os
import sys
from pathlib import Path

import requests


# Allow imports from the project root when running from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from climateview.stations import STATIONS


OPENAQ_LOCATIONS_URL = "https://api.openaq.org/v3/locations"
DEFAULT_RADIUS_METERS = 25_000
DEFAULT_LIMIT = 100

OPENAQ_SENSORS_URL = "https://api.openaq.org/v3/sensors"

DATE_RANGE_PARAMETERS = {"pm25", "ozone"}

def haversine_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    """Return the great-circle distance between two points in kilometers."""
    earth_radius_km = 6371.0088

    lat1 = math.radians(latitude_1)
    lon1 = math.radians(longitude_1)
    lat2 = math.radians(latitude_2)
    lon2 = math.radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def get_parameter_name(sensor):
    parameter = sensor.get("parameter") or {}

    return (
        parameter.get("name")
        or parameter.get("displayName")
        or parameter.get("description")
        or "unknown"
    )


def normalize_parameter_name(parameter_name):
    value = parameter_name.lower().replace(".", "").replace(" ", "")

    aliases = {
        "pm25": "pm25",
        "pm2.5": "pm25",
        "o3": "ozone",
        "ozone": "ozone",
        "pm10": "pm10",
        "no2": "no2",
        "nitrogendioxide": "no2",
        "co": "co",
        "carbonmonoxide": "co",
        "so2": "so2",
        "sulfurdioxide": "so2",
    }

    return aliases.get(value, value)


def get_location_coordinates(location):
    coordinates = location.get("coordinates") or {}

    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")

    if latitude is None or longitude is None:
        return None, None

    return float(latitude), float(longitude)


def get_owner_name(location):
    owner = location.get("owner") or {}

    return owner.get("name") or "Unknown"


def get_provider_name(location):
    provider = location.get("provider") or {}

    return provider.get("name") or "Unknown"


def score_location(location):
    """
    Higher scores represent more useful candidates.

    Prioritize:
    - stationary locations;
    - active locations;
    - PM2.5 availability;
    - ozone availability;
    - shorter distance.
    """
    score = 0

    if not location.get("isMobile", False):
        score += 20

    if location.get("isMonitor", False):
        score += 10

    if location.get("datetimeLast"):
        score += 5

    parameters = location["parameters"]

    if "pm25" in parameters:
        score += 20

    if "ozone" in parameters:
        score += 15

    if "pm10" in parameters:
        score += 5

    if "no2" in parameters:
        score += 5

    score -= location["distance_km"]

    return score


def fetch_nearby_locations(
    session,
    latitude,
    longitude,
    radius_meters,
):
    response = session.get(
        OPENAQ_LOCATIONS_URL,
        params={
            "coordinates": f"{latitude:.4f},{longitude:.4f}",
            "radius": radius_meters,
            "limit": DEFAULT_LIMIT,
            "page": 1,
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()
    return payload.get("results", [])


def enrich_location(
    location,
    station_latitude,
    station_longitude,
):
    location_latitude, location_longitude = (
        get_location_coordinates(location)
    )

    if location_latitude is None or location_longitude is None:
        return None

    sensors = location.get("sensors") or []

    parameters = {}
    sensor_ids = {}

    for sensor in sensors:
        parameter_name = normalize_parameter_name(
            get_parameter_name(sensor)
        )

        parameters[parameter_name] = True
        sensor_ids.setdefault(parameter_name, []).append(sensor.get("id"))

    enriched = {
        "id": location.get("id"),
        "name": location.get("name") or "Unnamed location",
        "latitude": location_latitude,
        "longitude": location_longitude,
        "distance_km": haversine_distance_km(
            station_latitude,
            station_longitude,
            location_latitude,
            location_longitude,
        ),
        "owner": get_owner_name(location),
        "provider": get_provider_name(location),
        "is_mobile": location.get("isMobile", False),
        "is_monitor": location.get("isMonitor", False),
        "parameters": set(parameters),
        "sensor_ids": sensor_ids,
    }

    enriched["score"] = score_location(enriched)

    return enriched


def print_location(session, location, rank):
    parameters = ", ".join(sorted(location["parameters"])) or "none"

    print(f"  {rank}. {location['name']}")
    print(f"     OpenAQ location ID: {location['id']}")
    print(f"     Distance: {location['distance_km']:.1f} km")
    print(f"     Owner: {location['owner']}")
    print(f"     Provider: {location['provider']}")
    print(f"     Parameters: {parameters}")
    print(f"     Stationary: {'yes' if not location['is_mobile'] else 'no'}")
    print(f"     Monitor: {'yes' if location['is_monitor'] else 'no'}")

    for parameter in sorted(location["sensor_ids"]):
        sensor_ids = location["sensor_ids"][parameter]

        if parameter not in DATE_RANGE_PARAMETERS:
            print(
                f"     {parameter} sensor IDs: "
                + ", ".join(str(sensor_id) for sensor_id in sensor_ids)
            )
            continue

        for sensor_id in sensor_ids:
            date_range = get_sensor_date_range(
                session=session,
                sensor_id=sensor_id,
            )

            if date_range["error"]:
                print(
                    f"     {parameter} sensor {sensor_id}: "
                    f"date range unavailable "
                    f"({date_range['error']})"
                )
            else:
                print(
                    f"     {parameter} sensor {sensor_id}: "
                    f"{date_range['first'] or 'unknown'} "
                    f"to {date_range['last'] or 'unknown'}"
                )
    print()


def process_station(
    session,
    station_key,
    station,
    radius_meters,
    max_results,
):
    latitude = station["latitude"]
    longitude = station["longitude"]

    print("=" * 80)
    print(f"{station['name']} ({station_key})")
    print(f"Coordinates: {latitude:.4f}, {longitude:.4f}")
    print()

    try:
        locations = fetch_nearby_locations(
            session=session,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
        )
    except requests.RequestException as exc:
        print(f"OpenAQ request failed: {exc}")
        print()
        return

    candidates = []

    for location in locations:
        enriched = enrich_location(
            location,
            station_latitude=latitude,
            station_longitude=longitude,
        )

        if enriched is not None:
            candidates.append(enriched)

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            candidate["distance_km"],
        )
    )

    if not candidates:
        print(
            f"No OpenAQ locations found within "
            f"{radius_meters / 1000:.0f} km."
        )
        print()
        return

    for rank, candidate in enumerate(
        candidates[:max_results],
        start=1,
    ):
        print_location(
            session=session,
            location=candidate,
            rank=rank,
        )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Find and rank nearby OpenAQ monitoring locations "
            "for ClimateView stations."
        )
    )

    parser.add_argument(
        "--station",
        choices=sorted(STATIONS.keys()),
        help=(
            "Search only one ClimateView station. "
            "If omitted, all active stations are searched."
        ),
    )

    parser.add_argument(
        "--radius-km",
        type=float,
        default=25.0,
        help="Search radius in kilometers. Maximum: 25. Default: 25.",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum candidate locations to print per station.",
    )

    parser.add_argument(
        "--token",
        default=os.environ.get("OPENAQ_TOKEN"),
        help=(
            "OpenAQ API token. "
            "Defaults to the OPENAQ_TOKEN environment variable."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    if not 0 < args.radius_km <= 25:
        raise ValueError("--radius-km must be greater than 0 and at most 25.")

    if not args.token:
        raise RuntimeError(
            "Specify the OpenAQ token using --token "
            "or set the OPENAQ_TOKEN environment variable."
        )

    session = requests.Session()
    session.headers.update(
        {
            "X-API-Key": args.token,
            "Accept": "application/json",
        }
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

    for station_key, station in selected_stations.items():
        process_station(
            session=session,
            station_key=station_key,
            station=station,
            radius_meters=int(args.radius_km * 1000),
            max_results=args.max_results,
        )


def extract_utc_datetime(datetime_value):
    if not datetime_value:
        return None

    if isinstance(datetime_value, str):
        return datetime_value

    if isinstance(datetime_value, dict):
        return (
            datetime_value.get("utc")
            or datetime_value.get("local")
        )

    return None

def fetch_sensor_metadata(session, sensor_id):
    response = session.get(
        f"{OPENAQ_SENSORS_URL}/{sensor_id}",
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()
    results = payload.get("results", [])

    if not results:
        return None

    return results[0]

def get_sensor_date_range(session, sensor_id):
    try:
        sensor = fetch_sensor_metadata(
            session=session,
            sensor_id=sensor_id,
        )
    except requests.RequestException as exc:
        return {
            "first": None,
            "last": None,
            "error": str(exc),
        }

    if sensor is None:
        return {
            "first": None,
            "last": None,
            "error": "Sensor metadata not found",
        }

    return {
        "first": extract_utc_datetime(
            sensor.get("datetimeFirst")
        ),
        "last": extract_utc_datetime(
            sensor.get("datetimeLast")
        ),
        "error": None,
    }



if __name__ == "__main__":
    main()