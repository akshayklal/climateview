#!/usr/bin/env python3

import sys
from pathlib import Path

import requests


INVENTORY_URL = (
    "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
    "ghcnd-inventory.txt"
)


def load_stations():
    project_root = Path(__file__).resolve().parent.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from climateview.stations import STATIONS

    return STATIONS


def load_inventory():
    print("Downloading NOAA GHCN-D inventory...")

    response = requests.get(INVENTORY_URL, timeout=120)
    response.raise_for_status()

    inventory = {}

    for line in response.text.splitlines():
        if len(line) < 45:
            continue

        station_id = line[0:11].strip()
        element = line[31:35].strip()
        first_year = int(line[36:40])
        last_year = int(line[41:45])

        inventory[(station_id, element)] = {
            "first_year": first_year,
            "last_year": last_year,
        }

    return inventory


def format_year(inventory, station_id, element):
    record = inventory.get((station_id, element))

    if not record:
        return "-"

    return str(record["first_year"])


def main():
    stations = load_stations()
    inventory = load_inventory()

    print()
    print(
        f"{'Station':34}"
        f"{'Station ID':14}"
        f"{'TMAX':8}"
        f"{'TMIN':8}"
        f"{'PRCP':8}"
    )

    for station_key, station in stations.items():
        if not station.get("active", False):
            continue

        station_id = station["noaa_station_id"]

        print(
            f"{station['name'][:33]:34}"
            f"{station['noaa_station_id']:14}"
            f"{format_year(inventory, station['noaa_station_id'], 'TMAX'):8}"
            f"{format_year(inventory, station['noaa_station_id'], 'TMIN'):8}"
            f"{format_year(inventory, station['noaa_station_id'], 'PRCP'):8}"
        )

if __name__ == "__main__":
    main()