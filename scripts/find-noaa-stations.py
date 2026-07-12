#!/usr/bin/env python3

import argparse
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

# -----------------------------------------------------------------------------
# Example usage
# -----------------------------------------------------------------------------

# Refresh the cached NOAA station and inventory metadata files.
# python3 scripts/find-noaa-stations.py --refresh

# Find the oldest stations within 75 km of downtown Chicago that still have data after 2020.
# python3 scripts/find-noaa-stations.py --latitude 41.8781 --longitude -87.6298 --radius-km 75 --active-after 2020 --sort oldest --limit 20

# Find California stations whose common TMAX/TMIN/PRCP record starts in or before 1920 and continues after 2020.
# python3 scripts/find-noaa-stations.py --state CA --started-before 1920 --active-after 2020 --sort oldest --limit 30

# Find Illinois stations with at least 100 years of common TMAX/TMIN/PRCP data.
# python3 scripts/find-noaa-stations.py --state IL --minimum-years 100 --active-after 2020 --sort longest

# Find Illinois stations with "chicago" in the NOAA station name.
# python3 scripts/find-noaa-stations.py --state IL --name chicago --sort oldest

# Find Illinois stations using only TMAX and TMIN records.
# python3 scripts/find-noaa-stations.py --state IL --require-elements TMAX,TMIN --sort oldest

# Find the oldest stations within 50 km of San Francisco.
# python3 scripts/find-noaa-stations.py --latitude 37.7749 --longitude -122.4194 --radius-km 50 --sort oldest

# Find the oldest stations within 100 km of Los Angeles.
# python3 scripts/find-noaa-stations.py --latitude 34.0522 --longitude -118.2437 --radius-km 100 --sort oldest

# Find U.S. stations with at least 150 years of common TMAX/TMIN/PRCP data.
# python3 scripts/find-noaa-stations.py --country US --minimum-years 150 --sort longest

# -----------------------------------------------------------------------------

NOAA_BASE_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"

META_DIR = Path("data/meta")
INVENTORY_FILE = META_DIR / "ghcnd-inventory.txt"
STATIONS_FILE = META_DIR / "ghcnd-stations.txt"

INVENTORY_URL = f"{NOAA_BASE_URL}/ghcnd-inventory.txt"
STATIONS_URL = f"{NOAA_BASE_URL}/ghcnd-stations.txt"

DEFAULT_ELEMENTS = ("TMAX", "TMIN", "PRCP")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find NOAA GHCN-D stations with long temperature and precipitation "
            "records. NOAA metadata is cached in data/meta."
        )
    )

    location_group = parser.add_argument_group("location filters")

    location_group.add_argument(
        "--latitude",
        type=float,
        help="Target latitude for a radius search.",
    )

    location_group.add_argument(
        "--longitude",
        type=float,
        help="Target longitude for a radius search.",
    )

    location_group.add_argument(
        "--radius-km",
        type=float,
        default=100.0,
        help="Search radius in kilometers. Default: 100.",
    )

    location_group.add_argument(
        "--state",
        help="Two-letter U.S. state code, such as IL or CA.",
    )

    location_group.add_argument(
        "--country",
        help=(
            "Two-character GHCN country prefix, such as US, CA, MX, or IN. "
            "The prefix is taken from the first two characters of the station ID."
        ),
    )

    location_group.add_argument(
        "--name",
        help="Case-insensitive text that must appear in the NOAA station name.",
    )

    record_group = parser.add_argument_group("record filters")

    record_group.add_argument(
        "--require-elements",
        default=",".join(DEFAULT_ELEMENTS),
        help=(
            "Comma-separated required elements. "
            "Default: TMAX,TMIN,PRCP."
        ),
    )

    record_group.add_argument(
        "--started-before",
        type=int,
        help=(
            "Require the common record for all requested elements to start "
            "in or before this year."
        ),
    )

    record_group.add_argument(
        "--active-after",
        type=int,
        help=(
            "Require the common record for all requested elements to extend "
            "through at least this year."
        ),
    )

    record_group.add_argument(
        "--minimum-years",
        type=int,
        help="Minimum number of years in the common record.",
    )

    output_group = parser.add_argument_group("output options")

    output_group.add_argument(
        "--sort",
        choices=["oldest", "longest", "distance", "name"],
        default="oldest",
        help="Result ordering. Default: oldest.",
    )

    output_group.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of stations to display. Use 0 for all. Default: 20.",
    )

    output_group.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload NOAA metadata even if cached files already exist.",
    )

    output_group.add_argument(
        "--station-id",
        help=(
            "Show detailed metadata and full element inventory for one NOAA "
            "station ID, such as USC00111577."
        ),
    )

    args = parser.parse_args()

    if (args.latitude is None) != (args.longitude is None):
        parser.error("--latitude and --longitude must be specified together")

    if args.radius_km <= 0:
        parser.error("--radius-km must be greater than zero")

    if args.limit < 0:
        parser.error("--limit cannot be negative")

    if args.minimum_years is not None and args.minimum_years <= 0:
        parser.error("--minimum-years must be greater than zero")

    return args


