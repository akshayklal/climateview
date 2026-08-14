#!/usr/bin/env python3

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from climateview.aqs_config import AQS_POLLUTANTS as POLLUTANTS
from climateview.aqs_config import AQS_POLLUTANTS_BY_CODE as POLLUTANTS_BY_CODE
from station_utils import select_stations


# AQS processing architecture:
# - stations.py stores the selected physical AQS site.
# - download-aqs.py saves all POCs and all daily summary rows without stitching.
# - This script ranks active POCs for each date using monitor open/close dates.
# - The oldest active POC is preferred until it closes.
# - If the preferred POC has no data on a particular date, the script falls
#   back to the next-oldest active POC that actually has data.
# - After POC selection, duplicate regulatory-standard rows are reduced to one
#   daily row using pollutant-specific sample-duration and standard priorities.

RAW_DATA_DIR = Path("data/raw/aqs")
PROCESSED_DATA_DIR = Path("data/processed/aqs")

def parse_date(value: object) -> Optional[date]:
    if value in (None, ""):
        return None

    text = str(value)

    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    return None


def poc_sort_value(value: object) -> Tuple[int, object]:
    text = str(value or "")

    if text.isdigit():
        return (0, int(text))

    return (1, text)


def active_monitors_ranked(
    monitors: Iterable[Dict],
    observation_date: date,
) -> List[Dict]:
    """Return active monitors oldest-first for one observation date."""
    active = []

    for monitor in monitors:
        open_date = monitor["_open_date"]
        close_date = monitor["_close_date"]

        if open_date is None or open_date > observation_date:
            continue

        if close_date is not None and close_date < observation_date:
            continue

        active.append(monitor)

    def priority(monitor: Dict) -> Tuple:
        open_date = monitor["_open_date"]
        close_date = monitor["_close_date"] or date.max
        return (
            open_date.toordinal(),
            -close_date.toordinal(),
            poc_sort_value(monitor.get("poc")),
        )

    return sorted(active, key=priority)


def normalize_poc(value: object) -> str:
    """Normalize integer-like POC values for metadata/data comparison."""
    if value in (None, ""):
        return ""

    text = str(value).strip()

    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass

    return text


def monitor_file_path(pollutant: str, aqs_site_id: str) -> Path:
    return RAW_DATA_DIR / aqs_site_id / (
        f"aqs-monitors-{pollutant}-{aqs_site_id}.json"
    )


def raw_file_pattern(pollutant: str, aqs_site_id: str) -> str:
    return f"aqs-{pollutant}-{aqs_site_id}-*.json"


def processed_file_path(pollutant: str, aqs_site_id: str) -> Path:
    return PROCESSED_DATA_DIR / f"aqs-{pollutant}-{aqs_site_id}.csv"


def load_json_list(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)

    if not isinstance(value, list):
        raise ValueError("Expected a JSON list in {}".format(path))

    return value


def load_monitor_metadata(
    pollutant: str,
    aqs_site_id: str,
) -> List[Dict]:
    path = monitor_file_path(pollutant, aqs_site_id)

    if not path.exists():
        raise FileNotFoundError(
            "Monitor metadata not found: {}. Run download-aqs.py first.".format(
                path
            )
        )

    monitors = load_json_list(path)

    if not monitors:
        raise ValueError("Monitor metadata is empty: {}".format(path))

    for monitor in monitors:
        monitor["_open_date"] = parse_date(monitor.get("open_date"))
        monitor["_close_date"] = parse_date(monitor.get("close_date"))

    return monitors


def load_raw_rows(
    pollutant: str,
    aqs_site_id: str,
) -> List[Dict]:
    pattern = raw_file_pattern(pollutant, aqs_site_id)
    station_directory = RAW_DATA_DIR / aqs_site_id
    files = sorted(station_directory.glob(pattern))

    if not files:
        raise FileNotFoundError(
            "No raw AQS files found for {} {} using {}".format(
                pollutant,
                aqs_site_id,
                station_directory / pattern,
            )
        )

    rows = []

    for path in files:
        rows.extend(load_json_list(path))

    return rows


def normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def duration_rank(pollutant: str, row: Dict) -> int:
    sample_duration = normalize_text(row.get("sample_duration"))

    for index, preferred in enumerate(
        POLLUTANTS[pollutant]["preferred_sample_durations"]
    ):
        if normalize_text(preferred) == sample_duration:
            return index

    return len(POLLUTANTS[pollutant]["preferred_sample_durations"]) + 1


def standard_rank(pollutant: str, row: Dict) -> int:
    pollutant_standard = normalize_text(row.get("pollutant_standard"))

    for index, preferred in enumerate(
        POLLUTANTS[pollutant]["preferred_standard_terms"]
    ):
        if normalize_text(preferred) in pollutant_standard:
            return index

    # Prefer a non-annual standard over annual duplicates.
    if "annual" in pollutant_standard:
        return 100

    if pollutant_standard:
        return 50

    return 75


