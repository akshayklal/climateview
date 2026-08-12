import json
from pathlib import Path


STATIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "stations.json"

with STATIONS_FILE.open(encoding="utf-8") as file:
    STATIONS = json.load(file)