def download_metadata(
    url: str,
    output_file: Path,
    refresh: bool,
) -> Path:
    if output_file.exists() and not refresh:
        print(f"Using existing metadata file: {output_file}")
        return output_file

    print(f"Downloading {url}")

    response = requests.get(url, timeout=180)
    response.raise_for_status()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(response.content)

    print(f"Saved metadata to {output_file}")
    return output_file


def load_station_metadata(
    stations_file: Path,
) -> Dict[str, Dict]:
    stations: Dict[str, Dict] = {}

    with stations_file.open("r", encoding="utf-8") as file:
        for line in file:
            if len(line) < 71:
                continue

            station_id = line[0:11].strip()

            try:
                latitude = float(line[12:20].strip())
                longitude = float(line[21:30].strip())
                elevation = float(line[31:37].strip())
            except ValueError:
                continue

            stations[station_id] = {
                "station_id": station_id,
                "country": station_id[:2],
                "latitude": latitude,
                "longitude": longitude,
                "elevation_m": elevation,
                "state": line[38:40].strip(),
                "name": line[41:71].strip(),
                "gsn_flag": line[72:75].strip(),
                "hcn_crn_flag": line[76:79].strip(),
                "wmo_id": line[80:85].strip(),
            }

    return stations


def load_inventory(
    inventory_file: Path,
) -> Tuple[Dict[str, Dict[str, Dict[str, int]]], int]:
    inventory: Dict[str, Dict[str, Dict[str, int]]] = {}
    station_ids = set()

    with inventory_file.open("r", encoding="utf-8") as file:
        for line in file:
            if len(line) < 45:
                continue

            station_id = line[0:11].strip()
            element = line[31:35].strip()

            try:
                first_year = int(line[36:40])
                last_year = int(line[41:45])
            except ValueError:
                continue

            station_ids.add(station_id)

            station_inventory = inventory.setdefault(station_id, {})
            station_inventory[element] = {
                "first_year": first_year,
                "last_year": last_year,
            }

    return inventory, len(station_ids)


