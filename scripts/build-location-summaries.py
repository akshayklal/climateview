#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from climateview.location_summaries import (
    build_explorable_patterns,
    build_location_summary,
)
from climateview.stations import STATIONS


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "location-summaries.json"
DEFAULT_PATTERNS_OUTPUT = (
    PROJECT_ROOT / "data" / "processed" / "patterns-worth-exploring.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build concise map summaries by comparing each location's first "
            "and latest ten years of processed data."
        )
    )
    parser.add_argument(
        "--station",
        choices=sorted(STATIONS),
        help="Build one location by station key. If omitted, build all locations.",
    )
    parser.add_argument(
        "--patterns-output",
        type=Path,
        default=DEFAULT_PATTERNS_OUTPUT,
        help=(
            "Output path for the explorable-pattern pool when building all "
            f"locations. Default: {DEFAULT_PATTERNS_OUTPUT}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    processed_dir = PROJECT_ROOT / "data" / "processed"
    selected = (
        {args.station: STATIONS[args.station]}
        if args.station
        else STATIONS
    )
    summaries = {
        station_key: build_location_summary(
            station,
            processed_dir,
        )
        for station_key, station in selected.items()
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    display_summaries = {
        station_key: {
            "summary": result["summary"],
            "map_metrics": result["map_metrics"],
        }
        for station_key, result in summaries.items()
    }
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(display_summaries, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print(f"Wrote {len(summaries)} location summaries to {args.output}")
    for station_key, summary in summaries.items():
        print(f"{station_key}: {summary['summary']}")

    if not args.station:
        patterns = build_explorable_patterns(summaries, STATIONS)
        args.patterns_output.parent.mkdir(parents=True, exist_ok=True)
        with args.patterns_output.open("w", encoding="utf-8") as file:
            json.dump(patterns, file, indent=2, ensure_ascii=False)
            file.write("\n")
        print(
            f"Wrote {len(patterns)} explorable patterns to "
            f"{args.patterns_output}"
        )


if __name__ == "__main__":
    main()
