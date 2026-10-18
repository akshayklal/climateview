"""Station-specific season definitions shared by charts and summaries.

stations.json selects season_profile: northern, southern, or none. Missing
profiles default to none: latitude alone does not define tropical/polar seasons.
An optional season_months mapping can define local seasons explicitly. Month
lists must be consecutive and in season order, e.g. Wet: [11, 12, 1, 2, 3].
"""

from collections.abc import Mapping


NORTHERN_SEASONS = {
    "Winter": (12, 1, 2),
    "Spring": (3, 4, 5),
    "Summer": (6, 7, 8),
    "Fall": (9, 10, 11),
}
SOUTHERN_SEASONS = {
    "Winter": (6, 7, 8),
    "Spring": (9, 10, 11),
    "Summer": (12, 1, 2),
    "Fall": (3, 4, 5),
}
SeasonMonths = Mapping[str, tuple[int, ...]]


def get_station_seasons(station: Mapping) -> dict[str, tuple[int, ...]]:
    """Return explicit local seasons; never infer four seasons for a new site."""
    profiles = {"northern": NORTHERN_SEASONS, "southern": SOUTHERN_SEASONS, "none": {}}
    if "season_months" in station:
        configured = station["season_months"]
    else:
        profile = station.get("season_profile", "none")
        if profile not in profiles:
            raise ValueError(f"Unknown season_profile: {profile!r}")
        configured = profiles[profile]
    if not isinstance(configured, Mapping):
        raise ValueError("season_months must map season labels to ordered month lists")
    result = {}
    used_months = set()
    used_labels = {"all year"}
    for label, values in configured.items():
        if not isinstance(label, str) or not label.strip() or label.casefold() in used_labels:
            raise ValueError(f"Invalid or duplicate season label: {label!r}")
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"Season {label!r} needs an ordered month list")
        months = tuple(values)
        if any(type(month) is not int or not 1 <= month <= 12 for month in months):
            raise ValueError(f"Invalid months for season {label!r}")
        if len(set(months)) != len(months) or used_months.intersection(months):
            raise ValueError("Season months must not overlap")
        if any(b != a % 12 + 1 for a, b in zip(months, months[1:])):
            raise ValueError(f"Months for {label!r} must be consecutive and in season order")
        result[label] = months
        used_labels.add(label.casefold())
        used_months.update(months)
    return result


def normalize_season(season: str | None, seasons: SeasonMonths) -> str:
    """Reset stale widget selections and resolve lowercase pattern labels."""
    return next(
        (label for label in seasons if label.casefold() == (season or "").casefold()),
        "All year",
    )


def minimum_season_days(months: tuple[int, ...]) -> int:
    """Preserve the existing 60-day threshold for a three-month season."""
    return 20 * len(months)


def rollover_months(months: tuple[int, ...]) -> tuple[int, ...]:
    """Months assigned to the following year for a season crossing January."""
    for index in range(1, len(months)):
        if months[index] < months[index - 1]:
            return months[:index]
    return ()
