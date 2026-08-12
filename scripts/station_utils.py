import sys
from pathlib import Path
from typing import Any


def load_stations() -> dict[str, dict[str, Any]]:
    """Load the project station registry."""
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from climateview.stations import STATIONS

    return STATIONS


def resolve_station(
    stations: dict[str, dict[str, Any]],
    station_value: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve a NOAA station ID to its registry entry."""
    normalized_value = station_value.replace("GHCND:", "")

    for station_key, station in stations.items():
        station_id = str(station.get("noaa_station_id", "")).replace(
            "GHCND:", ""
        )
        if station_id == normalized_value:
            return station_key, station

    valid_ids = ", ".join(
        station["noaa_station_id"] for station in stations.values()
    )
    raise ValueError(
        f"Unknown NOAA station ID '{station_value}'. Valid IDs: {valid_ids}"
    )


def select_stations(station_value: str | None):
    stations = load_stations()
    if station_value:
        return [resolve_station(stations, station_value)]
    return list(stations.items())


def noaa_station_ids(station_code: str) -> tuple[str, str, str]:
    """Return API, filename, and clean forms of a NOAA station ID."""
    clean_id = station_code.strip().replace("GHCND:", "")
    return f"GHCND:{clean_id}", f"GHCND_{clean_id}", clean_id