def row_quality_priority(pollutant: str, row: Dict) -> Tuple:
    """
    Rank duplicate daily rows after POC filtering.

    Lower tuples are preferred.
    """
    validity = normalize_text(row.get("validity_indicator"))
    validity_rank = 0 if validity == "y" else 1

    observation_percent = row.get("observation_percent")
    try:
        observation_percent_value = float(observation_percent)
    except (TypeError, ValueError):
        observation_percent_value = -1.0

    observation_count = row.get("observation_count")
    try:
        observation_count_value = int(observation_count)
    except (TypeError, ValueError):
        observation_count_value = -1

    has_mean = 0 if row.get("arithmetic_mean") is not None else 1

    return (
        duration_rank(pollutant, row),
        standard_rank(pollutant, row),
        validity_rank,
        has_mean,
        -observation_percent_value,
        -observation_count_value,
        str(row.get("method_code", "")),
    )


def choose_daily_row(pollutant: str, rows: List[Dict]) -> Dict:
    return min(
        rows,
        key=lambda row: row_quality_priority(pollutant, row),
    )


def compact_output_row(row: Dict, pollutant: str) -> Dict:
    """Keep only the daily fields used by the ClimateView application."""
    output = {
        "date": row.get("date_local"),
        "aqi": row.get("aqi"),
    }

    if pollutant == "ozone":
        output["daily_max"] = row.get("first_max_value")
    else:
        output["value"] = row.get("arithmetic_mean")

    return output


def process_pollutant(
    station_key: str,
    station: Dict,
    pollutant: str,
) -> None:
    config = POLLUTANTS[pollutant]
    aqs_site_id = station.get("aqs_site_id")
    parameter_code = config["parameter_code"]

    if not aqs_site_id:
        print("Skipping {}: no aqs_site_id configured.".format(station_key))
        return

    output_path = processed_file_path(pollutant, aqs_site_id)

    monitors = load_monitor_metadata(pollutant, aqs_site_id)
    raw_rows = load_raw_rows(pollutant, aqs_site_id)

    # Group rows by local date, but retain all POCs and all standards initially.
    rows_by_date: Dict[date, List[Dict]] = defaultdict(list)

    for row in raw_rows:
        if str(row.get("parameter_code", "")) != str(parameter_code):
            continue

        observation_date = parse_date(row.get("date_local"))

        if observation_date is None:
            continue

        rows_by_date[observation_date].append(row)

    processed_rows = []
    dates_without_active_monitor = 0
    dates_without_any_active_poc_data = 0
    dates_using_fallback_poc = 0

    for observation_date in sorted(rows_by_date):
        ranked_monitors = active_monitors_ranked(
            monitors,
            observation_date,
        )

        if not ranked_monitors:
            dates_without_active_monitor += 1
            continue

        rows_for_date = rows_by_date[observation_date]
        selected_rows = None
        selected_rank = None

        for rank, monitor in enumerate(ranked_monitors):
            candidate_poc = normalize_poc(monitor.get("poc"))
            candidate_rows = [
                row
                for row in rows_for_date
                if normalize_poc(row.get("poc")) == candidate_poc
            ]

            if candidate_rows:
                selected_rows = candidate_rows
                selected_rank = rank
                break

        if selected_rows is None:
            dates_without_any_active_poc_data += 1
            continue

        if selected_rank:
            dates_using_fallback_poc += 1

        selected_row = choose_daily_row(
            pollutant,
            selected_rows,
        )
        processed_rows.append(
            compact_output_row(selected_row, pollutant)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    value_column = config["value_column"]
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("date", "aqi", value_column),
        )
        writer.writeheader()
        writer.writerows(processed_rows)

    print(
        "Wrote {} daily {} records for {} to {}".format(
            len(processed_rows),
            config["label"],
            station.get("name", station_key),
            output_path,
        )
    )

    if dates_without_active_monitor:
        print(
            "  Dates skipped with no active monitor: {}".format(
                dates_without_active_monitor
            )
        )

    if dates_using_fallback_poc:
        print(
            "  Dates using fallback active POC: {}".format(
                dates_using_fallback_poc
            )
        )

    if dates_without_any_active_poc_data:
        print(
            "  Dates skipped because no active POC had a row: {}".format(
                dates_without_any_active_poc_data
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one stitched daily EPA AQS time series per station and "
            "pollutant from downloaded raw files."
        )
    )

    parser.add_argument(
        "--station",
        help=(
            "NOAA station ID, such as USC00111577. "
            "If omitted, all stations are processed."
        ),
    )

    parser.add_argument(
        "--pollutant",
        choices=sorted(POLLUTANTS_BY_CODE),
        required=True,
        help="AQS parameter code: 88101 for PM2.5 or 44201 for ozone.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pollutant = POLLUTANTS_BY_CODE[args.pollutant]

    for station_key, station in select_stations(args.station):
        try:
            process_pollutant(
                station_key=station_key,
                station=station,
                pollutant=pollutant,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(
                "Skipping {} {}: {}".format(
                    station_key,
                    POLLUTANTS[pollutant]["label"],
                    exc,
                )
            )


if __name__ == "__main__":
    main()
