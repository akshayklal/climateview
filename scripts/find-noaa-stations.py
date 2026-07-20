#!/usr/bin/env python3

import argparse
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import requests

# -----------------------------------------------------------------------------
# Example usage
# -----------------------------------------------------------------------------

# Refresh the cached NOAA station and inventory metadata files.
# python3 scripts/find-noaa-stations.py --refresh

# Find Illinois stations using only TMAX and TMIN records.
# python3 scripts/find-noaa-stations.py --state IL --require-elements TMAX,TMIN

# Find currently operating U.S. stations, oldest first.
# python3 scripts/find-noaa-stations.py --country US --limit 30

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
            "records that extend through at least the previous calendar year."
        )
    )

    location_group = parser.add_argument_group("location filters")

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

    record_group = parser.add_argument_group("record filters")

    record_group.add_argument(
        "--require-elements",
        default=",".join(DEFAULT_ELEMENTS),
        help=(
            "Comma-separated required elements. "
            "Default: TMAX,TMIN,PRCP."
        ),
    )

    output_group = parser.add_argument_group("output options")

    output_group.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of stations to display. Use 0 for all. Default: 20.",
    )

    output_group.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload NOAA metadata instead of using local files.",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit cannot be negative")

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

            stations[station_id] = {
                "station_id": station_id,
                "state": line[38:40].strip(),
                "name": line[41:71].strip(),
            }

    return stations


def load_inventory(
    inventory_file: Path,
) -> Dict[str, Dict[str, Tuple[int, int]]]:
    inventory: Dict[str, Dict[str, Tuple[int, int]]] = {}

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

            inventory.setdefault(station_id, {})[element] = (
                first_year,
                last_year,
            )

    return inventory


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
    inventory: Dict[str, Dict[str, Tuple[int, int]]],
    required_elements: Tuple[str, ...],
    state_filter: str = None,
    country_filter: str = None,
) -> List[Dict]:
    """Find current stations with every required element, oldest first."""
    candidates: List[Dict] = []
    latest_required_year = date.today().year - 1

    for station_id, station in stations.items():
        if state_filter and station["state"] != state_filter:
            continue

        if country_filter and not station_id.startswith(country_filter):
            continue

        element_inventory = inventory.get(station_id, {})

        if any(element not in element_inventory for element in required_elements):
            continue

        first_years = [
            element_inventory[element][0]
            for element in required_elements
        ]
        last_years = [
            element_inventory[element][1]
            for element in required_elements
        ]

        common_start = max(first_years)
        common_end = min(last_years)

        if common_end < max(common_start, latest_required_year):
            continue

        candidate = dict(station)
        candidate["elements"] = element_inventory
        candidate["common_start"] = common_start
        candidate["common_end"] = common_end
        candidate["common_years"] = common_end - common_start + 1

        candidates.append(candidate)

    return sorted(
        candidates,
        key=lambda row: (
            row["common_start"],
            row["name"],
        ),
    )


def format_element_range(candidate: Dict, element: str) -> str:
    record = candidate["elements"].get(element)

    if not record:
        return "-"

    return f"{record[0]}-{record[1]}"


def print_results(
    candidates: List[Dict],
    required_elements: Tuple[str, ...],
    limit: int,
) -> None:
    shown = candidates if limit == 0 else candidates[:limit]

    columns = [
        ("Station", 31),
        ("Station ID", 13),
        ("ST", 4),
    ]

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
    inventory = load_inventory(inventory_file)

    print(f"Stations in station metadata: {len(stations):,}")
    print(f"Unique stations in inventory: {len(inventory):,}")

    candidates = build_candidates(
        stations=stations,
        inventory=inventory,
        required_elements=required_elements,
        state_filter=args.state.upper() if args.state else None,
        country_filter=args.country.upper() if args.country else None,
    )

    print_results(
        candidates=candidates,
        required_elements=required_elements,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