def haversine_km(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    earth_radius_km = 6371.0088

    lat1 = math.radians(latitude1)
    lon1 = math.radians(longitude1)
    lat2 = math.radians(latitude2)
    lon2 = math.radians(longitude2)

    delta_latitude = lat2 - lat1
    delta_longitude = lon2 - lon1

    a = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_longitude / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def parse_elements(value: str) -> Tuple[str, ...]:
    elements = tuple(
        element.strip().upper()
        for element in value.split(",")
        if element.strip()
    )

    if not elements:
        raise ValueError("At least one required element must be specified")

    return elements


def build_candidates(
    stations: Dict[str, Dict],
    inventory: Dict[str, Dict[str, Dict[str, int]]],
    required_elements: Tuple[str, ...],
    target_latitude: Optional[float],
    target_longitude: Optional[float],
) -> List[Dict]:
    candidates: List[Dict] = []

    for station_id, station in stations.items():
        element_inventory = inventory.get(station_id, {})

        if any(element not in element_inventory for element in required_elements):
            continue

        first_years = [
            element_inventory[element]["first_year"]
            for element in required_elements
        ]
        last_years = [
            element_inventory[element]["last_year"]
            for element in required_elements
        ]

        common_start = max(first_years)
        common_end = min(last_years)

        if common_end < common_start:
            continue

        candidate = dict(station)
        candidate["elements"] = element_inventory
        candidate["common_start"] = common_start
        candidate["common_end"] = common_end
        candidate["common_years"] = common_end - common_start + 1

        if target_latitude is not None and target_longitude is not None:
            candidate["distance_km"] = haversine_km(
                target_latitude,
                target_longitude,
                station["latitude"],
                station["longitude"],
            )
        else:
            candidate["distance_km"] = None

        candidates.append(candidate)

    return candidates


def filter_candidates(
    candidates: Iterable[Dict],
    args: argparse.Namespace,
) -> List[Dict]:
    filtered: List[Dict] = []

    state_filter = args.state.upper() if args.state else None
    country_filter = args.country.upper() if args.country else None
    name_filter = args.name.casefold() if args.name else None

    for candidate in candidates:
        if state_filter and candidate["state"].upper() != state_filter:
            continue

        if country_filter and candidate["country"].upper() != country_filter:
            continue

        if name_filter and name_filter not in candidate["name"].casefold():
            continue

        distance = candidate["distance_km"]
        if distance is not None and distance > args.radius_km:
            continue

        if (
            args.started_before is not None
            and candidate["common_start"] > args.started_before
        ):
            continue

        if (
            args.active_after is not None
            and candidate["common_end"] < args.active_after
        ):
            continue

        if (
            args.minimum_years is not None
            and candidate["common_years"] < args.minimum_years
        ):
            continue

        filtered.append(candidate)

    return filtered


def sort_candidates(candidates: List[Dict], sort_mode: str) -> List[Dict]:
    if sort_mode == "oldest":
        key = lambda row: (
            row["common_start"],
            -row["common_end"],
            row["distance_km"] if row["distance_km"] is not None else math.inf,
            row["name"],
        )
    elif sort_mode == "longest":
        key = lambda row: (
            -row["common_years"],
            row["common_start"],
            row["distance_km"] if row["distance_km"] is not None else math.inf,
            row["name"],
        )
    elif sort_mode == "distance":
        key = lambda row: (
            row["distance_km"] if row["distance_km"] is not None else math.inf,
            row["common_start"],
            row["name"],
        )
    else:
        key = lambda row: (row["name"], row["station_id"])

    return sorted(candidates, key=key)


def format_element_range(candidate: Dict, element: str) -> str:
    record = candidate["elements"].get(element)

    if not record:
        return "-"

    return "{}-{}".format(
        record["first_year"],
        record["last_year"],
    )


def print_results(
    candidates: List[Dict],
    required_elements: Tuple[str, ...],
    limit: int,
) -> None:
    shown = candidates if limit == 0 else candidates[:limit]

    include_distance = any(
        candidate["distance_km"] is not None
        for candidate in candidates
    )

    columns = [
        ("Station", 31),
        ("Station ID", 13),
        ("ST", 4),
    ]

    if include_distance:
        columns.append(("Dist km", 9))

    for element in required_elements:
        columns.append((element, 12))

    columns.extend(
        [
            ("Common", 12),
            ("Years", 7),
        ]
    )

    print()
    print("".join(f"{title:<{width}}" for title, width in columns))
    print("".join("-" * width for _, width in columns))

    for candidate in shown:
        values = [
            candidate["name"][:30],
            candidate["station_id"],
            candidate["state"] or "-",
        ]

        if include_distance:
            values.append(f"{candidate['distance_km']:.1f}")

        for element in required_elements:
            values.append(format_element_range(candidate, element))

        values.extend(
            [
                f"{candidate['common_start']}-{candidate['common_end']}",
                str(candidate["common_years"]),
            ]
        )

        print(
            "".join(
                f"{str(value):<{width}}"
                for value, (_, width) in zip(values, columns)
            )
        )

    print()
    print(f"Matching stations: {len(candidates):,}")
    print(f"Displayed stations: {len(shown):,}")

def print_station_details(
    station_id: str,
    stations: Dict[str, Dict],
    inventory: Dict[str, Dict[str, Dict[str, int]]],
) -> None:
    normalized_station_id = station_id.strip().upper()

    station = stations.get(normalized_station_id)
    if not station:
        raise ValueError(
            "Station '{}' was not found in ghcnd-stations.txt".format(
                normalized_station_id
            )
        )

    element_inventory = inventory.get(normalized_station_id, {})

    print()
    print("Station details")
    print("---------------")
    print(f"Station ID:     {station['station_id']}")
    print(f"Name:           {station['name']}")
    print(f"Country:        {station['country']}")
    print(f"State:          {station['state'] or '-'}")
    print(f"Latitude:       {station['latitude']}")
    print(f"Longitude:      {station['longitude']}")
    print(f"Elevation (m):  {station['elevation_m']}")
    print(f"GSN flag:       {station['gsn_flag'] or '-'}")
    print(f"HCN/CRN flag:   {station['hcn_crn_flag'] or '-'}")
    print(f"WMO ID:         {station['wmo_id'] or '-'}")

    print()
    print("Element inventory")
    print("-----------------")
    print(
        f"{'Element':10}"
        f"{'First year':12}"
        f"{'Last year':12}"
        f"{'Years':8}"
    )

    for element, record in sorted(element_inventory.items()):
        first_year = record["first_year"]
        last_year = record["last_year"]
        years = last_year - first_year + 1

        print(
            f"{element:10}"
            f"{first_year:<12}"
            f"{last_year:<12}"
            f"{years:<8}"
        )

    required = [
        element
        for element in DEFAULT_ELEMENTS
        if element in element_inventory
    ]

    if len(required) == len(DEFAULT_ELEMENTS):
        common_start = max(
            element_inventory[element]["first_year"]
            for element in DEFAULT_ELEMENTS
        )
        common_end = min(
            element_inventory[element]["last_year"]
            for element in DEFAULT_ELEMENTS
        )

        print()
        print(
            "Common TMAX/TMIN/PRCP period: "
            f"{common_start}-{common_end} "
            f"({common_end - common_start + 1} years)"
        )

def main() -> None:
    args = parse_args()
    required_elements = parse_elements(args.require_elements)

    inventory_file = download_metadata(
        INVENTORY_URL,
        INVENTORY_FILE,
        args.refresh,
    )
    stations_file = download_metadata(
        STATIONS_URL,
        STATIONS_FILE,
        args.refresh,
    )

    print("Loading NOAA metadata...")

    stations = load_station_metadata(stations_file)
    inventory, inventory_station_count = load_inventory(inventory_file)

    print(f"Stations in station metadata: {len(stations):,}")
    print(f"Unique stations in inventory: {inventory_station_count:,}")

    if args.station_id:
        print_station_details(
            station_id=args.station_id,
            stations=stations,
            inventory=inventory,
        )
        return

    candidates = build_candidates(
        stations=stations,
        inventory=inventory,
        required_elements=required_elements,
        target_latitude=args.latitude,
        target_longitude=args.longitude,
    )

    candidates = filter_candidates(candidates, args)
    candidates = sort_candidates(candidates, args.sort)

    print_results(
        candidates=candidates,
        required_elements=required_elements,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
