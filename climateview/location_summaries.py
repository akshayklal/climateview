from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from climateview.aqs_config import AQS_POLLUTANTS
from climateview.statistics.air_quality import (
    calculate_air_quality_period_statistics,
)
from climateview.statistics.precipitation import (
    calculate_precipitation_period_statistics,
)
from climateview.statistics.temperature import (
    calculate_temperature_period_statistics,
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


def analyze_temperature(path: Path) -> dict[str, Any]:
    return calculate_temperature_period_statistics(_read_csv(path))


def analyze_precipitation(path: Path) -> dict[str, Any]:
    return calculate_precipitation_period_statistics(_read_csv(path))


def analyze_air_quality(path: Path, pollutant: str) -> dict[str, Any]:
    config = AQS_POLLUTANTS[pollutant]
    return calculate_air_quality_period_statistics(
        _read_csv(path), value_column=config["value_column"],
        display_scale=config["display_scale"], unit=config["unit"]
    )


def _without_derived_changes(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {
            "absolute_change",
            "percent_change",
            "period_size",
        }
    }


def _changes_from_means(result: dict[str, Any]) -> tuple[float, float]:
    baseline = float(result["baseline_mean"])
    recent = float(result["recent_mean"])
    absolute = recent - baseline
    percent = (absolute / baseline * 100) if baseline else 0.0
    return absolute, percent


def build_map_metrics(
    temperature: dict[str, Any],
    precipitation: dict[str, Any],
    air_quality: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return only supported changes needed to encode landing-map markers."""
    metrics = {}
    if temperature.get("available") and temperature.get("trend_supported"):
        change, _ = _changes_from_means(temperature)
        metrics["temperature"] = {"change": round(change, 1)}
    if precipitation.get("available") and precipitation.get(
        "significant_change"
    ):
        _, change = _changes_from_means(precipitation)
        metrics["precipitation"] = {"change": round(change, 1)}
    for pollutant in ("pm25", "ozone"):
        result = air_quality.get(pollutant, {})
        if not result.get("significant_change"):
            continue
        _, change = _changes_from_means(result)
        metrics[pollutant] = {"change": round(change, 1)}
    return metrics


def build_explorable_patterns(
    summaries: dict[str, dict[str, Any]],
    stations: dict[str, dict[str, Any]],
    *,
    featured_limit: int = 15,
) -> list[dict[str, Any]]:
    """Build a diverse pool of strong, supported findings for the map page."""
    candidates: dict[str, list[tuple[float, dict[str, Any]]]] = {}

    def add(
        category: str,
        station_key: str,
        title: str,
        summary: str,
        score: float,
        pollutant: str | None = None,
        season: str | None = None,
    ) -> None:
        destination_tab = (
            "Temperature"
            if category in {"temperature", "seasonal"}
            else "Precipitation"
            if category == "rainfall"
            else "Air Quality"
        )
        pattern = {
            "id": f"{category}:{station_key}",
            "category": category,
            "station_key": station_key,
            "tab": destination_tab,
            "title": title,
            "summary": summary,
        }
        if pollutant:
            pattern["pollutant"] = pollutant
        if season:
            pattern["season"] = season
        candidates.setdefault(category, []).append((score, pattern))

    for station_key, results in summaries.items():
        station = stations.get(station_key)
        if not station:
            continue
        name = station["name"]

        temperature = results.get("temperature", {})
        if temperature.get("available") and temperature.get(
            "trend_supported"
        ):
            change, _ = _changes_from_means(temperature)
            if abs(change) >= 0.5:
                direction = "warmer" if change > 0 else "cooler"
                detail = (
                    f"{name} is {abs(change):.1f}°F {direction} than its "
                    f"{temperature['baseline_period']} average."
                )
                add(
                    "temperature",
                    station_key,
                    "Long-term warming" if change > 0 else "Long-term cooling",
                    detail,
                    abs(change),
                )

            seasonal = temperature.get("strongest_seasonal_change")
            if (
                seasonal
                and seasonal.get("trend_supported")
                and abs(float(seasonal["change_f"])) >= 1.0
            ):
                seasonal_change = float(seasonal["change_f"])
                direction = "warmer" if seasonal_change > 0 else "cooler"
                add(
                    "seasonal",
                    station_key,
                    "Strong seasonal shift",
                    (
                        f"At {name}, {seasonal['season']} "
                        f"{seasonal['time_of_day']} are "
                        f"{abs(seasonal_change):.1f}°F {direction} than in "
                        f"{temperature['baseline_period']}."
                    ),
                    abs(seasonal_change),
                    season=seasonal["season"],
                )

        precipitation = results.get("precipitation", {})
        if precipitation.get("available") and precipitation.get(
            "significant_change"
        ):
            _, percent = _changes_from_means(precipitation)
            direction = "higher" if percent > 0 else "lower"
            add(
                "rainfall",
                station_key,
                "Heavier rainfall" if percent > 0 else "Less rainfall",
                (
                    f"Annual rainfall in {name} is {abs(percent):.0f}% "
                    f"{direction} than its "
                    f"{precipitation['baseline_period']} average."
                ),
                abs(percent),
            )

        air_quality = results.get("air_quality", {})
        pollutant_changes: dict[str, float] = {}
        for pollutant, label in (
            ("pm25", "Fine-particle pollution"),
            ("ozone", "Ground-level ozone pollution"),
        ):
            result = air_quality.get(pollutant, {})
            if not result.get("significant_change"):
                continue
            _, percent = _changes_from_means(result)
            pollutant_changes[pollutant] = percent
            direction = "down" if percent < 0 else "up"
            add(
                "fine_particles" if pollutant == "pm25" else "ozone",
                station_key,
                (
                    "Fine particles declining"
                    if pollutant == "pm25" and percent < 0
                    else "Fine particles increasing"
                    if pollutant == "pm25"
                    else "Ground-level ozone declining"
                    if percent < 0
                    else "Ground-level ozone increasing"
                ),
                (
                    f"{label} in {name} is {direction} "
                    f"{abs(percent):.0f}% since "
                    f"{str(result['baseline_period']).split('–', 1)[0]}."
                ),
                abs(percent),
                pollutant,
            )

        if (
            set(pollutant_changes) == {"pm25", "ozone"}
            and pollutant_changes["pm25"] * pollutant_changes["ozone"] < 0
        ):
            pm25 = pollutant_changes["pm25"]
            ozone = pollutant_changes["ozone"]
            add(
                "air_quality_contrast",
                station_key,
                "A mixed air-quality story",
                (
                    f"In {name}, fine-particle pollution is "
                    f"{'down' if pm25 < 0 else 'up'} {abs(pm25):.0f}%, while "
                    f"ground-level ozone pollution is "
                    f"{'down' if ozone < 0 else 'up'} {abs(ozone):.0f}%."
                ),
                abs(pm25) + abs(ozone),
                max(
                    pollutant_changes,
                    key=lambda key: abs(pollutant_changes[key]),
                ),
            )

    ranked: dict[str, list[dict[str, Any]]] = {}
    for category, items in candidates.items():
        ordered = sorted(items, reverse=True, key=lambda item: item[0])
        ranked[category] = []
        for category_rank, (_, pattern) in enumerate(ordered, start=1):
            pattern["category_rank"] = category_rank
            pattern["featured"] = False
            ranked[category].append(pattern)

    ordered_patterns = []
    rank = 0
    while True:
        added = False
        for category in sorted(ranked):
            items = ranked[category]
            if rank < len(items):
                ordered_patterns.append(items[rank])
                added = True
        if not added:
            break
        rank += 1

    for pattern in ordered_patterns[:featured_limit]:
        pattern["featured"] = True
    return ordered_patterns


def build_location_summary(
    station: dict[str, Any],
    processed_dir: Path,
) -> dict[str, Any]:
    noaa_id = station["noaa_station_id"]
    aqs_id = station.get("aqs_site_id")
    temperature = analyze_temperature(
        processed_dir
        / "noaa-temperature"
        / f"{noaa_id}_daily_temperature.csv"
    )
    precipitation = analyze_precipitation(
        processed_dir
        / "noaa-precipitation"
        / f"{noaa_id}_daily_precipitation.csv"
    )
    air_quality = {}
    for pollutant in ("pm25", "ozone"):
        air_quality[pollutant] = (
            analyze_air_quality(
                processed_dir / "aqs" / f"aqs-{pollutant}-{aqs_id}.csv", pollutant
            )
            if aqs_id else {"available": False}
        )

    summary = _build_summary_sentence(temperature, precipitation, air_quality)
    supported_air_quality = {
        pollutant: _without_derived_changes(result)
        for pollutant, result in air_quality.items()
        if result.get("available")
    }
    return {
        "summary": summary,
        "map_metrics": build_map_metrics(temperature, precipitation, air_quality),
        "temperature": _without_derived_changes(temperature),
        "precipitation": _without_derived_changes(precipitation),
        "air_quality": supported_air_quality,
    }


def _temperature_sentence(result: dict[str, Any]) -> str:
    if not result.get("available"):
        return "Long-term temperature records are not available"
    change = float(result["absolute_change"])
    if abs(change) < 0.05:
        return (
            f"Temperatures are little changed from the "
            f"{result['baseline_period']} average"
        )

    direction = "warmer" if change > 0 else "cooler"
    sentence = (
        f"{abs(change):.1f}°F {direction} than "
        f"{result['baseline_period']}"
    )
    strongest = result.get("strongest_seasonal_change")
    if strongest and abs(float(strongest["change_f"])) >= 0.5:
        sentence += (
            f", led by {direction} {strongest['season']} "
            f"{strongest['time_of_day']}"
        )
    return sentence


def _environment_clauses(
    precipitation: dict[str, Any],
    air_quality: dict[str, dict[str, Any]],
) -> list[str]:
    clauses = []
    if precipitation.get("available") and precipitation.get(
        "significant_change"
    ):
        percent = float(precipitation["percent_change"])
        direction = "up" if percent > 0 else "down"
        clauses.append(f"annual precipitation {direction} {abs(percent):.0f}%")

    supported_air_changes = sorted(
        [
            (pollutant, result)
            for pollutant, result in air_quality.items()
            if result.get("available") and result.get("significant_change")
        ],
        key=lambda item: (item[0] != "pm25", item[0]),
    )
    for pollutant, result in supported_air_changes:
        label = (
            "fine-particle pollution"
            if pollutant == "pm25"
            else "ground-level ozone pollution"
        )
        percent = float(result["percent_change"])
        direction = "down" if percent < 0 else "up"
        start_year = str(result["baseline_period"]).split("–", 1)[0]
        clauses.append(
            f"{label} {direction} {abs(percent):.0f}% since {start_year}"
        )
    return clauses


def _build_summary_sentence(
    temperature: dict[str, Any],
    precipitation: dict[str, Any],
    air_quality: dict[str, dict[str, Any]],
) -> str:
    clauses = [_temperature_sentence(temperature)]
    clauses.extend(_environment_clauses(precipitation, air_quality))
    return "; ".join(clauses) + "."
